"""Interface de revue : l'état de confirmation est propre à chaque document."""

import json
import math
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


def _credit_editor_rows(source, confirmed_source=None):
    """Construit la grille de choix à partir de toutes les lignes CREDIT."""
    candidates = list((source or {}).get("credit_candidates") or [])
    if not candidates:
        # Compatibilité avec les dossiers extraits avant cette fonctionnalité.
        candidates = [
            {**item, "selected_by_system": True,
             "reason": "revenu complémentaire proposé par le système"}
            for item in (source or {}).get("evidence") or []
        ] + [
            {**item, "selected_by_system": False}
            for item in (source or {}).get("excluded_evidence") or []
        ]

    saved = {
        item.get("candidate_id"): item
        for item in (confirmed_source or {}).get("human_credit_selection") or []
        if item.get("candidate_id")
    }
    rows = []
    for index, candidate in enumerate(candidates):
        candidate_id = candidate.get("candidate_id") or f"legacy-{index}"
        previous = saved.get(candidate_id, {})
        rows.append({
            "Retenir": bool(previous.get(
                "selected", candidate.get("selected_by_system", False)
            )),
            "Date": previous.get("date", candidate.get("date") or ""),
            "Libellé": previous.get(
                "description", candidate.get("description") or "Opération créditrice"
            ),
            "Montant (MAD)": float(previous.get(
                "montant", candidate.get("montant") or 0.0
            )),
            "Avis du système": candidate.get("reason") or "à vérifier",
            "_candidate_id": candidate_id,
            "_page": candidate.get("page"),
            "_quote": candidate.get("quote"),
        })
    return rows


def _credit_selection(editor_value):
    """Normalise la grille Streamlit et calcule le total choisi par le client."""
    if hasattr(editor_value, "to_dict"):
        rows = editor_value.to_dict("records")
    else:
        rows = list(editor_value or [])
    decisions = []
    total = 0.0
    for row in rows:
        amount = float(row.get("Montant (MAD)") or 0.0)
        if not math.isfinite(amount) or amount < 0:
            raise ValueError("Les montants des opérations doivent être positifs et finis.")
        selected = bool(row.get("Retenir"))
        if selected:
            total += amount
        decisions.append({
            "candidate_id": row.get("_candidate_id"),
            "selected": selected,
            "date": row.get("Date"),
            "description": str(row.get("Libellé") or "").strip(),
            "montant": amount,
            "page": row.get("_page"),
            "quote": row.get("_quote"),
        })
    return decisions, round(total, 2)


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
    credit_selections = {}

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

        source = decisions[name].get("source") or {}
        confirmed_source = record.get("source") or {} if confirmed else {}
        if (
            document_type == "releve"
            and name == "revenus_complementaires"
            and source.get("regularity_proven") is False
        ):
            label = "Entrées complémentaires détectées (MAD) — à confirmer"

        if (
            document_type == "releve"
            and name == "revenus_complementaires"
            and (
                source.get("credit_candidates")
                or source.get("evidence")
                or source.get("excluded_evidence")
            )
        ):
            amount_placeholder = st.empty()
            amount_key = f"review_value_{document_id}_{name}_computed"
            manual_key = f"review_value_{document_id}_{name}_manual"

            def mark_credit_selection_changed():
                # Le prochain rerun doit reprendre le total des cases.
                st.session_state[manual_key] = False

            def mark_credit_amount_edited():
                # Une frappe utilisateur ne doit jamais être écrasée par le
                # montant proposé lors du rerun déclenché par le champ.
                st.session_state[manual_key] = True

            if source.get("page"):
                st.caption(f"Trouvé à la page {source['page']}")

            with st.expander("Voir le détail du calcul"):
                st.caption(
                    "Le système présélectionne les revenus probables. "
                    "Cochez ou décochez une opération : le montant total "
                    "est recalculé immédiatement."
                )
                edited_rows = st.data_editor(
                    _credit_editor_rows(source, confirmed_source),
                    key=f"credit_income_editor_{document_id}",
                    hide_index=True,
                    width="stretch",
                    column_config={
                        "Retenir": st.column_config.CheckboxColumn(
                            "Retenir", help="Inclure cette opération dans le total"
                        ),
                        "Date": st.column_config.TextColumn("Date"),
                        "Libellé": st.column_config.TextColumn("Libellé"),
                        "Montant (MAD)": st.column_config.NumberColumn(
                            "Montant (MAD)", min_value=0.0, format="%.2f"
                        ),
                        "Avis du système": st.column_config.TextColumn(
                            "Avis du système"
                        ),
                        "_candidate_id": None,
                        "_page": None,
                        "_quote": None,
                    },
                    disabled=["Date", "Avis du système"],
                    num_rows="fixed",
                    on_change=mark_credit_selection_changed,
                )
            try:
                selection, selected_total = _credit_selection(edited_rows)
                credit_selections[name] = selection
                if (
                    amount_key not in st.session_state
                    or not st.session_state.get(manual_key, False)
                ):
                    st.session_state[amount_key] = f"{selected_total:.2f}"

                with amount_placeholder.container():
                    manual_total = st.text_input(
                        label,
                        key=amount_key,
                        on_change=mark_credit_amount_edited,
                        help=(
                            "Montant proposé d'après les opérations cochées. "
                            "Vous pouvez le corriger manuellement."
                        ),
                    )
                values[name] = str(manual_total)
            except (TypeError, ValueError) as exc:
                credit_selections[name] = []
                values[name] = ""
                with amount_placeholder.container():
                    st.error(str(exc))
            return

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

        if name in ("charge_mensuelle_credits", "revenus_complementaires"):
            evidence = source.get("evidence") or []
            excluded = source.get("excluded_evidence") or []
            method = source.get("method")
            if evidence or excluded or method:
                with st.expander("Voir le détail du calcul"):
                    if method:
                        st.caption(method)
                    for item in evidence:
                        amount = item.get("montant")
                        formatted = f"{float(amount):,.2f}".replace(",", " ")
                        st.markdown(
                            f"✅ **{formatted} MAD** — "
                            f"{item.get('description') or 'Opération créditrice'}"
                        )
                    for item in excluded:
                        amount = item.get("montant")
                        formatted = f"{float(amount):,.2f}".replace(",", " ")
                        st.markdown(
                            f"❌ **{formatted} MAD** — "
                            f"{item.get('description') or 'Opération exclue'}  \n"
                            f"Motif : {item.get('reason') or 'opération non éligible'}"
                        )

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

        # Les widgets placés dans un formulaire ne déclenchent pas de rerun.
        # Le relevé utilise un conteneur normal pour recalculer le revenu dès
        # qu'une opération est cochée ou décochée. Les autres documents
        # conservent leur formulaire et leur comportement actuel.
        review_panel = (
            st.container(border=True)
            if document_type == "releve"
            else st.form(f"document_review_form_{document_id}", border=True)
        )
        with review_panel:
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

            if document_type == "releve":
                submitted = st.button(
                    submit_label,
                    type="primary",
                    width="stretch",
                    key=f"document_review_submit_{document_id}",
                )
            else:
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

            if name in credit_selections:
                selected_source = dict(record.get("source") or {})
                selected_source["human_credit_selection"] = credit_selections[name]
                selected_source["selection_method"] = (
                    "sélection humaine des lignes de la colonne CREDIT"
                )
                record["source"] = selected_source

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

