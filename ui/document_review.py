"""Interface de revue : l'état de confirmation est propre à chaque document."""

import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import get_args

import streamlit as st

from database import audit
from extraction.confirmation import (
    REQUIRED_FIELDS, DATE_FIELDS, make_confirmation, export_confirmed_csv,
)
from extraction.schema import DOCUMENT_SCHEMAS, ExtractedField


LABELS = {
    "employeur": "Nom de l'employeur", "salaire_net": "Revenu mensuel net (MAD)",
    "date_embauche": "Date d'embauche", "charge_mensuelle_credits": "Charges mensuelles de crédits (MAD)",
    "revenus_complementaires": "Revenus complémentaires mensuels (MAD)",
}
IDENTITY_METADATA_FIELDS = {"identite_ambigue", "noms_non_attribues"}
REVIEW_FIELDS = {
    "bulletin": ("nom", "prenom", "employeur", "poste", "date_embauche", "periode",
                 "salaire_brut", "total_retenues", "salaire_net"),
    "releve": ("banque", "periode_debut", "periode_fin", "solde_final",
               "charge_mensuelle_credits", "revenus_complementaires"),
    "carte_identite": ("nom", "prenom", "cin", "date_naissance", "lieu_naissance",
                       "date_expiration", "adresse"),
    "compromis": ("prix_vente", "adresse_bien", "date_signature"),
}


def _normalized_label(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text).strip().upper()


def _observed_recurring_incoming(transactions):
    """Retourne un total indicatif, jamais une validation automatique."""
    groups = defaultdict(list)
    for item in transactions or []:
        if not isinstance(item, dict) or str(item.get("type") or "").lower() != "credit":
            continue
        label = _normalized_label(item.get("description"))
        if not (label.startswith("VIR-INST DE ") or label.startswith("VIREMENT RECU DE ")):
            continue
        if any(word in label for word in ("SALAIRE", "REMBOURSEMENT", "ANNULATION")):
            continue
        try:
            amount = abs(float(item.get("montant")))
        except (TypeError, ValueError):
            continue
        if amount:
            # Retirer les références numériques variables pour regrouper un même émetteur.
            group = re.sub(r"\b\d+\b", "", label)
            groups[re.sub(r"\s+", " ", group).strip()].append(amount)
    candidates = [values for values in groups.values() if len(values) >= 2]
    if len(candidates) != 1:
        return None
    return round(sum(candidates[0]), 2)


def _numeric(document_type, field):
    annotation = DOCUMENT_SCHEMAS[document_type].model_fields[field].annotation
    return (isinstance(annotation, type) and issubclass(annotation, ExtractedField)
            and float in get_args(annotation.model_fields["value"].annotation))


def render_declared_form(document_type, client_id):
    """Un champ laissé vide n'est pas remplacé par un zéro implicite."""
    fields = list(REQUIRED_FIELDS[document_type])
    if document_type == "releve":
        fields.append("revenus_complementaires")
    if document_type == "compromis":
        fields = ["prix_vente", "adresse_bien"]
    values = {}
    for field in fields:
        label = LABELS.get(field, field.replace("_", " ").capitalize())
        key = f"declared_{client_id}_{document_type}_{field}"
        if _numeric(document_type, field):
            value = st.number_input(label, value=None, min_value=0.0, key=key)
        else:
            value = st.text_input(label, key=key,
                                  help="JJ/MM/AAAA ou AAAA-MM-JJ" if field in DATE_FIELDS else None)
        if value is not None and value != "":
            values[field] = value
    return values


def _review_field_names(fields, document_type):
    """Champs métier visibles, sans les structures techniques volumineuses."""
    names = list(REVIEW_FIELDS.get(document_type, ()))
    for name, decision in fields.items():
        if name in names or name in IDENTITY_METADATA_FIELDS or name == "transactions":
            continue
        value = decision.get("value") if isinstance(decision, dict) else None
        if not isinstance(value, (list, dict)):
            names.append(name)
    return names


def _text_value(value):
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def render_document_review(result, document_type, document_id, advisor_id, session_id, confirmations):
    """Correction compacte : un tableau modifiable et une confirmation globale."""
    fields = result["validation_result"]["fields"]
    st.caption(
        "Modifiez directement la colonne « Valeur ». Les informations techniques "
        "volumineuses, comme les transactions, ne sont pas affichées dans ce tableau."
    )

    original = Path(result.get("pdf_path", ""))
    upload_root = Path("data/uploads").resolve()
    if original.is_file() and original.resolve().is_relative_to(upload_root):
        st.download_button(
            "Consulter le document original",
            original.read_bytes(),
            file_name=original.name,
            key=f"original_{document_id}",
        )

    names = _review_field_names(fields, document_type)
    decisions = {}
    table_rows = []
    for name in names:
        decision = fields.get(name) or {
            "value": None,
            "status": "absent",
            "source": None,
            "reasons": [],
        }
        decisions[name] = decision
        record = confirmations.get(name)
        confirmed = (
            isinstance(record, dict)
            and record.get("document_id") == document_id
            and record.get("status") in ("confirme", "corrige")
            and record.get("source_checked") is True
        )
        value = record.get("value") if confirmed else decision.get("value")
        source = (record.get("source") if confirmed else decision.get("source")) or {}
        if confirmed:
            status = "Confirmée"
        elif value is None:
            status = "À compléter"
        elif decision.get("status") == "signale":
            status = "À vérifier"
        else:
            status = "Extraite"
        document_name = source.get("document") or Path(result.get("pdf_path", "")).name or "Document"
        page = source.get("page")
        source_label = document_name + (f" — page {page}" if page else "")
        table_rows.append({
            "Information": LABELS.get(name, name.replace("_", " ").capitalize()),
            "Valeur": _text_value(value),
            "Statut": status,
            "Justificatif": source_label,
        })

    with st.form(f"document_review_table_form_{document_id}", border=True):
        edited = st.data_editor(
            table_rows,
            hide_index=True,
            width="stretch",
            num_rows="fixed",
            disabled=["Information", "Statut", "Justificatif"],
            column_config={
                "Information": st.column_config.TextColumn("Information", pinned=True),
                "Valeur": st.column_config.TextColumn("Valeur corrigée"),
                "Statut": st.column_config.TextColumn("État"),
                "Justificatif": st.column_config.TextColumn("Source"),
            },
            key=f"document_review_table_{document_id}",
        )
        checked = st.checkbox(
            "J'ai vérifié les informations modifiées avec mon justificatif",
            key=f"document_review_checked_{document_id}",
        )
        submitted = st.form_submit_button(
            "Enregistrer toutes mes corrections",
            icon=":material/save:",
            type="primary",
            width="stretch",
        )

    if submitted:
        if not checked:
            st.error("Cochez la confirmation après avoir vérifié le tableau.")
        else:
            records = edited.to_dict("records") if hasattr(edited, "to_dict") else list(edited)
            prepared = {}
            cleared = []
            errors = []
            required_fields = set(REQUIRED_FIELDS[document_type])
            for index, name in enumerate(names):
                edited_value = records[index].get("Valeur")
                if edited_value is None or not str(edited_value).strip():
                    if name in required_fields:
                        errors.append(
                            f"{LABELS.get(name, name.replace('_', ' ').capitalize())} : "
                            "renseignez une valeur"
                        )
                    else:
                        cleared.append(name)
                    continue
                try:
                    prepared[name] = make_confirmation(
                        document_type,
                        name,
                        edited_value,
                        decisions[name],
                        document_id=document_id,
                        advisor_id=advisor_id,
                        source_checked=True,
                    )
                except (TypeError, ValueError, json.JSONDecodeError) as exc:
                    errors.append(
                        f"{LABELS.get(name, name.replace('_', ' ').capitalize())} : {exc}"
                    )

            if errors:
                for error in errors:
                    st.error(error)
            else:
                for name in cleared:
                    confirmations.pop(name, None)
                for name, record in prepared.items():
                    confirmations[name] = record
                    audit.log_human_confirmation(
                        document_path=result.get("pdf_path", document_id),
                        document_type=document_type,
                        field_name=name,
                        confirmed_value=record["value"],
                        advisor_id=advisor_id,
                        session_id=session_id,
                        original_value=record["original_value"],
                        source=record["source"],
                        confirmation_status=record["status"],
                    )
                st.success("Toutes les corrections du tableau sont enregistrées.")
                st.rerun()

    with st.expander("Voir les extraits utilisés comme preuves", icon=":material/article:"):
        evidence_rows = []
        for name in names:
            source = decisions[name].get("source") or {}
            if source.get("quote"):
                evidence_rows.append({
                    "Information": LABELS.get(name, name.replace("_", " ").capitalize()),
                    "Page": _text_value(source.get("page")),
                    "Extrait OCR": _text_value(source.get("quote")),
                })
        if evidence_rows:
            st.dataframe(evidence_rows, hide_index=True, width="stretch")
        else:
            st.caption("Aucun extrait précis n'est disponible pour ce document.")

    missing = [
        name for name in REQUIRED_FIELDS[document_type]
        if not isinstance(confirmations.get(name), dict)
        or confirmations[name].get("document_id") != document_id
        or confirmations[name].get("value") is None
    ]
    if missing:
        st.warning(
            "Informations obligatoires à vérifier : "
            + ", ".join(LABELS.get(name, name.replace("_", " ").capitalize()) for name in missing)
        )

    try:
        csv_data = export_confirmed_csv(result, document_type, confirmations, document_id)
    except (ValueError, TypeError) as exc:
        st.error(f"Export bloqué : {exc}")
        csv_data = None
    st.download_button(
        "Télécharger mes informations vérifiées (CSV)",
        csv_data or b"",
        file_name=f"champs_confirmes_{document_type}.csv",
        mime="text/csv",
        disabled=csv_data is None,
        key=f"export_{document_id}",
        on_click="ignore",
    )
