"""Synthèse EB-105 : uniquement les cinq champs métier confirmés."""
import csv
import io

import streamlit as st

from extraction.financial_metrics import debt_ratio


BUSINESS_FIELDS = {
    "employeur": {"label": "Nom employeur", "type": "Texte", "document": "bulletin", "required": True},
    "salaire_net": {"label": "Revenu mensuel net", "type": "Nombre (MAD)", "document": "bulletin", "required": True},
    "date_embauche": {"label": "Date d'embauche", "type": "Date", "document": "bulletin", "required": True},
    "charge_mensuelle_credits": {"label": "Charges mensuelles de crédits", "type": "Nombre (MAD)", "document": "releve", "required": True},
    "revenus_complementaires": {"label": "Revenus complémentaires", "type": "Nombre (MAD)", "document": "releve", "required": False},
}


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
        unique = {repr(item[2]["value"]) for item in candidates}
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
    st.subheader("Synthèse du dossier client")
    st.caption("Seules les valeurs confirmées par un conseiller sont reprises. Aucun calcul d'endettement n'est effectué ici.")
    values = {row["field"]: row["Valeur confirmée"] for row in rows if row["Statut"] == "Confirmé"}
    if "salaire_net" in values and "charge_mensuelle_credits" in values:
        ratio = debt_ratio(values["salaire_net"], values["charge_mensuelle_credits"])
        cols = st.columns(3)
        cols[0].metric("Revenu net confirmé", f"{float(values['salaire_net']):,.2f} MAD", border=True)
        cols[1].metric("Charges confirmées", f"{float(values['charge_mensuelle_credits']):,.2f} MAD", border=True)
        cols[2].metric("Taux d'endettement", f"{ratio:.2%}", border=True)
        st.caption("Calcul : charges mensuelles confirmées ÷ revenu mensuel net confirmé. Revenus complémentaires exclus.")
    else:
        st.info("Le taux d'endettement sera calculé après confirmation du revenu net et des charges mensuelles.")
    if complete:
        st.success("Les quatre champs obligatoires sont confirmés.")
    else:
        st.warning("Dossier incomplet ou contradictoire : confirmez les champs obligatoires et résolvez les conflits.")
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
        "Exporter la synthèse confirmée", _csv(rows),
        file_name="synthese_dossier_confirmee.csv", mime="text/csv",
        key="export_client_summary", on_click="ignore",
    )
