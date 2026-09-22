"""Interface de revue : l'état de confirmation est propre à chaque document."""

import json
from typing import get_args
from ui.document_preview import (
    preferred_source_page,
    render_document_preview,
)
import streamlit as st

from database import audit
from extraction.confirmation import (
    REQUIRED_FIELDS, DATE_FIELDS, make_confirmation,
)
from extraction.schema import DOCUMENT_SCHEMAS, ExtractedField


LABELS = {
    "employeur": "Nom de l'employeur", "salaire_net": "Revenu mensuel net (MAD)",
    "date_embauche": "Date d'embauche", "charge_mensuelle_credits": "Charges mensuelles de crédits (MAD)",
    "revenus_complementaires": "Revenus complémentaires mensuels (MAD)",
    "prix_vente": "Prix du bien (MAD)",
}
IDENTITY_METADATA_FIELDS = {"identite_ambigue", "noms_non_attribues"}
REVIEW_FIELDS = {
    "bulletin": ("employeur", "date_embauche", "salaire_net", "periode", "poste",
                 "nom", "prenom"),
    "releve": ("charge_mensuelle_credits", "revenus_complementaires", "banque",
               "periode_debut", "periode_fin"),
    "carte_identite": ("nom", "prenom", "cin", "date_naissance", "lieu_naissance",
                       "date_expiration", "adresse"),
    "compromis": ("prix_vente", "adresse_bien", "date_signature"),
}


def _numeric(document_type, field):
    annotation = DOCUMENT_SCHEMAS[document_type].model_fields[field].annotation
    return (isinstance(annotation, type) and issubclass(annotation, ExtractedField)
            and float in get_args(annotation.model_fields["value"].annotation))


def render_declared_form(document_type, client_id, key_suffix=""):
    """Un champ laissé vide n'est pas remplacé par un zéro implicite."""
    fields = {
        "bulletin": ("salaire_net",),
        "releve": (
            "charge_mensuelle_credits",
            "revenus_complementaires",
        ),
        "compromis": ("prix_vente",),
    }.get(document_type, ())
    values = {}
    for field in fields:
        label = LABELS.get(field, field.replace("_", " ").capitalize())
        suffix = f"_{key_suffix}" if key_suffix else ""
        key = f"declared_{client_id}_{document_type}_{field}{suffix}"
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
    # Les anciens dossiers peuvent encore contenir l'ancien schéma complet.
    # Pour les deux documents les plus chargés, l'interface applique donc une
    # liste blanche stricte au lieu de réafficher ces champs historiques.
    if document_type in {"bulletin", "releve"}:
        return names
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


def render_document_review(
    result,
    document_type,
    document_id,
    advisor_id,
    session_id,
    confirmations,
    submit_label="Valider et continuer",
):
    """Afficher le document et les informations modifiables côte à côte."""
    fields = result["validation_result"]["fields"]
    names = _review_field_names(fields, document_type)

    essential = list(REQUIRED_FIELDS[document_type])

    if document_type == "releve":
        essential.append("revenus_complementaires")

    if document_type == "compromis":
        essential = list(REVIEW_FIELDS[document_type])

    names = list(dict.fromkeys(essential + names))

    decisions = {
        name: fields.get(name) or {
            "value": None,
            "source": None,
        }
        for name in names
    }

    discrepancies = result.get("validation_result", {}).get("discrepancies", [])
    evaluated_discrepancies = [
        discrepancy
        for discrepancy in discrepancies
        if discrepancy.get("passed") is not None
    ]
    failed_discrepancies = [
        discrepancy
        for discrepancy in evaluated_discrepancies
        if discrepancy.get("passed") is False
    ]
    if failed_discrepancies:
        st.warning("Incohérence détectée entre votre saisie et le document :")
        for discrepancy in failed_discrepancies:
            st.markdown(f"- {discrepancy['message']}")
    elif evaluated_discrepancies:
        st.success(
            "Les valeurs déclarées et extraites respectent le seuil d'écart autorisé."
        )

    st.caption(
        "Comparez les informations avec votre justificatif, "
        "corrigez-les si nécessaire, puis validez."
    )

    values = {}

    def render_field(name):
        record = confirmations.get(name) or {}

        confirmed = (
            record.get("document_id") == document_id
            and record.get("source_checked") is True
            and record.get("status") in ("confirme", "corrige")
        )

        value = (
            record.get("value")
            if confirmed
            else decisions[name].get("value")
        )

        label = LABELS.get(
            name,
            name.replace("_", " ").capitalize(),
        )

        values[name] = st.text_input(
            label,
            value=_text_value(value),
            key=f"review_value_{document_id}_{name}",
            help=(
                "JJ/MM/AAAA ou AAAA-MM-JJ"
                if name in DATE_FIELDS
                else None
            ),
        )

        source = decisions[name].get("source") or {}

        if source.get("page"):
            st.caption(
                f"Trouvé à la page {source['page']}"
            )

        if name in (
            "charge_mensuelle_credits",
            "revenus_complementaires",
        ):
            checkbox_label = (
                "Aucun crédit en cours"
                if name == "charge_mensuelle_credits"
                else "Aucun revenu complémentaire"
            )

            absent = st.checkbox(
                checkbox_label,
                key=f"none_{document_id}_{name}",
            )

            if absent:
                values[name] = "0"

    preview_column, information_column = st.columns(
        [1, 1.05],
        gap="large",
    )

    with preview_column:
        render_document_preview(
            document_path=result.get("pdf_path"),
            document_id=document_id,
            preferred_page=preferred_source_page(decisions),
        )

    with information_column:
        st.markdown("#### Informations détectées")

        with st.form(
            f"document_review_form_{document_id}",
            border=True,
        ):
            for name in essential:
                render_field(name)

            additional_fields = [
                name
                for name in names
                if name not in essential
            ]

            if additional_fields:
                with st.expander(
                    "Voir les autres informations"
                ):
                    for name in additional_fields:
                        render_field(name)

            submitted = st.form_submit_button(
                submit_label,
                type="primary",
                width="stretch",
            )

    if not submitted:
        return False

    prepared = {}
    errors = []

    required = set(REQUIRED_FIELDS[document_type])

    if document_type == "releve":
        required.add("revenus_complementaires")

    for name in names:
        value = values[name]

        if not str(value).strip():
            if name in required:
                label = LABELS.get(
                    name,
                    name.replace("_", " ").capitalize(),
                )
                errors.append(
                    f"{label} : renseignez une valeur."
                )
            continue

        try:
            record = make_confirmation(
                document_type,
                name,
                value,
                decisions[name],
                document_id=document_id,
                advisor_id=advisor_id,
                source_checked=True,
            )

            if (
                name == "salaire_net"
                and record["value"] <= 0
            ):
                raise ValueError(
                    "Le revenu doit être supérieur à zéro."
                )

            prepared[name] = record

        except (ValueError, TypeError) as exc:
            errors.append(
                f"{LABELS.get(name, name)} : {exc}"
            )

    if errors:
        for error in errors:
            st.error(error)

        return False

    try:
        for name, record in prepared.items():
            audit.log_human_confirmation(
                document_path=result.get(
                    "pdf_path",
                    document_id,
                ),
                document_type=document_type,
                field_name=name,
                confirmed_value=record["value"],
                advisor_id=advisor_id,
                session_id=session_id,
                original_value=record["original_value"],
                source=record["source"],
                confirmation_status=record["status"],
            )

    except Exception:
        st.error(
            "La validation n’a pas pu être enregistrée. "
            "Vos saisies sont conservées ; réessayez."
        )
        return False

    confirmations.clear()
    confirmations.update(prepared)

    return True
