"""Synthèse EB-105 : uniquement les cinq champs métier confirmés."""
import csv
import io
import re
from datetime import datetime

import streamlit as st

from database import audit
from database.customer_accounts import save_document
from extraction.confirmation import make_confirmation
from extraction.financial_metrics import debt_ratio


BUSINESS_FIELDS = {
    "employeur": {"label": "Nom employeur", "type": "Texte", "document": "bulletin", "required": True},
    "salaire_net": {"label": "Revenu mensuel net", "type": "Nombre (MAD)", "document": "bulletin", "required": True},
    "date_embauche": {"label": "Date d'embauche", "type": "Date", "document": "bulletin", "required": True},
    "charge_mensuelle_credits": {"label": "Charges mensuelles de crédits", "type": "Nombre (MAD)", "document": "releve", "required": True},
    "revenus_complementaires": {"label": "Revenus complémentaires", "type": "Nombre (MAD)", "document": "releve", "required": True},
}


def _canonical_value(value, expected_type):
    """Évite les faux conflits dus uniquement au format d'une même valeur."""
    if value is None:
        return None
    if expected_type.startswith("Nombre"):
        text = re.sub(r"\s+", "", str(value)).replace(",", ".")
        try:
            return ("number", round(float(text), 2))
        except ValueError:
            return ("text", text.casefold())
    if expected_type == "Date":
        text = str(value).strip()
        for pattern in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
            try:
                return ("date", datetime.strptime(text, pattern).date().isoformat())
            except ValueError:
                continue
        return ("text", re.sub(r"\s+", " ", text).casefold())
    return ("text", re.sub(r"\s+", " ", str(value)).strip().casefold())


def _valid_confirmation(record, document_id):
    return (
        isinstance(record, dict)
        and record.get("document_id") == document_id
        and record.get("status") in ("confirme", "corrige")
        and record.get("source_checked") is True
        and record.get("advisor_id")
        and record.get("confirmed_at")
        and record.get("value") is not None
    )


def build_client_summary(documents):
    """Ne choisit pas silencieusement entre deux confirmations différentes."""
    rows = []
    complete = True
    for field, spec in BUSINESS_FIELDS.items():
        candidates = []
        for document_id, document in documents.items():
            if document.get("type") != spec["document"]:
                continue
            record = (document.get("confirmed_fields") or {}).get(field)
            if _valid_confirmation(record, document_id):
                candidates.append((document_id, document, record))
        unique = {
            _canonical_value(item[2]["value"], spec["type"])
            for item in candidates
        }
        conflict = len(unique) > 1
        selected = max(candidates, key=lambda item: item[2]["confirmed_at"]) if candidates and not conflict else None
        if conflict:
            status, value, document_name, source = "Conflit", None, None, {}
        elif selected:
            _, document, record = selected
            status, value = "Confirmé", record["value"]
            document_name = document.get("filename")
            source = record.get("source") or {}
        else:
            status, value, document_name, source = ("Manquant" if spec["required"] else "Optionnel absent"), None, None, {}
        if spec["required"] and status != "Confirmé":
            complete = False
        rows.append({
            "field": field, "Champ": spec["label"], "Type attendu": spec["type"],
            "Valeur confirmée": value, "Statut": status,
            "Pièce originale": document_name, "Page": source.get("page"),
            "Extrait": source.get("quote"), "SHA-256": source.get("sha256"),
        })
    return rows, complete


def _csv(rows):
    buffer = io.StringIO(newline="")
    public_rows = [{key: value for key, value in row.items() if key != "field"} for row in rows]
    writer = csv.DictWriter(buffer, fieldnames=list(public_rows[0]))
    writer.writeheader()
    writer.writerows(public_rows)
    return buffer.getvalue().encode("utf-8-sig")


def render_client_summary(documents):
    rows, complete = build_client_summary(documents)
    st.subheader("Ma situation financière")
    st.caption("Cette synthèse utilise uniquement les informations que vous avez vérifiées.")
    values = {row["field"]: row["Valeur confirmée"] for row in rows if row["Statut"] == "Confirmé"}
    if all(field in values for field in ("salaire_net", "revenus_complementaires", "charge_mensuelle_credits")):
        total_income = float(values["salaire_net"]) + float(values["revenus_complementaires"])
        ratio = debt_ratio(total_income, values["charge_mensuelle_credits"])
        cols = st.columns(3)
        cols[0].metric("Mes revenus retenus", f"{total_income:,.2f} MAD", border=True)
        cols[1].metric("Mes charges de crédits", f"{float(values['charge_mensuelle_credits']):,.2f} MAD", border=True)
        cols[2].metric("Taux d'endettement", f"{ratio:.2%}", border=True)
        st.caption("Calcul indicatif : charges mensuelles ÷ (revenu net + revenus complémentaires vérifiés).")
    else:
        st.info("Vérifiez votre revenu net et vos charges mensuelles pour afficher le taux d'endettement.")
    if complete:
        st.success("Les informations indispensables à la simulation sont vérifiées.")
    else:
        st.warning("Certaines informations doivent encore être vérifiées ou corrigées.")
    display_rows = []
    for row in rows:
        display = {key: value for key, value in row.items() if key not in ("field", "SHA-256")}
        display["Valeur confirmée"] = "" if row["Valeur confirmée"] is None else str(row["Valeur confirmée"])
        display_rows.append(display)
    st.dataframe(
        display_rows,
        hide_index=True, width="stretch",
    )
    with st.expander("Traçabilité technique"):
        st.dataframe(
            [{"Champ": row["Champ"], "Pièce originale": row["Pièce originale"],
              "Page": row["Page"], "SHA-256": row["SHA-256"]} for row in rows],
            hide_index=True, width="stretch",
        )
    st.download_button(
        "Télécharger ma synthèse", _csv(rows),
        file_name="synthese_dossier_confirmee.csv", mime="text/csv",
        key="export_client_summary", on_click="ignore",
    )

FIELD_ORDER = tuple(BUSINESS_FIELDS)


def _valid_final_confirmation(record, document_id):
    return (
        isinstance(record, dict)
        and record.get("document_id") == document_id
        and record.get("status") in ("confirme", "corrige")
        and record.get("source_checked") is True
        and record.get("value") is not None
    )


def _document_decision(document, field):
    return (
        ((document.get("result") or {}).get("validation_result") or {})
        .get("fields", {})
        .get(field)
    )


def _field_proposal(documents, field, spec):
    matching = [
        (document_id, document)
        for document_id, document in documents.items()
        if document.get("type") == spec["document"]
        and document.get("status") == "completed"
    ]
    matching.sort(key=lambda item: item[1].get("timestamp") or "", reverse=True)
    if not matching:
        return {
            "field": field, "value": "", "status": "Document manquant",
            "source": "—", "target": None, "decision": None,
        }

    confirmed = []
    extracted = []
    for document_id, document in matching:
        record = (document.get("confirmed_fields") or {}).get(field)
        decision = _document_decision(document, field)
        if _valid_final_confirmation(record, document_id):
            confirmed.append((document_id, document, record, decision))
        if isinstance(decision, dict):
            extracted.append((document_id, document, decision))

    if confirmed:
        unique = {
            _canonical_value(item[2]["value"], spec["type"])
            for item in confirmed
        }
        selected = confirmed[0]
        document_id, document, record, decision = selected
        sources = ", ".join(dict.fromkeys(item[1].get("filename") or "Document" for item in confirmed))
        return {
            "field": field,
            "value": str(record["value"]),
            "status": "Conflit" if len(unique) > 1 else "Déjà confirmé",
            "source": sources,
            "target": (document_id, document),
            "decision": decision or {"value": record["value"], "source": record.get("source")},
        }

    usable = [item for item in extracted if item[2].get("value") is not None]
    selected = usable[0] if usable else (extracted[0] if extracted else None)
    if selected is None:
        document_id, document = matching[0]
        return {
            "field": field, "value": "", "status": "À compléter",
            "source": document.get("filename") or "Document",
            "target": (document_id, document),
            "decision": {"value": None, "source": None},
        }

    document_id, document, decision = selected
    unique = {
        _canonical_value(item[2]["value"], spec["type"])
        for item in usable
    }
    sources = ", ".join(dict.fromkeys(item[1].get("filename") or "Document" for item in usable))
    return {
        "field": field,
        "value": "" if decision.get("value") is None else str(decision["value"]),
        "status": "Conflit" if len(unique) > 1 else ("À vérifier" if usable else "À compléter"),
        "source": sources or (document.get("filename") or "Document"),
        "target": (document_id, document),
        "decision": decision,
    }


def render_final_verification(documents, customer_id, advisor_id, session_id):
    """Affiche un seul tableau, valide toutes les valeurs, puis ouvre la simulation."""
    proposals = {
        field: _field_proposal(documents, field, BUSINESS_FIELDS[field])
        for field in FIELD_ORDER
    }
    table_rows = [
        {
            "Information": BUSINESS_FIELDS[field]["label"],
            "Valeur": proposals[field]["value"],
            "Source": proposals[field]["source"],
            "État": proposals[field]["status"],
        }
        for field in FIELD_ORDER
    ]

    conflicts = [BUSINESS_FIELDS[field]["label"] for field in FIELD_ORDER
                 if proposals[field]["status"] == "Conflit"]
    if conflicts:
        st.warning(
            "Des justificatifs présentent des valeurs différentes pour : "
            + ", ".join(conflicts)
            + ". Corrigez la colonne « Valeur » après comparaison des pièces."
        )
    st.info(
        "Vérifiez les cinq lignes. Si vous n'avez ni crédit en cours ni revenu "
        "complémentaire, saisissez 0 dans la ligne correspondante."
    )

    with st.form(f"five_fields_verification_{customer_id}", border=True):
        edited = st.data_editor(
            table_rows,
            hide_index=True,
            width="stretch",
            num_rows="fixed",
            disabled=["Information", "Source", "État"],
            column_config={
                "Information": st.column_config.TextColumn("Information", pinned=True),
                "Valeur": st.column_config.TextColumn("Valeur à utiliser", required=True),
                "Source": st.column_config.TextColumn("Justificatif"),
                "État": st.column_config.TextColumn("Contrôle"),
            },
            key=f"verification_table_{customer_id}",
        )
        checked = st.checkbox(
            "J'ai vérifié ces cinq informations avec mes justificatifs",
            key=f"verification_checked_{customer_id}",
        )
        submitted = st.form_submit_button(
            "Vérifier et accéder à ma simulation",
            icon=":material/check_circle:",
            type="primary",
            width="stretch",
        )

    if not submitted:
        return False
    if not checked:
        st.error("Cochez la confirmation après avoir vérifié les cinq informations.")
        return False

    records = edited.to_dict("records") if hasattr(edited, "to_dict") else list(edited)
    values = {
        field: records[index].get("Valeur")
        for index, field in enumerate(FIELD_ORDER)
    }
    prepared = {}
    errors = []
    for field in FIELD_ORDER:
        proposal = proposals[field]
        if proposal["target"] is None:
            errors.append(f"{BUSINESS_FIELDS[field]['label']} : justificatif source manquant")
            continue
        if values[field] is None or not str(values[field]).strip():
            errors.append(f"{BUSINESS_FIELDS[field]['label']} : renseignez une valeur")
            continue
        document_id, document = proposal["target"]
        try:
            confirmation = make_confirmation(
                document.get("type"), field, values[field], proposal["decision"],
                document_id=document_id, advisor_id=advisor_id, source_checked=True,
            )
            if field == "salaire_net" and float(confirmation["value"]) <= 0:
                raise ValueError("le revenu mensuel net doit être supérieur à 0")
            prepared[field] = (document_id, document, confirmation)
        except (TypeError, ValueError) as exc:
            errors.append(f"{BUSINESS_FIELDS[field]['label']} : {exc}")

    if errors:
        for error in errors:
            st.error(error)
        return False

    modified = set()
    for field, (selected_id, selected_document, confirmation) in prepared.items():
        for document_id, document in documents.items():
            if document_id == selected_id:
                continue
            confirmations = document.get("confirmed_fields") or {}
            if field in confirmations:
                confirmations.pop(field, None)
                document["confirmed_fields"] = confirmations
                modified.add(document_id)
        selected_document.setdefault("confirmed_fields", {})[field] = confirmation
        modified.add(selected_id)
        source = confirmation.get("source") or {}
        audit.log_human_confirmation(
            document_path=selected_document.get("document_path") or selected_id,
            document_type=selected_document.get("type"),
            field_name=field,
            confirmed_value=confirmation["value"],
            advisor_id=advisor_id,
            session_id=session_id,
            original_value=confirmation["original_value"],
            source=source,
            confirmation_status=confirmation["status"],
        )

    for document_id in modified:
        save_document(customer_id, document_id, documents[document_id])

    st.toast("Vos informations sont vérifiées. Simulation débloquée.", icon=":material/check_circle:")
    st.session_state.page = "Simulation"
    st.rerun()
    return True
