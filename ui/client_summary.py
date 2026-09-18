"""Synthèse EB-105 : uniquement les cinq champs métier confirmés."""
import csv
import io
import re
import statistics
from datetime import datetime

import streamlit as st

from database import audit
from database.customer_accounts import save_document, save_project
from extraction.confirmation import make_confirmation
from extraction.financial_metrics import debt_ratio


BUSINESS_FIELDS = {
    "employeur": {"label": "Nom employeur", "type": "Texte", "document": "bulletin", "required": True},
    "salaire_net": {"label": "Revenu mensuel net", "type": "Nombre (MAD)", "document": "bulletin", "required": True},
    "date_embauche": {"label": "Date d'embauche", "type": "Date", "document": "bulletin", "required": True},
    "charge_mensuelle_credits": {"label": "Charges mensuelles de crédits", "type": "Nombre (MAD)", "document": "releve", "required": True},
    "revenus_complementaires": {"label": "Revenus complémentaires", "type": "Nombre (MAD)", "document": "releve", "required": True},
}

FINANCIAL_STATEMENT_FIELDS = {
    "charge_mensuelle_credits",
    "revenus_complementaires",
}
DOSSIER_FIELD_KEYS = {
    field: f"dossier_{field}"
    for field in FINANCIAL_STATEMENT_FIELDS
}


def _aggregate_financial_values(field, values):
    """Agrégation prudente de 1 à 3 mois confirmés par le client."""
    numeric = [float(value) for value in values]
    if not numeric:
        return None, "Aucune valeur confirmée"
    if field == "revenus_complementaires":
        # Avec deux mois, retenir la valeur basse empêche qu'un virement
        # exceptionnel sur un seul relevé soit considéré comme régulier.
        aggregate = statistics.median_low(numeric)
    else:
        # Pour les charges, retenir la valeur haute à deux mois est plus
        # prudent et évite de sous-estimer un crédit existant.
        aggregate = statistics.median_high(numeric)

    if len(numeric) == 1:
        regularity = "Estimation sur 1 relevé"
    elif max(numeric) == min(numeric):
        regularity = f"Stable sur {len(numeric)} relevés"
    else:
        denominator = max(abs(aggregate), 1.0)
        variation = (max(numeric) - min(numeric)) / denominator
        regularity = (
            f"Régulier sur {len(numeric)} relevés"
            if variation <= 0.20
            else f"Variable sur {len(numeric)} relevés — à confirmer"
        )
    return round(float(aggregate), 2), regularity


def _valid_dossier_override(documents, field, source_ids):
    key = DOSSIER_FIELD_KEYS[field]
    overrides = []
    for document_id, document in documents.items():
        record = (document.get("confirmed_fields") or {}).get(key)
        if not _valid_confirmation(record, document_id):
            continue
        aggregation = record.get("aggregation") or {}
        if set(aggregation.get("source_document_ids") or []) == set(source_ids):
            overrides.append((document_id, document, record))
    return max(
        overrides,
        key=lambda item: item[2].get("confirmed_at") or "",
    ) if overrides else None


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
        if field in FINANCIAL_STATEMENT_FIELDS and candidates:
            source_ids = [item[0] for item in candidates]
            override = _valid_dossier_override(documents, field, source_ids)
            if override:
                _, document, record = override
                value = record["value"]
                aggregation = record.get("aggregation") or {}
                regularity = aggregation.get("regularity") or "Confirmé par le client"
                source = record.get("source") or {}
            else:
                value, regularity = _aggregate_financial_values(
                    field, [item[2]["value"] for item in candidates]
                )
                _, document, record = candidates[0]
                source = record.get("source") or {}
            status = "Confirmé"
            document_name = ", ".join(
                dict.fromkeys(item[1].get("filename") or "Relevé" for item in candidates)
            )
            conflict = False
            selected = None
        else:
            regularity = None
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
            "Régularité": regularity,
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

    if field in FINANCIAL_STATEMENT_FIELDS and confirmed:
        value, regularity = _aggregate_financial_values(
            field, [item[2]["value"] for item in confirmed]
        )
        selected = confirmed[0]
        document_id, document, record, decision = selected
        source_ids = [item[0] for item in confirmed]
        sources = ", ".join(
            dict.fromkeys(item[1].get("filename") or "Relevé" for item in confirmed)
        )
        return {
            "field": field,
            "value": str(value),
            "status": regularity,
            "source": sources,
            "target": (document_id, document),
            "decision": {
                "value": value,
                "source": record.get("source") or (decision or {}).get("source"),
            },
            "aggregation": {
                "method": (
                    "median_low"
                    if field == "revenus_complementaires"
                    else "median_high"
                ),
                "source_document_ids": source_ids,
                "source_values": [float(item[2]["value"]) for item in confirmed],
                "regularity": regularity,
            },
        }

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


def _confirmed_document_value(documents, document_type, field):
    """Retourne la dernière valeur explicitement confirmée pour une pièce."""
    candidates = []
    for document_id, document in documents.items():
        if document.get("type") != document_type:
            continue
        record = (document.get("confirmed_fields") or {}).get(field)
        if _valid_final_confirmation(record, document_id):
            candidates.append((record.get("confirmed_at") or "", record.get("value")))
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0])[1]


def render_final_verification(
    documents, customer_id, advisor_id, session_id, project=None,
):
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
    project = project or {}
    compromise_price = _confirmed_document_value(documents, "compromis", "prix_vente")
    initial_price = float(compromise_price or project.get("purchase_price") or 0)
    initial_contribution = float(project.get("contribution") or 0)
    values = {}
    with st.form(f"five_fields_verification_{customer_id}", border=True):
        st.caption("Ces valeurs reprennent vos corrections. En continuant, vous confirmez ce récapitulatif.")
        for field in FIELD_ORDER:
            if field in FINANCIAL_STATEMENT_FIELDS:
                st.caption(
                    f"{BUSINESS_FIELDS[field]['label']} — "
                    f"{proposals[field]['status']}"
                )
            values[field] = st.text_input(
                BUSINESS_FIELDS[field]["label"], value=proposals[field]["value"],
                key=f"final_{customer_id}_{field}_" + str(proposals[field]["value"]),
                help="JJ/MM/AAAA ou AAAA-MM-JJ" if field == "date_embauche" else None,
            )
        st.markdown("#### Mon financement")
        if compromise_price is not None:
            st.caption(
                "Le prix du bien provient du compromis que vous avez vérifié. "
                "Vous pouvez encore le corriger avant la simulation."
            )
        project_left, project_right = st.columns(2)
        purchase_price = project_left.number_input(
            "Prix du bien (MAD)", min_value=0.0, value=initial_price,
            step=10000.0, key=f"final_{customer_id}_purchase_price",
        )
        contribution = project_right.number_input(
            "Apport personnel (MAD)", min_value=0.0,
            value=initial_contribution, step=5000.0,
            key=f"final_{customer_id}_contribution",
        )
        financing_need = max(purchase_price - contribution, 0.0)
        st.info(f"Montant à financer estimé : {financing_need:,.0f} MAD")
        submitted = st.form_submit_button("Voir ma simulation", type="primary", width="stretch")
    if not submitted:
        return False

    prepared = {}
    errors = []
    if purchase_price <= 0:
        errors.append("Prix du bien : renseignez un montant supérieur à 0")
    if contribution > purchase_price:
        errors.append("Apport personnel : il ne peut pas dépasser le prix du bien")
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
            if field in FINANCIAL_STATEMENT_FIELDS:
                confirmation["aggregation"] = proposal.get("aggregation") or {
                    "method": "confirmation_client",
                    "source_document_ids": [document_id],
                    "source_values": [float(confirmation["value"])],
                    "regularity": "Confirmé par le client",
                }
            prepared[field] = (document_id, document, confirmation)
        except (TypeError, ValueError) as exc:
            errors.append(f"{BUSINESS_FIELDS[field]['label']} : {exc}")

    if errors:
        for error in errors:
            st.error(error)
        return False

    try:
        for field, (selected_id, selected_document, confirmation) in prepared.items():
            audit.log_human_confirmation(
                document_path=selected_document.get("document_path") or selected_id,
                document_type=selected_document.get("type"), field_name=field,
                confirmed_value=confirmation["value"], advisor_id=advisor_id,
                session_id=session_id, original_value=confirmation["original_value"],
                source=confirmation.get("source") or {}, confirmation_status=confirmation["status"],
            )
    except Exception:
        st.error("La validation n'a pas pu être enregistrée. Réessayez pour accéder à la simulation.")
        return False
    from copy import deepcopy
    updated = deepcopy(documents)
    modified = set()
    for field, (selected_id, _, confirmation) in prepared.items():
        if field in FINANCIAL_STATEMENT_FIELDS:
            dossier_key = DOSSIER_FIELD_KEYS[field]
            for document_id, document in updated.items():
                if dossier_key in (document.get("confirmed_fields") or {}):
                    document["confirmed_fields"].pop(dossier_key)
                    modified.add(document_id)
            updated[selected_id].setdefault("confirmed_fields", {})[
                dossier_key
            ] = confirmation
            modified.add(selected_id)
            continue
        for document_id, document in updated.items():
            if document_id != selected_id and field in (document.get("confirmed_fields") or {}):
                document["confirmed_fields"].pop(field)
                modified.add(document_id)
        updated[selected_id].setdefault("confirmed_fields", {})[field] = confirmation
        modified.add(selected_id)
    try:
        for document_id in modified:
            save_document(customer_id, document_id, updated[document_id])
        save_project(
            customer_id,
            project.get("city") or "",
            project.get("property_type") or "",
            purchase_price,
            contribution,
            int(project.get("duration_years") or 20),
        )
    except Exception:
        st.error("La sauvegarde a échoué. Réessayez avant de poursuivre.")
        return False
    for document_id in modified:
        documents[document_id].update(updated[document_id])

    st.toast("Vos informations sont vérifiées. Simulation débloquée.", icon=":material/check_circle:")
    st.session_state.page = "Simulation"
    st.rerun()
    return True
