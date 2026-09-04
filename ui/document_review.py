"""Interface de revue : l'état de confirmation est propre à chaque document."""

import json
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


def render_document_review(result, document_type, document_id, advisor_id, session_id, confirmations):
    fields = result["validation_result"]["fields"]
    st.caption("Aucune valeur n'est validée automatiquement. Vérifiez les justificatifs avant de confirmer.")
    original = Path(result.get("pdf_path", ""))
    upload_root = Path("data/uploads").resolve()
    if original.is_file() and original.resolve().is_relative_to(upload_root):
        st.download_button("Consulter le document original", original.read_bytes(),
                           file_name=original.name, key=f"original_{document_id}")
    for name, decision in fields.items():
        if name in IDENTITY_METADATA_FIELDS:
            continue
        record = confirmations.get(name)
        confirmed = (isinstance(record, dict) and record.get("document_id") == document_id
                     and record.get("status") in ("confirme", "corrige"))
        value = record["value"] if confirmed else decision.get("value")
        with st.container(border=True):
            required = name in REQUIRED_FIELDS[document_type]
            st.subheader(LABELS.get(name, name.replace("_", " ").capitalize()) + (" *" if required else ""))
            if decision.get("confidence") is not None:
                st.caption(f"Confiance déclarée par le modèle : {decision['confidence']:.0%} (non calibrée)")
            source = decision.get("source") or {}
            if source.get("verified"):
                st.caption(f"Document : {source['document']} — page {source['page']}")
                st.text(source["quote"])
                st.caption("Citation retrouvée dans l'OCR ; vérifiez qu'elle justifie réellement la valeur.")
                evidence = source.get("evidence") or []
                if evidence:
                    st.caption("Opérations utilisées pour le calcul :")
                    st.dataframe(
                        [{
                            "Date": item.get("date"), "Libellé": item.get("description"),
                            "Montant (MAD)": item.get("montant"), "Page": item.get("page"),
                            "Extrait OCR": item.get("quote"),
                        } for item in evidence],
                        hide_index=True, width="stretch",
                    )
                    if source.get("regularity_proven") is False:
                        st.warning(
                            "Montant observé sur un seul mois : son caractère régulier "
                            "doit être confirmé par le conseiller."
                        )
            else:
                st.warning("Provenance non vérifiée. Consultez le document original avant toute saisie ou confirmation.")
            discrepancy = decision.get("discrepancy")
            if discrepancy and discrepancy.get("passed") is False:
                declared = discrepancy.get("declared_value")
                extracted = discrepancy.get("extracted_value")
                difference = discrepancy.get("absolute_difference")
                relative = discrepancy.get("relative_difference")
                message = (
                    f"Valeur déclarée : {declared:g} — Valeur extraite : {extracted:g} — "
                    f"Différence : {difference:+g} ({relative:.1%})"
                )
                if discrepancy.get("severity") == "critique":
                    st.error("Écart critique. " + message)
                else:
                    st.warning("Écart à vérifier. " + message)
            for reason in decision.get("reasons", []):
                if not reason.startswith("Écart "):
                    st.caption(reason)
            key = f"review_value_{document_id}_{name}"
            if confirmed:
                st.write("Valeur finale :", value)
                st.caption(f"{record['status']} — {record['advisor_id']} — {record['confirmed_at']}")
                if st.button("Modifier", key=f"reopen_{document_id}_{name}"):
                    try:
                        audit.log_event("human_confirmation_revoked", advisor_id=advisor_id,
                                        session_id=session_id, document_path=result.get("pdf_path", document_id),
                                        document_type=document_type, field_name=name, value=record["value"],
                                        decision="a_reconfirmer", strict=True)
                    except Exception as exc:
                        st.error(f"Réouverture non enregistrée : {exc}")
                        continue
                    # Révoquer la confirmation avant toute nouvelle édition.
                    st.session_state[key] = json.dumps(value, ensure_ascii=False) if isinstance(value, list) else value
                    st.session_state[f"review_check_{document_id}_{name}"] = False
                    del confirmations[name]
                    st.rerun()
                continue
            numeric = _numeric(document_type, name)
            default = float(value) if numeric and value is not None else value
            if isinstance(value, list):
                default = json.dumps(value, ensure_ascii=False)
            elif not numeric:
                default = str(value) if value is not None else ""
            st.session_state.setdefault(key, default)
            if numeric:
                edited = st.number_input("Valeur proposée", value=None, key=key, disabled=False,
                                         step=0.01, format="%.2f")
            else:
                edited = st.text_input("Valeur proposée", key=key,
                                       help="JJ/MM/AAAA ou AAAA-MM-JJ" if name in DATE_FIELDS else None)
            checked = st.checkbox("J'ai vérifié cette valeur dans le justificatif",
                                  key=f"review_check_{document_id}_{name}")
            if st.button("Confirmer", key=f"confirm_{name}_{document_id}", disabled=not checked):
                try:
                    record = make_confirmation(
                        document_type, name, edited, decision, document_id=document_id,
                        advisor_id=advisor_id, source_checked=checked,
                    )
                    audit.log_human_confirmation(
                        document_path=result.get("pdf_path", document_id), document_type=document_type,
                        field_name=name, confirmed_value=record["value"], advisor_id=advisor_id,
                        session_id=session_id, original_value=record["original_value"],
                        source=record["source"], confirmation_status=record["status"],
                    )
                except Exception as exc:
                    st.error(f"Confirmation non enregistrée : {exc}")
                else:
                    confirmations[name] = record
                    st.rerun()
    missing = [name for name in REQUIRED_FIELDS[document_type]
               if not isinstance(confirmations.get(name), dict)
               or confirmations[name].get("document_id") != document_id
               or confirmations[name].get("value") is None]
    if missing:
        st.warning("Dossier incomplet — champs obligatoires à confirmer : " + ", ".join(missing))
    try:
        csv_data = export_confirmed_csv(result, document_type, confirmations, document_id)
    except (ValueError, TypeError) as exc:
        st.error(f"Export bloqué : {exc}")
        csv_data = None
    st.download_button("Exporter les champs confirmés (CSV)", csv_data or b"",
                       file_name=f"champs_confirmes_{document_type}.csv", mime="text/csv",
                       disabled=csv_data is None, key=f"export_{document_id}", on_click="ignore")
    st.caption("Export partiel possible : seuls les champs explicitement confirmés sont inclus.")
