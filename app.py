"""
Assistant IA — Crédit Habitat
Projet PFE Crédit Agricole du Maroc
===================================

Interface de démonstration permettant de tester :

1. Analyse documentaire
   Contrôle -> OCR -> Extraction -> Validation

2. Assistant IA
   Question -> Retrieval -> Contrôle du périmètre -> Réponse sourcée

Tous les appels passent par Orchestrator afin de conserver
un point d'entrée unique cohérent avec l'architecture du projet.
"""
import html
import logging
import uuid
from pathlib import Path
from datetime import datetime
from ui.advisor_dashboard import (
    render_advisor_dashboard,
    render_advisor_sidebar,
)
import streamlit as st
from dotenv import load_dotenv

load_dotenv()
from config.settings import settings
from database import audit
from database.customer_accounts import (
    authenticate, create_customer, delete_document,
    load_documents, load_project, save_document, save_project,
)
from ui.document_review import render_document_review
from ui.simulation import render_simulation
from ui.borrowing_capacity import render_borrowing_capacity
from copy import deepcopy
from ui.client_summary import (
    build_client_summary, render_final_verification,
)
from ui.session_state import initialize_session_state
from ui.home_components import image_to_data_url, render_home_assurance_strip
from ui.assistant_dock import render_assistant_dock
from utils.document_processing import (
    count_pdf_pages,
    process_document_with_progress,
    request_document_analysis,
    save_document_files,
    validate_file,
)

# =========================================================
# CONFIGURATION
# =========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

st.set_page_config(
    page_title="Crédit Habitat — Assistant IA",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# =========================================================
# DESIGN - STYLES AMÉLIORÉS
# =========================================================

from ui.app_styles import inject_app_styles


@st.dialog("Espace client", width="large")
def render_customer_access_dialog():
    """Regrouper la connexion et la création de compte hors de la page d'accueil."""
    login_tab, signup_tab = st.tabs(["Se connecter", "Créer un compte"])

    with login_tab:
        with st.form("customer_login_dialog", border=False):
            login_email = st.text_input(
                "Adresse e-mail",
                key="dialog_login_email",
            )
            login_password = st.text_input(
                "Mot de passe",
                type="password",
                key="dialog_login_password",
            )
            login_submit = st.form_submit_button(
                "Se connecter",
                type="primary",
                width="stretch",
            )
            if login_submit:
                customer = authenticate(login_email, login_password)
                if customer is None:
                    st.error("Adresse e-mail ou mot de passe incorrect.")
                else:
                    st.session_state.customer_profile = {
                        "prenom": customer["first_name"],
                        "nom": customer["last_name"],
                        "email": customer["email"],
                        "telephone": customer["phone"],
                    }
                    st.session_state.current_client_id = customer["id"]
                    st.session_state.documents = load_documents(customer["id"])
                    st.session_state.account_created = True
                    st.session_state.page = "Accueil"
                    st.rerun()

    with signup_tab:
        with st.form("customer_signup_dialog", border=False):
            left, right = st.columns(2)
            prenom = left.text_input("Prénom *", key="dialog_signup_first_name")
            nom = right.text_input("Nom *", key="dialog_signup_last_name")
            email = left.text_input("Adresse e-mail *", key="dialog_signup_email")
            telephone = right.text_input("Téléphone *", key="dialog_signup_phone")
            password = left.text_input(
                "Mot de passe *",
                type="password",
                key="dialog_signup_password",
            )
            confirmation = right.text_input(
                "Confirmer le mot de passe *",
                type="password",
                key="dialog_signup_password_confirmation",
            )
            consent = st.checkbox(
                "J'accepte que mes informations soient utilisées pour préparer cette simulation.",
                key="dialog_signup_consent",
            )
            submitted = st.form_submit_button(
                "Créer mon compte",
                type="primary",
                width="stretch",
            )
            if submitted:
                if password != confirmation:
                    st.error("Les deux mots de passe ne correspondent pas.")
                elif not consent:
                    st.error("Votre accord est nécessaire pour poursuivre.")
                else:
                    try:
                        customer = create_customer(
                            email,
                            password,
                            prenom,
                            nom,
                            telephone,
                        )
                    except ValueError as exc:
                        st.error(str(exc))
                    else:
                        st.session_state.customer_profile = {
                            "prenom": customer["first_name"],
                            "nom": customer["last_name"],
                            "email": customer["email"],
                            "telephone": customer["phone"],
                        }
                        st.session_state.current_client_id = customer["id"]
                        st.session_state.documents = load_documents(customer["id"])
                        st.session_state.account_created = True
                        st.session_state.page = "Accueil"
                        st.rerun()


def render_housing_project_step(project=None):
    """Afficher la description du projet comme première page du parcours."""
    project = project or {}
    property_options = [
        "Appartement",
        "Maison",
        "Terrain + construction",
        "Autre",
    ]
    saved_type = project.get("property_type") or property_options[0]
    saved_duration = int(project.get("duration_years") or 20)

    st.title("Décrire mon projet")
    st.caption("Étape 1 sur 4 · Ces informations seront reprises dans la simulation.")
    with st.container(border=True):
        st.markdown("### Mon projet immobilier")
        with st.form("housing_project_profile", border=False):
            left, right = st.columns(2)
            property_type = left.selectbox(
                "Type de bien *",
                property_options,
                index=(
                    property_options.index(saved_type)
                    if saved_type in property_options
                    else 0
                ),
            )
            city = right.text_input(
                "Ville du projet *",
                value=project.get("city") or "",
                placeholder="Ex. Rabat",
            )
            duration_years = st.slider(
                "Durée souhaitée du crédit",
                min_value=5,
                max_value=30,
                value=max(5, min(30, saved_duration)),
                format="%d ans",
                help="Cette durée sera utilisée pour calculer la mensualité.",
            )
            submitted = st.form_submit_button(
                "Enregistrer et continuer",
                type="primary",
                width="stretch",
            )

    if not submitted:
        return
    if not city.strip():
        st.error("Renseignez la ville du projet pour continuer.")
        return

    # Le prix vient ensuite du compromis et l'apport de la vérification.
    # Lors d'une modification, conserver les montants déjà confirmés.
    save_project(
        st.session_state.current_client_id,
        city.strip(),
        property_type,
        float(project.get("purchase_price") or 0),
        float(project.get("contribution") or 0),
        duration_years,
    )
    st.session_state.page = "Extraction"
    st.toast("Votre projet est enregistré.", icon=":material/check_circle:")
    st.rerun()


def render_header():
    """Afficher un en-tête inspiré de l'identité institutionnelle du GCAM."""
    page_labels = {
        "Accueil": "Mon projet habitat",
        "Projet": "Décrire mon projet",
        "Extraction": "Mes justificatifs",
        "Verification": "Vérification des informations",
        "Estimation": "Estimation rapide",
        "Simulation": "Ma simulation",
    }
    current_page = page_labels.get(st.session_state.page, "Crédit Habitat")
    logo_url = image_to_data_url("assets/logo_ca.jpg")
    st.markdown(
        """
        <header class="cam-site-header">
            <div class="cam-utility-bar">
                <span class="cam-corporate">Groupe Crédit Agricole du Maroc</span>
               
        </header>
        """,
        unsafe_allow_html=True,
    )

    if logo_url:
        st.markdown(
            f"""
            <style>
            .st-key-top_nav_logo button {{
                background-image: url("{logo_url}") !important;
                background-position: left .85rem center !important;
                background-size: 54px auto !important;
            }}
            </style>
            """,
            unsafe_allow_html=True,
        )

    account_ready = bool(st.session_state.account_created)
    profile = st.session_state.get("customer_profile", {})
    initials = "".join(
        str(value).strip()[:1].upper()
        for value in (profile.get("prenom"), profile.get("nom"))
        if value
    ) or "CL"
    documents = current_client_documents() if account_ready else {}
    required_types = {"carte_identite", "bulletin", "releve"}
    documents_ready = account_ready and required_types.issubset(
        reviewed_document_types(documents)
    )
    dossier_complete = False
    if account_ready:
        _, _, dossier_complete, _ = dossier_readiness()

    with st.container(key="cam_top_navigation"):
        (
            nav_logo,
            nav_project,
            nav_docs,
            nav_check,
            nav_sim,
            nav_estimate,
            nav_space,
        ) = st.columns(
            [1.55, .95, 1.05, 1.15, .95, 1, .9],
            gap="small",
        )
        with nav_logo:
            if st.button(
                "Crédit Agricole du Maroc",
                width="stretch",
                key="top_nav_logo",
                help="Retour à l'accueil",
                disabled=st.session_state.processing,
            ):
                _go_to("Accueil")
                st.rerun()
        with nav_project:
            if st.button(
                "1  Mon projet",
                width="stretch",
                type="primary" if st.session_state.page == "Projet" else "secondary",
                key="top_nav_project",
                disabled=st.session_state.processing,
            ):
                _go_to("Projet" if account_ready else "Accueil")
                st.rerun()
        with nav_docs:
            if st.button(
                "2  Justificatifs",
                width="stretch",
                type="primary" if st.session_state.page == "Extraction" else "secondary",
                key="top_nav_documents",
                disabled=st.session_state.processing or not account_ready,
            ):
                _go_to("Extraction")
                st.rerun()
        with nav_check:
            if st.button(
                "3  Vérification",
                width="stretch",
                type="primary" if st.session_state.page == "Verification" else "secondary",
                key="top_nav_verification",
                disabled=st.session_state.processing or not documents_ready,
            ):
                _go_to("Verification")
                st.rerun()
        with nav_sim:
            if st.button(
                "4  Simulation",
                width="stretch",
                type="primary" if st.session_state.page == "Simulation" else "secondary",
                key="top_nav_simulation",
                disabled=st.session_state.processing or not dossier_complete,
            ):
                _go_to("Simulation")
                st.rerun()
        with nav_estimate:
            if st.button(
                "5  Estimation",
                width="stretch",
                type="primary" if st.session_state.page == "Estimation" else "secondary",
                key="top_nav_estimation",
                disabled=st.session_state.processing,
            ):
                _go_to("Estimation")
                st.rerun()
        with nav_space:
            with st.popover(f"{initials}  Mon espace", width="stretch"):
                if account_ready:
                    profile = st.session_state.customer_profile
                    display_name = " ".join(
                        filter(None, (profile.get("prenom"), profile.get("nom")))
                    ).strip()
                    safe_name = html.escape(display_name or "Mon compte")
                    safe_email = html.escape(str(profile.get("email", "")))
                    st.markdown(
                        f"""
                        <div class="cam-space-profile">
                            <div class="cam-space-name">{safe_name}</div>
                            <div class="cam-space-email">{safe_email}</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                    try:
                        saved_project = (
                            load_project(st.session_state.current_client_id) or {}
                        )
                    except Exception:
                        saved_project = {}
                    completed_steps = sum(
                        (bool(saved_project), documents_ready, dossier_complete, dossier_complete)
                    )
                    progress_percent = int(completed_steps / 4 * 100)
                    st.markdown(
                        f'<div class="cam-space-progress">Avancement du dossier : '
                        f'<strong>{progress_percent} %</strong></div>',
                        unsafe_allow_html=True,
                    )
                    st.progress(progress_percent / 100)
                else:
                    st.caption(
                        "Connectez-vous pour sauvegarder et reprendre votre dossier."
                    )
                    if st.button(
                        "Espace client",
                        icon=":material/account_circle:",
                        type="primary",
                        width="stretch",
                        key="top_nav_customer_access",
                    ):
                        render_customer_access_dialog()

                if st.button(
                    "Demander à Nour",
                    icon=":material/chat:",
                    width="stretch",
                    key="top_nav_nour",
                ):
                    st.session_state.assistant_open = True
                    st.rerun()

                st.markdown("**🛡️ Confidentialité**")
                st.caption(
                    "Vos justificatifs servent uniquement à préparer votre simulation."
                )
                st.caption(
                    "Vous gardez le contrôle sur les informations enregistrées."
                )

                if st.button(
                    "Espace conseiller",
                    icon=":material/admin_panel_settings:",
                    width="stretch",
                    key="top_nav_advisor",
                ):
                    st.session_state.page = "Conseiller"
                    st.rerun()

                if account_ready and st.button(
                    "Se déconnecter",
                    icon=":material/logout:",
                    width="stretch",
                    key="top_nav_logout",
                ):
                    for key in (
                        "documents", "current_doc_id", "confirmed_fields", "last_result",
                        "chat_history", "credit_profile", "customer_profile",
                        "compromis_skipped", "additional_statement_mode",
                    ):
                        st.session_state.pop(key, None)
                    st.session_state.account_created = False
                    st.session_state.current_client_id = None
                    st.session_state.page = "Accueil"
                    st.rerun()

    st.markdown(
        f"""
        <div class="cam-breadcrumb">
            Accueil &nbsp;&gt;&nbsp; <strong>{html.escape(current_page)}</strong>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_cam_hero(eyebrow, title, text):
    """Afficher l'accueil principal et l'avancement réel du dossier."""
    account_ready = bool(st.session_state.account_created)
    project_ready = False
    documents_ready = False
    dossier_complete = False

    if account_ready:
        try:
            project_ready = bool(load_project(st.session_state.current_client_id))
        except Exception:
            project_ready = False
        documents = current_client_documents()
        required_types = {"carte_identite", "bulletin", "releve"}
        documents_ready = required_types.issubset(reviewed_document_types(documents))
        try:
            _, _, dossier_complete, _ = dossier_readiness()
        except Exception:
            dossier_complete = False

    # La quatrième étape devient disponible lorsque le dossier est complet.
    # Elle reste l'étape active tant que le client se trouve sur l'accueil.
    completed = [
        project_ready,
        documents_ready,
        dossier_complete,
        False,
    ]
    active_index = next(
        (index for index, is_done in enumerate(completed) if not is_done),
        3,
    )
    journey_steps = (
        ("Décrire le projet", "Type de bien, ville et durée"),
        ("Ajouter les justificatifs", "Identité, revenus et relevé bancaire"),
        ("Vérifier les informations", "Correction et validation avant simulation"),
        ("Comparer les simulations", "Durées, mensualités et capacité d'emprunt"),
    )
    journey_rows = []
    for index, (label, description) in enumerate(journey_steps):
        if completed[index]:
            row_class = "is-done"
            state = "TERMINÉ"
        elif index == active_index:
            row_class = "is-current"
            state = "EN COURS" if account_ready else "COMMENCER"
        else:
            row_class = ""
            state = "À FAIRE"
        journey_rows.append(
            f"""
            <div class="cam-journey-row {row_class}">
                <span class="cam-journey-number">{index + 1}</span>
                <span class="cam-journey-copy">
                    <strong>{html.escape(label)}</strong>
                    <small>{html.escape(description)}</small>
                </span>
                <span class="cam-journey-state">{state}</span>
            </div>
            """
        )
    journey_html = "".join(journey_rows)
    current_step = min(sum(completed) + 1, 4)
    progress_percent = current_step * 25

    if not account_ready:
        primary_label = "Démarrer le parcours"
    elif not project_ready:
        primary_label = "Décrire mon projet"
    elif not documents_ready:
        primary_label = "Ajouter mes justificatifs"
    elif not dossier_complete:
        primary_label = "Vérifier mes informations"
    else:
        primary_label = "Voir ma simulation"

    def continue_journey():
        if not account_ready:
            render_customer_access_dialog()
        elif not project_ready:
            _go_to("Projet")
            st.rerun()
        elif not documents_ready:
            _go_to("Extraction")
            st.rerun()
        elif not dossier_complete:
            _go_to("Verification")
            st.rerun()
        else:
            _go_to("Simulation")
            st.rerun()

    with st.container(key="cam_home_experience"):
        intro_column, journey_column = st.columns([1.35, 1], gap=None)

        with intro_column:
            with st.container(key="cam_home_intro", height="stretch"):
                st.markdown(
                    f"""
                    <div class="cam-home-intro-copy">
                        <div class="ca-eyebrow"><span></span>{html.escape(str(eyebrow))}</div>
                        <h1>{html.escape(str(title))}</h1>
                        <p>{html.escape(str(text))}</p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                primary_action, example_action = st.columns([1.25, 1], gap="small")
                with primary_action:
                    if st.button(
                        primary_label,
                        icon=":material/arrow_forward:",
                        type="primary",
                        width="stretch",
                        key="cam_home_primary_action",
                        disabled=st.session_state.processing,
                    ):
                        continue_journey()
                with example_action:
                    if st.button(
                        "Faire une estimation",
                        width="stretch",
                        key="cam_home_example_action",
                        disabled=st.session_state.processing,
                    ):
                        _go_to("Estimation")
                        st.rerun()
                st.markdown(
                    """
                    <div class="cam-hero-trust">
                        <span>♢&nbsp; Données protégées</span>
                        <span>✓&nbsp; Validation par vos soins</span>
                        <span>◷&nbsp; Estimation non contractuelle</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        with journey_column:
            with st.container(key="cam_home_journey", height="stretch"):
                st.markdown(
                    f"""
                    <div class="cam-journey-kicker">VOTRE DEMANDE</div>
                    <div class="cam-journey-title">Un parcours guidé, étape par étape</div>
                    <div class="cam-journey-subtitle">Étape {current_step} sur 4 · progression enregistrée automatiquement</div>
                    <div class="cam-journey-progress" role="progressbar" aria-valuenow="{progress_percent}" aria-valuemin="0" aria-valuemax="100">
                        <span style="width:{progress_percent}%"></span>
                    </div>
                    <div class="cam-journey-list">{journey_html}</div>
                    """,
                    unsafe_allow_html=True,
                )
                footer_info, footer_action = st.columns([1.1, .9], vertical_alignment="center")
                with footer_info:
                    st.caption(f"Progression {current_step}/4 étapes")
                with footer_action:
                    if st.button(
                        "Continuer",
                        icon=":material/arrow_forward:",
                        type="primary",
                        width="stretch",
                        key="cam_home_continue_action",
                        disabled=st.session_state.processing,
                    ):
                        continue_journey()



def _go_to(page):
    st.session_state.page = page


def current_client_documents():
    return {
        doc_id: document for doc_id, document in st.session_state.documents.items()
        if document.get("client_id") == st.session_state.current_client_id
    }


DOCUMENT_JOURNEY = (
    {
        "type": "carte_identite",
        "title": "Carte d'identité",
        "instruction": "Ajoutez le recto et le verso de votre carte d'identité.",
        "optional": False,
    },
    {
        "type": "bulletin",
        "title": "Bulletin de paie",
        "instruction": "Ajoutez votre bulletin de paie le plus récent.",
        "optional": False,
    },
    {
        "type": "releve",
        "title": "Relevé bancaire",
        "instruction": "Ajoutez un relevé bancaire récent et lisible.",
        "optional": False,
    },
    {
        "type": "compromis",
        "title": "Compromis de vente",
        "instruction": "Ajoutez votre compromis si vous l'avez déjà signé.",
        "optional": True,
    },
)
MAX_BANK_STATEMENTS = 3


def _bank_statements(documents=None):
    documents = documents if documents is not None else current_client_documents()
    statements = [
        (document_id, document)
        for document_id, document in documents.items()
        if document.get("type") == "releve"
        and document.get("status") == "completed"
        and document.get("result")
    ]
    return sorted(
        statements,
        key=lambda item: item[1].get("timestamp") or "",
    )


def _request_additional_statement():
    statements = _bank_statements()
    if len(statements) >= MAX_BANK_STATEMENTS:
        return
    st.session_state.additional_statement_mode = True
    st.session_state.page = "Extraction"
    st.session_state.current_doc_id = None
    st.session_state.last_result = None
    st.session_state.confirmed_fields = {}
    st.rerun()


def completed_document_types(documents=None):
    """Retourner les types dont l'analyse est terminée pour le client connecté."""
    documents = documents if documents is not None else current_client_documents()
    return {
        document.get("type")
        for document in documents.values()
        if document.get("status") == "completed"
    }


def reviewed_document_types(documents=None):
    """Retourner les types explicitement validés par l'utilisateur."""
    documents = documents if documents is not None else current_client_documents()
    return {
        document.get("type")
        for document in documents.values()
        if document.get("status") == "completed"
        and document.get("journey_reviewed") is True
    }


def required_documents_ready(documents=None):
    """Les justificatifs obligatoires sont prêts après validation humaine."""
    documents = documents if documents is not None else current_client_documents()
    required_types = {"carte_identite", "bulletin", "releve"}
    return required_types.issubset(reviewed_document_types(documents))


def credit_journey_step(documents=None):
    """Rester sur un justificatif jusqu'à sa validation par le client."""
    documents = documents if documents is not None else current_client_documents()
    reviewed_types = reviewed_document_types(documents)

    for index, document_step in enumerate(DOCUMENT_JOURNEY[:3]):
        document_type = document_step["type"]
        if document_type not in reviewed_types:
            return index

    if not st.session_state.get("compromis_skipped", False):
        if "compromis" not in reviewed_types:
            return 3

    _, information_ready = build_client_summary(documents)
    return 5 if information_ready and st.session_state.page == "Simulation" else 4


def render_credit_journey(active_step, documents=None):
    """Afficher le parcours et ouvrir directement la pièce sélectionnée."""
    documents = documents if documents is not None else current_client_documents()
    labels = (
        "Carte d'identité",
        "Bulletin",
        "Relevé",
        "Compromis",
        "Vérification",
        "Simulation",
    )
    st.progress(min(active_step, 5) / 5)
    columns = st.columns(len(labels), gap="small")

    for index, (column, label) in enumerate(zip(columns, labels)):
        if index < active_step:
            icon = "✅"
        elif index == active_step:
            icon = "●"
        else:
            icon = "○"

        with column:
            if index < len(DOCUMENT_JOURNEY):
                document_type = DOCUMENT_JOURNEY[index]["type"]
                candidates = [
                    (document_id, document)
                    for document_id, document in documents.items()
                    if document.get("type") == document_type
                    and document.get("status") == "completed"
                    and document.get("result")
                ]
                candidates.sort(
                    key=lambda item: item[1].get("timestamp") or "",
                    reverse=True,
                )
                selected = candidates[0] if candidates else None
                if st.button(
                    f"{icon} {index + 1}  {label}",
                    key=f"journey_open_{document_type}",
                    width="stretch",
                    disabled=selected is None,
                    help=(
                        f"Ouvrir et vérifier : {selected[1].get('filename', 'Document')}"
                        if selected
                        else "Aucun document analysé pour cette étape"
                    ),
                ):
                    document_id, document = selected
                    st.session_state.current_doc_id = document_id
                    st.session_state.last_result = document.get("result")
                    st.session_state.confirmed_fields = document.get(
                        "confirmed_fields", {}
                    )
                    st.rerun()
                st.caption(
                    "Cliquer pour revoir"
                    if selected
                    else "Document non ajouté"
                )
            else:
                st.markdown(f"**{icon} {index + 1}**")
                st.caption(label)


def _next_journey_document(current_type, documents=None):
    """Retourner le justificatif suivant disponible dans l'ordre du parcours."""
    documents = documents if documents is not None else current_client_documents()
    types = [step["type"] for step in DOCUMENT_JOURNEY]
    try:
        start = types.index(current_type) + 1
    except ValueError:
        return None
    for document_type in types[start:]:
        candidates = [
            (document_id, document)
            for document_id, document in documents.items()
            if document.get("type") == document_type
            and document.get("status") == "completed"
            and document.get("result")
        ]
        if candidates:
            return max(
                candidates,
                key=lambda item: item[1].get("timestamp") or "",
            )
    return None


def _open_document_or_resume(next_document):
    """Ouvrir une pièce existante ou reprendre l'étape normale du parcours."""
    if next_document:
        document_id, document = next_document
        st.session_state.current_doc_id = document_id
        st.session_state.last_result = document.get("result")
        st.session_state.confirmed_fields = document.get("confirmed_fields", {})
    else:
        st.session_state.current_doc_id = None
        st.session_state.last_result = None
        st.session_state.confirmed_fields = {}


def render_guided_document_review(document_id, document, journey_step, advisor_id):
    """Afficher, à la demande, la relecture détaillée d'un document."""
    result = document.get("result") or {}
    control_result = result.get("control_result", {})
    already_reviewed = document.get("journey_reviewed") is True

    if document.get("type") == "releve":
        statements = _bank_statements()
        statement_ids = [item[0] for item in statements]
        if len(statements) > 1 and document_id in statement_ids:
            position = statement_ids.index(document_id)
            st.caption(f"Relevé bancaire {position + 1} sur {len(statements)}")
            previous_col, next_col = st.columns(2)
            with previous_col:
                if st.button(
                    "Relevé précédent",
                    icon=":material/arrow_back:",
                    key=f"previous_statement_{document_id}",
                    disabled=position == 0,
                    width="stretch",
                ):
                    _open_document_or_resume(statements[position - 1])
                    st.rerun()
            with next_col:
                if st.button(
                    "Relevé suivant",
                    icon=":material/arrow_forward:",
                    key=f"next_statement_{document_id}",
                    disabled=position >= len(statements) - 1,
                    width="stretch",
                ):
                    _open_document_or_resume(statements[position + 1])
                    st.rerun()
        if len(statements) < MAX_BANK_STATEMENTS:
            if st.button(
                f"Ajouter un relevé ({len(statements)}/{MAX_BANK_STATEMENTS})",
                icon=":material/note_add:",
                type="primary",
                width="stretch",
                key=f"add_statement_from_review_{document_id}",
            ):
                _request_additional_statement()
        else:
            st.success("3 relevés bancaires enregistrés")

    title_col, delete_col = st.columns([4, 1])
    with title_col:
        st.subheader(f"Détails — {document.get('filename', 'Document')}")
        if not already_reviewed:
            st.badge("À vérifier", color="orange", icon=":material/rate_review:")
    with delete_col:
        if st.button(
            "Supprimer",
            icon=":material/delete:",
            key=f"delete_reviewed_document_{document_id}",
            width="stretch",
        ):
            delete_one_document_dialog(document_id)
    st.caption(
        "Comparez les informations détectées avec le justificatif, corrigez-les "
        "si nécessaire, puis validez pour accéder au document suivant."
        if not already_reviewed else
        "Vous pouvez modifier à nouveau les informations enregistrées pour ce justificatif."
    )

    if not control_result.get("valid", False):
        st.error(
            f"Document rejeté : {control_result.get('reason', 'raison inconnue')}"
        )
        return

    security = result.get("extraction_security", {})
    if security.get("suspicious"):
        st.warning(
            "Certaines informations du document demandent une vérification attentive."
        )

    validation_result = result.get("validation_result") or {}
    fields = validation_result.get("fields", {})
    if not fields:
        st.error("Aucune information exploitable n'a été extraite de ce document.")
        return

    confirmations = deepcopy(document.get("confirmed_fields") or {})
    submitted = render_document_review(
        result, document["type"], document_id, advisor_id,
        st.session_state.session_id, confirmations,
        submit_label=(
            "Enregistrer et passer au document suivant"
            if already_reviewed
            else "Valider et continuer"
        ),
    )
    if submitted:
        updated = dict(document, confirmed_fields=confirmations, journey_reviewed=True)
        try:
            save_document(st.session_state.current_client_id, document_id, updated)
        except Exception:
            st.error("La sauvegarde a échoué. Vos saisies sont conservées ; réessayez.")
            return
        document.update(updated)
        if document.get("type") == "releve":
            st.session_state.additional_statement_mode = False
            statements = _bank_statements()
            statement_ids = [item[0] for item in statements]
            position = statement_ids.index(document_id) if document_id in statement_ids else -1
            next_document = (
                statements[position + 1]
                if 0 <= position < len(statements) - 1
                else _next_journey_document(
                    document.get("type"), current_client_documents()
                )
            )
        else:
            next_document = _next_journey_document(
                document.get("type"),
                current_client_documents(),
            )
        _open_document_or_resume(next_document)
        st.session_state.journey_notice = "Les corrections détaillées sont enregistrées."
        st.rerun()


def _remove_uploaded_files(paths):
    """Supprime uniquement des fichiers situés dans le répertoire d'upload."""
    upload_root = Path("data/uploads").resolve()
    failures = []
    for raw_path in set(filter(None, paths)):
        try:
            candidate = Path(raw_path).resolve()
            if not candidate.is_relative_to(upload_root):
                failures.append(Path(raw_path).name)
                continue
            if candidate.is_file():
                candidate.unlink()
        except (OSError, RuntimeError):
            failures.append(Path(raw_path).name)
    return failures


@st.dialog("Supprimer ce justificatif")
def delete_one_document_dialog(document_id):
    document = st.session_state.documents.get(document_id)
    if not document or document.get("client_id") != st.session_state.current_client_id:
        st.error("Ce justificatif n'est plus disponible.")
        return
    st.warning(
        f"Le justificatif « {document.get('filename') or 'Document'} » et toutes les "
        "informations confirmées depuis cette pièce seront supprimés."
    )
    confirmed = st.checkbox(
        "Je confirme la suppression de ce justificatif",
        key=f"confirm_delete_document_{document_id}",
    )
    if st.button(
        "Supprimer définitivement",
        icon=":material/delete:",
        type="primary",
        width="stretch",
        disabled=not confirmed,
        key=f"delete_document_confirm_{document_id}",
    ):
        try:
            delete_document(st.session_state.current_client_id, document_id)
        except Exception as exc:
            st.error(f"Suppression impossible : {exc}")
            return
        failures = _remove_uploaded_files([document.get("document_path")])
        for key in list(st.session_state):
            if document_id in str(key):
                st.session_state.pop(key, None)
        st.session_state.documents.pop(document_id, None)
        if st.session_state.get("current_doc_id") == document_id:
            st.session_state.current_doc_id = None
            st.session_state.last_result = None
            st.session_state.confirmed_fields = {}
        st.session_state.pop(f"verification_table_{st.session_state.current_client_id}", None)
        st.session_state.pop(f"verification_checked_{st.session_state.current_client_id}", None)
        audit.log_event(
            "client_document_deleted",
            advisor_id=f"client_portal_{st.session_state.session_id[:8]}",
            session_id=st.session_state.session_id,
            document_path=document.get("document_path"),
            document_type=document.get("type"),
            decision="confirme_par_client",
            details={"fichier_non_supprime": failures},
        )
        st.session_state.documents_reset_notice = "Le justificatif a été supprimé."
        st.rerun()


def dossier_readiness():
    """État métier réel utilisé pour verrouiller/déverrouiller la simulation."""
    documents = current_client_documents()
    rows, business_complete = build_client_summary(documents) if documents else ([], False)
    missing = [row["Champ"] for row in rows if row["Statut"] in ("Manquant", "Conflit")]
    required_documents = {
        "carte_identite": "Carte d'identité",
        "bulletin": "Bulletin de paie",
        "releve": "Relevé bancaire",
    }
    available_types = reviewed_document_types(documents)
    missing.extend(label for doc_type, label in required_documents.items()
                   if doc_type not in available_types)
    return documents, rows, business_complete and not missing, missing


initialize_session_state()
# =========================================================
# SIDEBAR AMÉLIORÉE AVEC GESTION CLIENT
# =========================================================

inject_app_styles()

advisor_id = (
    f"client_portal_"
    f"{st.session_state.session_id[:8]}"
)

if st.session_state.page != "Conseiller":
    render_assistant_dock(advisor_id)

# =========================================================
# APPLICATION DU THÈME
# =========================================================



# =========================================================
# RENDU DE L'EN-TÊTE
# =========================================================

if st.session_state.page != "Conseiller":
    render_header()

# =========================================================
# PAGE ACCUEIL
# =========================================================

if st.session_state.page == "Conseiller":
    if st.button(
        "Retour à l'espace client",
        icon=":material/arrow_back:",
        key="advisor_back_to_client",
    ):
        st.session_state.page = "Accueil"
        st.rerun()
    render_advisor_sidebar()
    render_advisor_dashboard()

elif st.session_state.page == "Accueil":
    if not st.session_state.account_created:
        render_cam_hero(
            "Crédit habitat · Espace client",
            "Commençons votre projet habitat",
            "Créez votre espace personnel pour sauvegarder vos justificatifs, "
            "reprendre votre parcours à tout moment et affiner votre simulation "
            "en toute autonomie.",
        )
        render_home_assurance_strip()
        st.stop()

    client_docs = current_client_documents()
    completed_types = completed_document_types(client_docs)
    required_types = {"carte_identite", "bulletin", "releve"}
    completed_required = len(required_types & completed_types)
    documents_ready = required_types.issubset(reviewed_document_types(client_docs))
    _, _, dossier_complete, _ = dossier_readiness()
    saved_project = (
        load_project(st.session_state.current_client_id)
        or st.session_state.get("quick_project", {})
    )

    if dossier_complete:
        hero_title = "Votre dossier est prêt pour la simulation."
        hero_text = (
            "Vos justificatifs et vos informations essentielles sont vérifiés. "
            "Vous pouvez maintenant comparer plusieurs scénarios de financement."
        )
    elif completed_required:
        hero_title = "Reprenez votre projet là où vous l’avez laissé."
        hero_text = (
            "Votre dossier est sauvegardé. Finalisez les justificatifs et vérifiez "
            "les informations détectées avant de lancer la simulation."
        )
    else:
        hero_title = "Construisez votre projet immobilier en toute simplicité."
        hero_text = (
            "Déposez vos justificatifs, contrôlez les informations détectées et "
            "obtenez une estimation personnalisée de votre financement."
        )

    render_cam_hero(
        "Crédit habitat · Espace personnel",
        hero_title,
        hero_text,
    )
    render_home_assurance_strip()

    # -----------------------------------------------------
    # SYNTHÈSE OU FORMULAIRE DU PROJET
    # -----------------------------------------------------

    if saved_project:
        with st.container(key="home_project_summary", border=True):
            summary_title, summary_action = st.columns(
                [4, 1], vertical_alignment="center"
            )
            with summary_title:
                st.markdown("### Votre projet immobilier")
                st.markdown(
                    '<div class="home-status-line"><span class="home-status-dot"></span>'
                    '<span>Projet enregistré</span></div>',
                    unsafe_allow_html=True,
                )
            with summary_action:
                if st.button(
                    "Modifier", icon=":material/edit:", width="stretch",
                    key="edit_home_project",
                ):
                    st.session_state.page = "Projet"
                    st.rerun()

            project_metrics = st.columns(3)
            project_metrics[0].metric(
                "Ville", saved_project.get("city") or "À préciser", border=True
            )
            project_metrics[1].metric(
                "Type de bien", saved_project.get("property_type") or "À préciser", border=True
            )
            project_metrics[2].metric(
                "Durée",
                f"{int(saved_project.get('duration_years') or 20)} ans",
                border=True,
            )

    # -----------------------------------------------------
    # ACTIONS CONTEXTUELLES
    # -----------------------------------------------------

    if not saved_project:
        primary_title = "Décrire mon projet"
        primary_text = "Indiquez le type de bien, la ville et la durée souhaitée du crédit."
        primary_caption = "Première étape · moins d'une minute"
        primary_label = "Décrire mon projet"
        primary_icon = ":material/home_work:"
        primary_page = "Projet"
    elif dossier_complete:
        primary_title = "Votre simulation est disponible"
        primary_text = "Consultez votre mensualité, votre capacité d’emprunt et comparez les durées."
        primary_caption = "Données issues de vos informations vérifiées"
        primary_label = "Voir ma simulation"
        primary_icon = ":material/analytics:"
        primary_page = "Simulation"
    elif documents_ready:
        primary_title = "Vérifier mes informations"
        primary_text = "Contrôlez les informations essentielles extraites de vos justificatifs."
        primary_caption = "Dernière étape avant votre simulation"
        primary_label = "Continuer la vérification"
        primary_icon = ":material/fact_check:"
        primary_page = "Verification"
    else:
        primary_title = "Continuer mon dossier"
        primary_text = "Ajoutez vos justificatifs pour obtenir une simulation personnalisée."
        primary_caption = f"{completed_required}/3 justificatifs obligatoires traités"
        primary_label = "Accéder à mes justificatifs"
        primary_icon = ":material/upload_file:"
        primary_page = "Extraction"

    action_left, action_right = st.columns(2, gap="large")
    with action_left:
        with st.container(key="home_primary_action", border=True, height="stretch"):
            st.markdown(f"### {primary_title}")
            st.write(primary_text)
            st.caption(primary_caption)
            if st.button(
                primary_label, icon=primary_icon, type="primary", width="stretch",
                disabled=st.session_state.processing, key="home_primary_action_button",
            ):
                st.session_state.page = primary_page
                st.rerun()

    with action_right:
        with st.container(key="home_secondary_action", border=True, height="stretch"):
            st.markdown("### Explorer une autre hypothèse")
            st.write(
                "Estimez une mensualité, calculez votre capacité d’emprunt "
                "ou comparez plusieurs durées."
            )
            st.caption("Calcul immédiat · Modifiable · Non contractuel")
            if st.button(
                "Ouvrir les outils de simulation", icon=":material/calculate:",
                width="stretch", disabled=st.session_state.processing, key="home_quick",
            ):
                st.session_state.page = "Estimation"
                st.rerun()

    # -----------------------------------------------------
    # ÉTAT DU DOSSIER
    # -----------------------------------------------------

    st.markdown('<div class="ca-section-title">État de votre dossier</div>', unsafe_allow_html=True)
    st.caption("Une vue synthétique des éléments nécessaires à votre simulation personnalisée.")
    status_columns = st.columns(3, gap="medium")

    with status_columns[0]:
        with st.container(border=True, height="stretch"):
            st.caption("PROJET IMMOBILIER")
            st.markdown("### " + ("Renseigné" if saved_project else "À compléter"))
            st.write(
                "Le type de bien, la ville et la durée sont enregistrés."
                if saved_project else
                "Renseignez les caractéristiques principales de votre projet."
            )

    with status_columns[1]:
        with st.container(border=True, height="stretch"):
            st.caption("JUSTIFICATIFS")
            st.markdown(f"### {completed_required} sur 3")
            st.write(
                "Les trois justificatifs obligatoires ont été analysés."
                if completed_required == 3 else
                f"Il reste {3 - completed_required} justificatif(s) obligatoire(s) à traiter."
            )

    with status_columns[2]:
        with st.container(border=True, height="stretch"):
            st.caption("VÉRIFICATION")
            st.markdown("### " + ("Terminée" if dossier_complete else "En attente"))
            st.write(
                "Les informations indispensables sont confirmées."
                if dossier_complete else
                "La simulation personnalisée sera disponible après vérification."
            )

    with st.container(key="home_help_banner", border=True):
        help_text, help_action = st.columns([3.4, 1], vertical_alignment="center")
        with help_text:
            st.markdown("### Une question sur votre crédit habitat ?")
            st.caption(
                "Nour vous explique les documents, les étapes et les conditions "
                "à partir de la documentation disponible."
            )
        with help_action:
            if st.button(
                "Poser une question", icon=":material/chat:",
                width="stretch", key="home_ask_question",
            ):
                st.session_state.assistant_open = True
                st.rerun()

    with st.container(border=True):
        st.markdown("**Une estimation pour mieux vous orienter**")
        st.caption(
            "Le résultat fourni est indicatif et ne constitue ni un accord de crédit ni une offre contractuelle. "
            "La banque étudiera votre dossier complet avant toute décision."
        )


# =========================================================
# PAGE DESCRIPTION DU PROJET
# =========================================================

elif st.session_state.page == "Projet":
    if not st.session_state.account_created:
        st.session_state.page = "Accueil"
        st.rerun()
    saved_project = load_project(st.session_state.current_client_id) or {}
    render_housing_project_step(saved_project)


# =========================================================
# PAGE EXTRACTION AMÉLIORÉE AVEC GESTION MULTI-DOCUMENTS
# =========================================================

elif st.session_state.page == "Extraction":
    if not st.session_state.account_created:
        st.session_state.page = "Accueil"
        st.rerun()
    if not load_project(st.session_state.current_client_id):
        st.session_state.page = "Projet"
        st.rerun()
    st.title("Mon parcours de crédit habitat")
    st.caption(
        "Avancez simplement, une étape après l'autre. Le prochain document à "
        "ajouter est sélectionné automatiquement."
    )
    reset_notice = st.session_state.pop("documents_reset_notice", None)
    if reset_notice:
        st.success(reset_notice, icon=":material/check_circle:")
    journey_notice = st.session_state.pop("journey_notice", None)
    if journey_notice:
        st.success(journey_notice, icon=":material/check_circle:")
    
    # -----------------------------------------------------
    # LISTE DES DOCUMENTS DU CLIENT
    # -----------------------------------------------------
    
    client_docs = {
        doc_id: doc_data 
        for doc_id, doc_data in st.session_state.documents.items()
        if doc_data.get("client_id") == st.session_state.current_client_id
    }

    statement_count = len(_bank_statements(client_docs))
    if statement_count >= MAX_BANK_STATEMENTS:
        st.session_state.additional_statement_mode = False
    additional_statement_mode = bool(
        st.session_state.get("additional_statement_mode")
    )

    journey_step = credit_journey_step(client_docs)
    _, _, dossier_complete, _ = dossier_readiness()

    # Si l'analyse d'un document est terminée mais que le client ne l'a pas
    # encore validé, rouvrir automatiquement sa fiche. Ainsi, un rerun ou une
    # reconnexion ne peut pas faire avancer silencieusement le parcours.
    selected_document = st.session_state.documents.get(
        st.session_state.current_doc_id
    )
    active_journey_step = 2 if additional_statement_mode else journey_step
    if not selected_document and active_journey_step < len(DOCUMENT_JOURNEY):
        active_document_type = DOCUMENT_JOURNEY[active_journey_step]["type"]
        pending_reviews = [
            (document_id, document)
            for document_id, document in client_docs.items()
            if document.get("type") == active_document_type
            and document.get("status") == "completed"
            and document.get("journey_reviewed") is not True
            and document.get("result")
        ]
        pending_reviews.sort(
            key=lambda item: item[1].get("timestamp") or "",
            reverse=True,
        )
        if pending_reviews:
            selected_id, selected_document = pending_reviews[0]
            st.session_state.current_doc_id = selected_id
            st.session_state.last_result = selected_document.get("result")
            st.session_state.confirmed_fields = selected_document.get(
                "confirmed_fields", {}
            )

    # Un dossier finalisé reste entièrement consultable depuis « Mes documents ».
    # L'étape 6 sert uniquement à afficher toutes les coches dans ce cas.
    render_credit_journey(
        2 if additional_statement_mode else (6 if dossier_complete else journey_step),
        client_docs,
    )
    st.divider()

    # Lorsqu'une étape documentaire est sélectionnée, sa fiche de
    # vérification s'affiche immédiatement. Les boutons du parcours en haut
    # remplacent l'ancienne grille de documents.
    selected = st.session_state.documents.get(st.session_state.current_doc_id)
    if selected and selected.get("status") == "completed" and selected.get("result"):
        render_guided_document_review(
            st.session_state.current_doc_id,
            selected,
            journey_step,
            advisor_id,
        )
        st.stop()

    if not additional_statement_mode and journey_step >= 4:
        st.success(
            "Vos justificatifs sont enregistrés. Vérifiez maintenant les 5 informations "
            "essentielles dans un tableau unique pour débloquer la simulation."
        )
        action_left, action_right = st.columns(2)
        with action_left:
            if st.button(
                "Vérifier mes 5 informations",
                icon=":material/fact_check:",
                type="primary",
                width="stretch",
                key="documents_open_verification",
            ):
                st.session_state.page = "Verification"
                st.rerun()

        with action_right:
            if statement_count < MAX_BANK_STATEMENTS:
                if st.button(
                    f"Ajouter un autre relevé ({statement_count}/{MAX_BANK_STATEMENTS})",
                    icon=":material/note_add:",
                    width="stretch",
                    key="add_statement_after_documents",
                ):
                    _request_additional_statement()
            else:
                st.success("3 relevés bancaires enregistrés")
      

        if st.session_state.get("compromis_skipped", False):
            if st.button(
                "Ajouter mon compromis de vente",
                icon=":material/upload_file:",
                width="stretch",
                key="documents_add_compromis",
            ):
                st.session_state.compromis_skipped = False
                st.session_state.current_doc_id = None
                st.session_state.last_result = None
                st.rerun()
        st.stop()

    document_step = (
        DOCUMENT_JOURNEY[2]
        if additional_statement_mode
        else DOCUMENT_JOURNEY[journey_step]
    )
    document_type = document_step["type"]

    if additional_statement_mode:
        st.subheader(
            f"Ajouter un relevé bancaire — "
            f"{statement_count + 1} sur {MAX_BANK_STATEMENTS}"
        )
        st.info(
            "Les relevés supplémentaires sont facultatifs. Ils permettent "
            "d'estimer plus fiablement la régularité des revenus et des charges."
        )
    else:
        st.subheader(f"Étape {journey_step + 1} — {document_step['title']}")
    st.write(document_step["instruction"])

    if (
        not additional_statement_mode
        and document_type == "compromis"
        and statement_count < MAX_BANK_STATEMENTS
    ):
        if st.button(
            f"Ajouter un autre relevé ({statement_count}/{MAX_BANK_STATEMENTS})",
            icon=":material/note_add:",
            width="stretch",
            key="add_statement_before_compromise",
        ):
            _request_additional_statement()

    if document_step["optional"]:
        st.info(
            "Cette étape est facultative. Vous pouvez continuer même si vous "
            "n'avez pas encore signé de compromis."
        )
        if st.button(
            "Continuer sans compromis",
            icon=":material/skip_next:",
            width="stretch",
            key="skip_optional_compromis",
        ):
            st.session_state.compromis_skipped = True
            st.session_state.current_doc_id = None
            st.session_state.last_result = None
            st.rerun()
    
    # -----------------------------------------------------
    # AJOUTER UN NOUVEAU DOCUMENT
    # -----------------------------------------------------
    
    declared_data = {}
    with st.container():
        is_identity = document_type == "carte_identite"
        identity_mode = None

        if is_identity:
            identity_mode = st.radio(
                "Format de la carte d'identité",
                options=("PDF unique recto-verso", "Deux fichiers séparés"),
                horizontal=True,
                disabled=st.session_state.processing,
                key=f"identity_mode_{st.session_state.current_client_id}",
            )

            if identity_mode == "PDF unique recto-verso":
                identity_pdf = st.file_uploader(
                    "PDF contenant le recto et le verso",
                    type=["pdf"],
                    accept_multiple_files=False,
                    help="Le PDF doit contenir exactement deux pages, dans l'ordre recto puis verso.",
                    key=f"identity_pdf_{st.session_state.current_client_id}",
                )
                uploaded_files = [identity_pdf] if identity_pdf is not None else []
            else:
                recto = st.file_uploader(
                    "Recto de la carte",
                    type=[ext.lstrip(".") for ext in settings.allowed_extensions],
                    accept_multiple_files=False,
                    key=f"identity_recto_{st.session_state.current_client_id}",
                )
                verso = st.file_uploader(
                    "Verso de la carte",
                    type=[ext.lstrip(".") for ext in settings.allowed_extensions],
                    accept_multiple_files=False,
                    key=f"identity_verso_{st.session_state.current_client_id}",
                )
                uploaded_files = [file for file in (recto, verso) if file is not None]
        else:
            uploaded_value = st.file_uploader(
                "Déposer un document",
                type=[ext.lstrip(".") for ext in settings.allowed_extensions],
                accept_multiple_files=False,
                help=(
                    f"Formats acceptés : {', '.join(settings.allowed_extensions)}. "
                    f"Taille max : {settings.max_file_size_mb} MB"
                ),
                key=(
                    f"uploader_{st.session_state.current_client_id}_{document_type}_"
                    f"{statement_count}"
                    if document_type == "releve"
                    else f"uploader_{st.session_state.current_client_id}_{document_type}"
                ),
            )
            uploaded_files = [uploaded_value] if uploaded_value is not None else []

        upload_ready = bool(uploaded_files)

        if is_identity and identity_mode == "Deux fichiers séparés" and len(uploaded_files) != 2:
            upload_ready = False
            st.caption("Ajoutez les deux faces pour activer l'analyse.")

        if uploaded_files:
            invalid_messages = []
            for selected_file in uploaded_files:
                is_valid, message = validate_file(selected_file)
                if not is_valid:
                    invalid_messages.append(f"{selected_file.name} : {message}")

            total_size = sum(selected_file.size for selected_file in uploaded_files)
            if total_size > settings.max_file_size_mb * 1024 * 1024:
                invalid_messages.append(
                    f"Taille totale trop importante (max {settings.max_file_size_mb} MB)"
                )

            if (
                is_identity
                and identity_mode == "PDF unique recto-verso"
                and not invalid_messages
            ):
                try:
                    page_count = count_pdf_pages(uploaded_files[0])
                    if page_count != 2:
                        invalid_messages.append(
                            f"Le PDF doit contenir exactement 2 pages ; il en contient {page_count}."
                        )
                except Exception:
                    invalid_messages.append("Le PDF est illisible ou endommagé.")

            if invalid_messages:
                upload_ready = False
                for message in invalid_messages:
                    st.error(f"⚠️ {message}")
            else:
                for index, selected_file in enumerate(uploaded_files):
                    if is_identity and identity_mode == "Deux fichiers séparés":
                        label = "Recto" if index == 0 else "Verso"
                    elif is_identity:
                        label = "PDF recto-verso"
                    else:
                        label = "Document"
                    st.success(f"✅ {label} : {selected_file.name}")
                st.caption(f"📦 Taille totale : {total_size / 1024:.1f} KB")
    
    # -----------------------------------------------------
    # ERREUR PERSISTEE (affichée après un st.rerun() suite à un échec)
    # -----------------------------------------------------

    if st.session_state.get("last_error"):
        st.error(f"❌ Erreur lors du traitement : {st.session_state.last_error}")
        with st.expander("🔍 Détails techniques"):
            st.code(st.session_state.last_error)
        if st.button("Fermer ce message"):
            st.session_state.last_error = None
            st.rerun()
        st.divider()

    # Boutons d'action
    with st.container():
        st.button(
            "Lire mon document",
            icon=":material/arrow_forward:",
            type="primary",
            width="stretch",
            disabled=st.session_state.processing or not upload_ready,
            key="launch_document_analysis",
            on_click=request_document_analysis,
        )
    # -----------------------------------------------------
    # EXECUTION AMÉLIORÉE
    # -----------------------------------------------------
    
    if st.session_state.pop("analysis_requested", False):
        if not st.session_state.current_client_id:
            st.session_state.processing = False
            st.error("⚠️ Veuillez renseigner un identifiant client")
            st.stop()
        
        if not upload_ready:
            st.session_state.processing = False
            st.error("⚠️ Déposez un document avant de lancer l'analyse")
            st.stop()
        

        
        # Créer un ID unique pour ce document
        doc_id = str(uuid.uuid4())
        
        # Stocker le document dans la session
        st.session_state.documents[doc_id] = {
            "client_id": st.session_state.current_client_id,
            "type": document_type,
            "filename": (
                " + ".join(file.name for file in uploaded_files)
                if len(uploaded_files) > 1 else uploaded_files[0].name
            ),
            "timestamp": datetime.now().isoformat(),
            "status": "processing",
            "result": None,
            "confirmed_fields": {},
            "journey_reviewed": False,
            "declared_data": declared_data
        }
        
        st.session_state.current_doc_id = doc_id
        
        # Traiter avec progression
        st.session_state.processing = True
        st.session_state.last_error = None
        
        try:
            saved_path = save_document_files(uploaded_files, document_type, doc_id)
            st.session_state.documents[doc_id]["document_path"] = str(saved_path)
            result = process_document_with_progress(
                file_path=saved_path,
                document_type=document_type,
                declared_data=declared_data,
                advisor_id=advisor_id,
                session_id=st.session_state.session_id
            )
            
            # Mettre à jour les données du document
            st.session_state.documents[doc_id]["result"] = result
            st.session_state.documents[doc_id]["status"] = "completed"
            # Conserver le document actif : au prochain rerun, l'écran de
            # relecture s'affiche avant toute possibilité de passer au suivant.
            st.session_state.current_doc_id = doc_id
            st.session_state.last_result = result
            st.session_state.confirmed_fields = {}
            save_document(
                st.session_state.current_client_id, doc_id,
                st.session_state.documents[doc_id],
            )
            st.session_state.journey_notice = (
                f"{document_step['title']} analysé. Vérifiez les informations "
                "détectées, corrigez-les si nécessaire, puis cliquez sur "
                "« Valider et continuer »."
            )
            if document_type == "compromis":
                st.session_state.compromis_skipped = False
            
            # Log dans l'audit
            try:
                audit.log_document_processed(
                    document_id=doc_id,
                    document_type=document_type,
                    client_id=st.session_state.current_client_id,
                    advisor_id=advisor_id,
                    status="completed"
                )
            except Exception:
                pass
            
        except Exception as e:
            st.session_state.documents[doc_id]["status"] = "error"
            # st.error() affiché juste avant st.rerun() disparaît
            # instantanément (le rerun efface tout ce qui vient d'être
            # rendu) : on stocke le message en session_state pour le
            # ré-afficher après le rerun, au lieu de le perdre.
            st.session_state.last_error = str(e)
            logging.exception(
                "[Interface] Échec du traitement du document %s", doc_id
            )
        finally:
            st.session_state.processing = False
            st.rerun()
    
    # -----------------------------------------------------
# PAGE VÉRIFICATION DES INFORMATIONS ESSENTIELLES
# =========================================================

elif st.session_state.page == "Verification":
    if not st.session_state.account_created:
        st.session_state.page = "Accueil"
        st.rerun()
    client_docs = current_client_documents()
    if not required_documents_ready(client_docs):
        st.title("Vérification indisponible")
        st.warning(
            "Ajoutez d'abord votre carte d'identité, votre bulletin de paie "
            "et votre relevé bancaire."
        )
        if st.button(
            "Retourner à mes documents",
            icon=":material/upload_file:",
            type="primary",
            width="stretch",
        ):
            st.session_state.page = "Extraction"
            st.rerun()
        st.stop()

    statement_count = len(_bank_statements(client_docs))
    back_column, statement_column = st.columns(2)
    with back_column:
        if st.button(
            "Retour à mes justificatifs",
            icon=":material/arrow_back:",
            width="stretch",
            key="verification_back_to_documents_top",
        ):
            st.session_state.page = "Extraction"
            st.rerun()
    with statement_column:
        if statement_count < MAX_BANK_STATEMENTS:
            if st.button(
                f"Ajouter un relevé ({statement_count}/{MAX_BANK_STATEMENTS})",
                icon=":material/note_add:",
                type="primary",
                width="stretch",
                key="verification_add_statement",
            ):
                _request_additional_statement()
        else:
            st.success("3 relevés bancaires enregistrés")

    st.title("Vérifier mes informations")
    st.caption(
        "Retrouvez vos informations déjà corrigées. Vous pouvez les modifier avant votre "
        "simulation."
    )
    verification_project = (
        load_project(st.session_state.current_client_id)
        or st.session_state.get("quick_project", {})
    )
    render_final_verification(
        client_docs,
        st.session_state.current_client_id,
        advisor_id,
        st.session_state.session_id,
        verification_project,
    )

# =========================================================
# PAGE SIMULATION CLIENT
# =========================================================

elif st.session_state.page == "Estimation":
    st.title("Préparer mon projet habitat")

    st.caption(
        "Estimez votre mensualité ou découvrez votre "
        "capacité d'emprunt, sans compte ni justificatif."
    )

    simulation_tab, capacity_tab = st.tabs([
        "Estimer ma mensualité",
        "Calculer ma capacité d'emprunt",
    ])

    estimate = None
    quick_profile = st.session_state.get("credit_profile", {})
    quick_income = float(
        quick_profile.get("revenu_mensuel_net") or 0
    ) + float(
        quick_profile.get("autres_revenus_mensuels") or 0
    )
    quick_charges = float(
        quick_profile.get("charges_mensuelles") or 0
    )
    quick_project = st.session_state.get("quick_project", {})

    with simulation_tab:
        estimate = render_simulation(
            project=quick_project,
            key_prefix="quick",
            income=quick_income or None,
            existing_monthly_charges=quick_charges,
        )

    with capacity_tab:
        render_borrowing_capacity(
            project=quick_project,
            key_prefix="quick_capacity",
            income=quick_income or None,
            existing_monthly_charges=quick_charges,
        )

    if st.button(
        "Affiner avec mes documents",
        type="primary",
        key="quick_refine",
        width="stretch",
    ):
        if estimate:
            st.session_state.quick_project = estimate

        st.session_state.page = (
            "Extraction"
            if st.session_state.account_created
            else "Accueil"
        )

        st.rerun()

elif st.session_state.page == "Simulation":
    if not st.session_state.account_created:
        st.session_state.page = "Estimation"
        st.rerun()

    client_docs, _, dossier_complete, _ = dossier_readiness()

    if not dossier_complete:
        st.session_state.page = "Verification"
        st.rerun()

    st.title("Ma simulation de crédit habitat")

    st.caption(
        "Simulez votre crédit et comparez plusieurs durées "
        "avant de choisir le scénario adapté à votre projet."
    )

    saved_project = (
        load_project(st.session_state.current_client_id)
        or st.session_state.get("quick_project", {})
    )

    rows, _ = build_client_summary(client_docs)

    confirmed = {
        row["field"]: row["Valeur confirmée"]
        for row in rows
        if row["Statut"] == "Confirmé"
    }

    def confirmed_number(field_name):
        try:
            return float(
                confirmed.get(field_name) or 0
            )
        except (TypeError, ValueError):
            return 0.0

    income = (
        confirmed_number("salaire_net")
        + confirmed_number("revenus_complementaires")
    )

    existing_charges = confirmed_number(
        "charge_mensuelle_credits"
    )

    simulation_tab, capacity_tab = st.tabs([
    "Simuler ma mensualité",
    "Ma capacité d'emprunt",
])

    with simulation_tab:
         render_simulation(
        project=saved_project,
        key_prefix=(
            f"simulation_"
            f"{st.session_state.current_client_id}"
        ),
        income=income,
        existing_monthly_charges=existing_charges,
    )

    with capacity_tab:
         render_borrowing_capacity(
        project=saved_project,
        key_prefix=(
            f"capacity_"
            f"{st.session_state.current_client_id}"
        ),
        income=income,
        existing_monthly_charges=existing_charges,
    )
    with st.expander(
        "Ma situation vérifiée"
    ):
        for row in rows:
            st.write(
                f"{row['Champ']} : "
                f"{row['Valeur confirmée']}"
            )

    if st.button(
        "Modifier ma situation",
        key="simulation_edit",
        icon=":material/edit:",
    ):
        st.session_state.page = "Verification"
        st.rerun()

# =========================================================
# PAGE ASSISTANT AMÉLIORÉE
# =========================================================

# L'assistant est rendu après le contenu mais reste fixé à droite par CSS.

# =========================================================
# FOOTER
# =========================================================

st.divider()
st.caption("Crédit Agricole du Maroc — Assistant Crédit Habitat")

# =========================================================
# GESTION DES ERREURS GLOBALES
# =========================================================

if "error" in st.session_state:
    st.error(f"⚠️ {st.session_state.error}")
    if st.button("Effacer l'erreur", key="clear_global_error"):
        del st.session_state.error
        st.rerun()
