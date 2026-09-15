"""Tableau de bord de suivi des dossiers par le conseiller."""

import hmac
import os
from datetime import datetime

import streamlit as st
from ui.document_preview import render_document_preview
from database.customer_accounts import (
    list_customer_dossiers,
    load_advisor_review,
    load_documents,
    load_project,
    save_advisor_review,
)
from ui.client_summary import build_client_summary


REQUIRED_DOCUMENTS = {
    "carte_identite",
    "bulletin",
    "releve",
}

DOCUMENT_LABELS = {
    "carte_identite": "Carte d'identité",
    "bulletin": "Bulletin de paie",
    "releve": "Relevé bancaire",
    "compromis": "Compromis de vente",
}

STATUS_LABELS = {
    "en_cours": "En cours",
    "verifie": "Dossier vérifié",
    "correction_demandee": "Correction demandée",
}


def _format_date(value):
    """Afficher proprement une date ISO."""

    if not value:
        return "—"

    try:
        parsed = datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        )

        return parsed.strftime("%d/%m/%Y à %H:%M")
    except ValueError:
        return str(value)


def _document_needs_review(document):
    """Déterminer si le pipeline IA a signalé le document."""

    validation = (
        (document.get("result") or {})
        .get("validation_result")
        or {}
    )

    return bool(
        validation.get("needs_priority_review")
    )


def _document_alerts(document):
    """Extraire les alertes par champ."""

    validation = (
        (document.get("result") or {})
        .get("validation_result")
        or {}
    )

    alerts = []

    for field_name, decision in (
        validation.get("fields") or {}
    ).items():
        if decision.get("status") != "signale":
            continue

        reasons = decision.get("reasons") or [
            "Vérification humaine nécessaire"
        ]

        alerts.append({
            "Champ": field_name,
            "Raison": " ; ".join(reasons),
        })

    return alerts


def _build_dossier(customer):
    """Construire la synthèse d'un dossier client."""

    customer_id = customer["id"]
    documents = load_documents(customer_id)
    project = load_project(customer_id)
    advisor_review = load_advisor_review(customer_id)

    completed_types = {
        document.get("type")
        for document in documents.values()
        if document.get("status") == "completed"
    }

    reviewed_types = {
        document.get("type")
        for document in documents.values()
        if document.get("status") == "completed"
        and document.get("journey_reviewed") is True
    }

    required_uploaded = (
        REQUIRED_DOCUMENTS.issubset(completed_types)
    )

    required_reviewed = (
        REQUIRED_DOCUMENTS.issubset(reviewed_types)
    )

    summary_rows, information_complete = (
        build_client_summary(documents)
    )

    priority_alerts = sum(
        1
        for document in documents.values()
        if _document_needs_review(document)
    )

    progress_points = 0

    if project:
        progress_points += 1

    for document_type in REQUIRED_DOCUMENTS:
        if document_type in completed_types:
            progress_points += 1

    if information_complete:
        progress_points += 1

    progress = int(progress_points / 5 * 100)

    saved_status = (
        advisor_review.get("status")
        if advisor_review
        else None
    )

    if saved_status == "verifie":
        status = "Dossier vérifié"

    elif saved_status == "correction_demandee":
        status = "Correction demandée"

    elif information_complete and required_reviewed:
        status = "Prêt à étudier"

    elif required_uploaded:
        status = "À vérifier"

    else:
        status = "Incomplet"

    return {
        **customer,
        "documents": documents,
        "project": project,
        "summary_rows": summary_rows,
        "information_complete": information_complete,
        "required_uploaded": required_uploaded,
        "required_reviewed": required_reviewed,
        "priority_alerts": priority_alerts,
        "progress": progress,
        "status": status,
        "advisor_review": advisor_review,
    }


def _advisor_credentials():
    """Lire les accès depuis les variables d'environnement."""

    username = os.getenv(
        "ADVISOR_USERNAME",
        "conseiller",
    )

    access_code = os.getenv(
        "ADVISOR_ACCESS_CODE"
    )

    return username, access_code


def render_advisor_login():
    """Afficher la connexion conseiller."""

    st.title("Espace conseiller")

    st.caption(
        "Accès réservé au suivi et à la vérification "
        "des dossiers de crédit habitat."
    )

    expected_username, expected_code = (
        _advisor_credentials()
    )

    if not expected_code:
        st.error(
            "Le code d'accès conseiller n'est pas configuré."
        )

        st.code(
            '$env:ADVISOR_USERNAME="conseiller"\n'
            '$env:ADVISOR_ACCESS_CODE="VotreCodeSecurise"\n'
            "streamlit run app.py",
            language="powershell",
        )

        return False

    with st.form(
        "advisor_login_form",
        border=True,
    ):
        username = st.text_input(
            "Identifiant conseiller"
        )

        access_code = st.text_input(
            "Code d'accès",
            type="password",
        )

        submitted = st.form_submit_button(
            "Accéder au tableau de bord",
            type="primary",
            width="stretch",
        )

    if submitted:
        valid_username = hmac.compare_digest(
            username.strip(),
            expected_username,
        )

        valid_code = hmac.compare_digest(
            access_code,
            expected_code,
        )

        if valid_username and valid_code:
            st.session_state.advisor_authenticated = True
            st.session_state.advisor_username = username.strip()
            st.rerun()

        else:
            st.error(
                "Identifiant ou code d'accès incorrect."
            )

    return False


def render_advisor_sidebar():
    """Afficher la navigation dédiée au conseiller."""

    st.markdown("## Espace conseiller")
    st.caption("Suivi des dossiers Crédit Habitat")

    if st.session_state.get(
        "advisor_authenticated",
        False,
    ):
        st.success(
            st.session_state.get(
                "advisor_username",
                "Conseiller",
            )
        )

        if st.button(
            "Tableau de bord",
            icon=":material/dashboard:",
            type="primary",
            width="stretch",
            key="advisor_dashboard_home",
        ):
            st.session_state.page = "Conseiller"
            st.rerun()

        if st.button(
            "Se déconnecter",
            icon=":material/logout:",
            width="stretch",
            key="advisor_logout",
        ):
            st.session_state.advisor_authenticated = False
            st.session_state.advisor_username = None
            st.session_state.page = "Accueil"
            st.rerun()

    if st.button(
        "Retour à l'espace client",
        icon=":material/arrow_back:",
        width="stretch",
        key="advisor_back_to_client",
    ):
        st.session_state.page = "Accueil"
        st.rerun()


def render_dossier_details(dossier):
    """Afficher la fiche détaillée d'un client."""

    customer_name = (
        f"{dossier['first_name']} "
        f"{dossier['last_name']}"
    ).strip()

    st.divider()
    st.subheader(customer_name)

    identity_column, contact_column = st.columns(2)

    with identity_column:
        st.write(f"**E-mail :** {dossier['email']}")
        st.write(f"**Téléphone :** {dossier['phone']}")

    with contact_column:
        st.write(
            "**Compte créé :** "
            f"{_format_date(dossier['created_at'])}"
        )

        st.write(
            "**Dernière connexion :** "
            f"{_format_date(dossier['last_login_at'])}"
        )

    # -----------------------------------------------------
    # PROJET IMMOBILIER
    # -----------------------------------------------------

    st.markdown("#### Projet immobilier")

    project = dossier.get("project")

    if project:
        project_columns = st.columns(3)

        project_columns[0].metric(
            "Prix du bien",
            (
                f"{float(project.get('purchase_price') or 0):,.2f} "
                "MAD"
            ),
        )

        project_columns[1].metric(
            "Apport",
            (
                f"{float(project.get('contribution') or 0):,.2f} "
                "MAD"
            ),
        )

        project_columns[2].metric(
            "Durée",
            f"{int(project.get('duration_years') or 0)} ans",
        )

        if project.get("city"):
            st.write(
                f"**Ville :** {project['city']}"
            )

        if project.get("property_type"):
            st.write(
                "**Type de bien :** "
                f"{project['property_type']}"
            )

    else:
        st.warning(
            "Le client n'a pas encore renseigné son projet."
        )

    # -----------------------------------------------------
    # DOCUMENTS
    # -----------------------------------------------------

    st.markdown("#### Documents")

    document_rows = []

    for document in dossier["documents"].values():
        document_rows.append({
            "Type": DOCUMENT_LABELS.get(
                document.get("type"),
                document.get("type"),
            ),
            "Fichier": document.get("filename"),
            "Traitement": document.get("status"),
            "Vérifié par le client": (
                "Oui"
                if document.get("journey_reviewed")
                else "Non"
            ),
            "Alerte IA": (
                "Oui"
                if _document_needs_review(document)
                else "Non"
            ),
        })

    if document_rows:
        st.dataframe(
            document_rows,
            hide_index=True,
            width="stretch",
        )

    # -----------------------------------------------------
    # CONSULTATION DU DOCUMENT ORIGINAL
    # -----------------------------------------------------

        viewable_documents = {
            document_id: document
            for document_id, document
            in dossier["documents"].items()
            if document.get("document_path")
    }

        if viewable_documents:
            st.markdown("#### Consulter un justificatif")

            selected_document_id = st.selectbox(
                "Document à afficher",
                options=list(viewable_documents),
                format_func=lambda document_id: (
                    DOCUMENT_LABELS.get(
                        viewable_documents[document_id].get("type"),
                        viewable_documents[document_id].get(
                            "type",
                            "Document",
                    ),
                )
                    + " — "
                    + viewable_documents[document_id].get(
                        "filename",
                        "Document",
                )
            ),
                key=f"advisor_document_{dossier['id']}",
        )

            selected_document = viewable_documents[
                selected_document_id
        ]

            preview_column, information_column = st.columns(
                [1.4, 0.6],
                gap="large",
        )

            with preview_column:
                render_document_preview(
                    document_path=selected_document.get(
                        "document_path"
                ),
                    document_id=selected_document_id,
                    preferred_page=None,
            )

            with information_column:
                st.markdown("##### Informations du document")

                st.write(
                    "**Type :** "
                    + DOCUMENT_LABELS.get(
                        selected_document.get("type"),
                        selected_document.get(
                            "type",
                            "Document",
                    ),
                )
            )

                st.write(
                    "**Nom du fichier :** "
                    + selected_document.get(
                        "filename",
                        "Document",
                )
            )

                st.write(
                "**Date de dépôt :** "
                + _format_date(
                    selected_document.get("timestamp")
                )
            )

                st.write(
                    "**Traitement :** "
                    + selected_document.get(
                        "status",
                        "Inconnu",
                )
            )

                client_reviewed = (
                    selected_document.get(
                        "journey_reviewed"
                )
                    is True
            )

                st.write(
                    "**Vérifié par le client :** "
                    + ("Oui" if client_reviewed else "Non")
            )

                needs_review = _document_needs_review(
                    selected_document
            )

                if needs_review:
                    st.warning(
                        "Ce document contient des éléments "
                        "nécessitant une vérification humaine."
                )
                else:
                    st.success(
                        "Aucune alerte prioritaire sur ce document."
                )

        else:
            st.info(
            "Aucun document n'a encore été déposé."
    )

    # -----------------------------------------------------
    # INFORMATIONS CONFIRMÉES
    # -----------------------------------------------------

    st.markdown("#### Informations confirmées")

    confirmed_rows = [
    {
        "Information": str(row["Champ"]),
        "Valeur": (
            "—"
            if row["Valeur confirmée"] is None
            else str(row["Valeur confirmée"])
        ),
        "Statut": str(row["Statut"]),
        "Document": str(
            row["Pièce originale"] or "—"
        ),
        "Page": (
            "—"
            if row["Page"] is None
            else str(row["Page"])
        ),
    }
    for row in dossier["summary_rows"]
    ]

    st.dataframe(
        confirmed_rows,
        hide_index=True,
        width="stretch",
    )

    # -----------------------------------------------------
    # ALERTES IA
    # -----------------------------------------------------

    all_alerts = []

    for document in dossier["documents"].values():
        filename = document.get(
            "filename",
            "Document",
        )

        for alert in _document_alerts(document):
            all_alerts.append({
                "Document": filename,
                **alert,
            })

    with st.expander(
        f"Alertes nécessitant une vérification "
        f"({len(all_alerts)})",
        expanded=bool(all_alerts),
    ):
        if all_alerts:
            st.dataframe(
                all_alerts,
                hide_index=True,
                width="stretch",
            )
        else:
            st.success(
                "Aucune alerte prioritaire détectée."
            )

    # -----------------------------------------------------
    # DÉCISION DU CONSEILLER
    # -----------------------------------------------------

    st.markdown("#### Décision du conseiller")

    current_review = (
        dossier.get("advisor_review")
        or {}
    )

    status_options = list(STATUS_LABELS)

    current_status = current_review.get(
        "status",
        "en_cours",
    )

    current_index = (
        status_options.index(current_status)
        if current_status in status_options
        else 0
    )

    with st.form(
        f"advisor_review_{dossier['id']}",
        border=True,
    ):
        selected_status = st.selectbox(
            "Statut du dossier",
            options=status_options,
            index=current_index,
            format_func=lambda value: (
                STATUS_LABELS[value]
            ),
        )

        comment = st.text_area(
            "Commentaire",
            value=current_review.get(
                "comment",
                "",
            ),
            placeholder=(
                "Expliquez les vérifications effectuées "
                "ou les corrections demandées."
            ),
        )

        submitted = st.form_submit_button(
            "Enregistrer la décision",
            type="primary",
            width="stretch",
        )

    if submitted:
        save_advisor_review(
            customer_id=dossier["id"],
            status=selected_status,
            comment=comment,
            advisor_id=st.session_state.get(
                "advisor_username",
                "conseiller",
            ),
        )

        st.toast(
            "Décision enregistrée.",
            icon=":material/check_circle:",
        )

        st.rerun()


def render_advisor_dashboard():
    """Afficher le tableau de bord complet."""

    if not st.session_state.get(
        "advisor_authenticated",
        False,
    ):
        render_advisor_login()
        return

    st.title("Tableau de bord conseiller")

    st.caption(
        "Suivez les dossiers clients et concentrez-vous "
        "sur ceux qui nécessitent une vérification."
    )

    customers = list_customer_dossiers()

    dossiers = [
        _build_dossier(customer)
        for customer in customers
    ]

    total = len(dossiers)

    incomplete = sum(
        dossier["status"] == "Incomplet"
        for dossier in dossiers
    )

    to_review = sum(
        dossier["status"] in {
            "À vérifier",
            "Prêt à étudier",
        }
        for dossier in dossiers
    )

    verified = sum(
        dossier["status"] == "Dossier vérifié"
        for dossier in dossiers
    )

    metric_columns = st.columns(4)

    metric_columns[0].metric(
        "Dossiers",
        total,
        border=True,
    )

    metric_columns[1].metric(
        "Incomplets",
        incomplete,
        border=True,
    )

    metric_columns[2].metric(
        "À traiter",
        to_review,
        border=True,
    )

    metric_columns[3].metric(
        "Vérifiés",
        verified,
        border=True,
    )

    if not dossiers:
        st.info(
            "Aucun dossier client n'est encore disponible."
        )
        return

    # -----------------------------------------------------
    # FILTRES
    # -----------------------------------------------------

    filter_column, search_column = st.columns(2)

    with filter_column:
        selected_status = st.selectbox(
            "Filtrer par statut",
            options=[
                "Tous",
                "Incomplet",
                "À vérifier",
                "Prêt à étudier",
                "Correction demandée",
                "Dossier vérifié",
            ],
        )

    with search_column:
        search = st.text_input(
            "Rechercher un client",
            placeholder="Nom ou adresse e-mail",
        ).strip().casefold()

    filtered = []

    for dossier in dossiers:
        full_name = (
            f"{dossier['first_name']} "
            f"{dossier['last_name']}"
        ).casefold()

        matches_status = (
            selected_status == "Tous"
            or dossier["status"] == selected_status
        )

        matches_search = (
            not search
            or search in full_name
            or search in dossier["email"].casefold()
        )

        if matches_status and matches_search:
            filtered.append(dossier)

    table_rows = [
        {
            "Client": (
                f"{dossier['first_name']} "
                f"{dossier['last_name']}"
            ),
            "Progression": f"{dossier['progress']} %",
            "Documents": len(dossier["documents"]),
            "Alertes IA": dossier["priority_alerts"],
            "Statut": dossier["status"],
            "Dernière connexion": _format_date(
                dossier["last_login_at"]
            ),
        }
        for dossier in filtered
    ]

    if table_rows:
        st.dataframe(
            table_rows,
            hide_index=True,
            width="stretch",
        )
    else:
        st.warning(
            "Aucun dossier ne correspond aux filtres."
        )
        return

    selected_customer_id = st.selectbox(
        "Consulter un dossier",
        options=[
            dossier["id"]
            for dossier in filtered
        ],
        format_func=lambda customer_id: next(
            (
                f"{dossier['first_name']} "
                f"{dossier['last_name']} — "
                f"{dossier['status']}"
            )
            for dossier in filtered
            if dossier["id"] == customer_id
        ),
    )

    selected_dossier = next(
        dossier
        for dossier in filtered
        if dossier["id"] == selected_customer_id
    )

    render_dossier_details(
        selected_dossier
    )