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
from ocr.scan_quality import analyze_document_quality
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
    authenticate, create_customer, delete_all_documents, delete_document,
    load_documents, load_project, save_document, save_project,
)
from extraction.schema import DOCUMENT_SCHEMAS
from ui.document_review import render_document_review
from ui.simulation import render_simulation
from ui.borrowing_capacity import render_borrowing_capacity
from copy import deepcopy
from ui.client_summary import (
    build_client_summary, render_client_summary, render_final_verification,
)
from ui.session_state import initialize_session_state
from ui.home_components import image_to_data_url, render_home_assurance_strip
from ui.assistant_dock import apply_assistant_result, render_assistant_dock
from utils.document_processing import (
    count_pdf_pages,
    get_orchestrator,
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
# CACHE
# =========================================================

@st.cache_data(show_spinner=False)
def get_document_quality(file_content: bytes, filename: str):
    """Éviter de recalculer la qualité à chaque rerun Streamlit."""
    return analyze_document_quality(
        content=file_content,
        filename=filename,
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


def render_header():
    """Afficher un en-tête inspiré de l'identité institutionnelle du GCAM."""
    page_labels = {
        "Accueil": "Mon projet habitat",
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
        completed_document_types(documents)
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
                type="primary" if st.session_state.page == "Accueil" else "secondary",
                key="top_nav_project",
                disabled=st.session_state.processing,
            ):
                _go_to("Accueil")
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
                        "compromis_skipped",
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


def render_cam_hero(eyebrow, title, text, badge):
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
        documents_ready = required_types.issubset(completed_document_types(documents))
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
        ("Décrire le projet", "Type de bien, montant et apport"),
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
            st.session_state.editing_home_project = True
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
    documents = documents if documents is not None else current_client_documents()
    required_types = {"carte_identite", "bulletin", "releve"}
    return required_types.issubset(completed_document_types(documents))


def credit_journey_step(documents=None):
    """Déterminer automatiquement la prochaine étape du parcours de crédit."""
    documents = documents if documents is not None else current_client_documents()
    completed_types = completed_document_types(documents)

    for index, document_step in enumerate(DOCUMENT_JOURNEY[:3]):
        document_type = document_step["type"]
        if document_type not in completed_types:
            return index

    if not st.session_state.get("compromis_skipped", False):
        if "compromis" not in completed_types:
            return 3

    _, information_ready = build_client_summary(documents)
    return 5 if information_ready and st.session_state.page == "Simulation" else 4


def render_credit_journey(active_step):
    """Afficher les six étapes du parcours dans un format court et lisible."""
    labels = (
        "Identité",
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
            st.markdown(f"**{icon} {index + 1}**")
            st.caption(label)


def render_guided_document_review(document_id, document, journey_step, advisor_id):
    """Afficher, à la demande, la relecture détaillée d'un document."""
    result = document.get("result") or {}
    control_result = result.get("control_result", {})

    title_col, close_col = st.columns([5, 1])
    with title_col:
        st.subheader(f"Détails — {document.get('filename', 'Document')}")
    with close_col:
        if st.button(
            "Fermer",
            icon=":material/close:",
            key=f"close_document_review_{document_id}",
            width="stretch",
        ):
            st.session_state.current_doc_id = None
            st.session_state.last_result = None
            st.session_state.confirmed_fields = {}
            st.rerun()
    st.caption(
        "Cette relecture détaillée est facultative. Les 5 informations utiles à la "
        "simulation seront regroupées dans un seul tableau à l'étape Vérification."
    )

    if not control_result.get("valid", False):
        st.error(
            f"Document rejeté : {control_result.get('reason', 'raison inconnue')}"
        )
        if st.button(
            "Supprimer et déposer un autre document",
            icon=":material/delete:",
            width="stretch",
            key=f"guided_delete_invalid_{document_id}",
        ):
            delete_one_document_dialog(document_id)
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
    )
    if submitted:
        updated = dict(document, confirmed_fields=confirmations, journey_reviewed=True)
        try:
            save_document(st.session_state.current_client_id, document_id, updated)
        except Exception:
            st.error("La sauvegarde a échoué. Vos saisies sont conservées ; réessayez.")
            return
        document.update(updated)
        st.session_state.current_doc_id = None
        st.session_state.last_result = None
        st.session_state.confirmed_fields = {}
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


def _clear_document_session(documents):
    """Retire l'état lié aux justificatifs sans déconnecter le client."""
    document_ids = tuple(documents)
    client_id = st.session_state.current_client_id
    for key in list(st.session_state):
        key_text = str(key)
        if any(document_id in key_text for document_id in document_ids):
            st.session_state.pop(key, None)
        elif key_text.startswith(f"declared_{client_id}_"):
            st.session_state.pop(key, None)
        elif key_text.startswith((f"verification_table_{client_id}",
                                  f"verification_checked_{client_id}")):
            st.session_state.pop(key, None)
    for key, default in (
        ("current_doc_id", None),
        ("confirmed_fields", {}),
        ("last_result", None),
    ):
        st.session_state[key] = default


@st.dialog("Recommencer avec de nouveaux justificatifs")
def reset_documents_dialog():
    """Demande une confirmation avant la réinitialisation du dossier documentaire."""
    documents = current_client_documents()
    st.warning(
        "Cette action supprimera tous vos justificatifs ainsi que les informations "
        "extraites, corrigées et confirmées à partir de ces documents."
    )
    st.info("Votre compte client et les informations de votre projet immobilier seront conservés.")
    confirmed = st.checkbox(
        "Je comprends que les justificatifs devront être déposés et vérifiés de nouveau",
        key="confirm_reset_all_documents",
    )
    if st.button(
        "Supprimer les justificatifs",
        icon=":material/delete_sweep:",
        type="primary",
        width="stretch",
        disabled=not confirmed,
        key="reset_all_documents_confirm",
    ):
        try:
            stored_paths = delete_all_documents(st.session_state.current_client_id)
        except Exception as exc:
            st.error(f"Réinitialisation impossible : {exc}")
            return
        session_paths = [document.get("document_path") for document in documents.values()]
        failures = _remove_uploaded_files(stored_paths + session_paths)
        _clear_document_session(documents)
        st.session_state.compromis_skipped = False
        for document_id in documents:
            st.session_state.documents.pop(document_id, None)
        audit.log_event(
            "client_documents_reset",
            advisor_id=f"client_portal_{st.session_state.session_id[:8]}",
            session_id=st.session_state.session_id,
            decision="confirme_par_client",
            details={"documents_supprimes": len(documents), "fichiers_non_supprimes": failures},
        )
        st.session_state.documents_reset_notice = (
            "Vos anciens justificatifs et leurs informations ont été supprimés. "
            "Vous pouvez déposer les nouveaux documents."
        )
        st.rerun()


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


def _confirmed_candidates(documents, field):
    candidates = []
    for document_id, document in documents.items():
        record = (document.get("confirmed_fields") or {}).get(field)
        if not isinstance(record, dict):
            continue
        if record.get("document_id") != document_id:
            continue
        if record.get("status") not in ("confirme", "corrige"):
            continue
        if record.get("value") is None:
            continue
        candidates.append({
            "document_id": document_id,
            "filename": document.get("filename") or "Document",
            "value": record["value"],
            "record": record,
        })
    return candidates


def render_conflict_resolution(documents, rows, advisor_id):
    """Laisse le client choisir explicitement la source à conserver."""
    conflicts = [row for row in rows if row.get("Statut") == "Conflit"]
    if not conflicts:
        return
    st.subheader("Résoudre les informations contradictoires")
    st.warning(
        "Deux justificatifs contiennent des valeurs différentes. Choisissez la valeur "
        "qui correspond à votre situation actuelle après consultation des documents."
    )
    for row in conflicts:
        field = row["field"]
        candidates = _confirmed_candidates(documents, field)
        if len(candidates) < 2:
            continue
        with st.container(border=True):
            st.markdown(f"**{row['Champ']}**")
            st.dataframe(
                [{
                    "Valeur": str(candidate["value"]),
                    "Justificatif": candidate["filename"],
                    "Page": str((candidate["record"].get("source") or {}).get("page") or "—"),
                    "Extrait": str((candidate["record"].get("source") or {}).get("quote") or "—"),
                } for candidate in candidates],
                hide_index=True,
                width="stretch",
            )
            choice = st.selectbox(
                "Valeur à conserver",
                options=range(len(candidates)),
                format_func=lambda index: (
                    f"{candidates[index]['value']} — {candidates[index]['filename']}"
                ),
                key=f"conflict_choice_{field}",
            )
            checked = st.checkbox(
                "J'ai comparé les justificatifs et je confirme ce choix",
                key=f"conflict_checked_{field}",
            )
            if st.button(
                "Conserver cette valeur",
                icon=":material/check_circle:",
                type="primary",
                disabled=not checked,
                key=f"resolve_conflict_{field}",
            ):
                selected = candidates[choice]
                discarded = []
                for candidate in candidates:
                    if candidate["document_id"] == selected["document_id"]:
                        continue
                    document = documents[candidate["document_id"]]
                    (document.get("confirmed_fields") or {}).pop(field, None)
                    save_document(
                        st.session_state.current_client_id,
                        candidate["document_id"],
                        document,
                    )
                    discarded.append({
                        "document": candidate["filename"],
                        "value": candidate["value"],
                    })
                audit.log_event(
                    "client_conflict_resolved",
                    advisor_id=advisor_id,
                    session_id=st.session_state.session_id,
                    document_path=selected["filename"],
                    field_name=field,
                    value=selected["value"],
                    decision="valeur_conservee_par_client",
                    details={"valeurs_ecartees": discarded},
                )
                st.toast("Conflit résolu et choix sauvegardé.", icon=":material/check_circle:")
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
    available_types = {
        document.get("type") for document in documents.values()
        if document.get("status") == "completed"
    }
    missing.extend(label for doc_type, label in required_documents.items()
                   if doc_type not in available_types)
    return documents, rows, business_complete and not missing, missing


def render_application_sidebar():
    """Navigation bancaire courte, guidée et compréhensible sans jargon."""
    account_ready = bool(st.session_state.account_created)
    documents = current_client_documents() if account_ready else {}
    completed_types = {
        document.get("type") for document in documents.values()
        if document.get("status") == "completed"
    }
    missing_document_count = len(
        {"carte_identite", "bulletin", "releve"} - completed_types
    )
    required_types = {"carte_identite", "bulletin", "releve"}
    documents_ready = required_types.issubset(completed_types)

    saved_project = {}
    if account_ready:
        try:
            saved_project = load_project(st.session_state.current_client_id) or {}
        except Exception:
            saved_project = {}
    project_ready = bool(saved_project)

    dossier_complete = False
    if account_ready:
        _, _, dossier_complete, _ = dossier_readiness()
    completed_steps = sum((project_ready, documents_ready, dossier_complete, dossier_complete))
    progress_percent = int(completed_steps / 4 * 100)

    logo = Path("assets/logo_ca.jpg")
    with st.container(key="sidebar_brand"):
        logo_column, title_column = st.columns([1, 2.8], vertical_alignment="center")
        with logo_column:
            if logo.is_file():
                st.image(str(logo), width=58)
            else:
                st.markdown(":material/account_balance:")
        with title_column:
            st.markdown("**Crédit Agricole  \\\ndu Maroc**")

    with st.container(key="sidebar_intro"):
        st.markdown("## Crédit Habitat")
        st.caption("Votre projet, étape par étape")

    with st.container(key="sidebar_progress"):
        if not account_ready:
            next_step = "Connectez-vous pour préparer votre dossier."
        elif not project_ready:
            next_step = "Prochaine étape : renseigner votre projet."
        elif not documents_ready:
            next_step = "Prochaine étape : ajouter vos justificatifs."
        elif not dossier_complete:
            next_step = "Prochaine étape : vérifier vos informations."
        else:
            next_step = "Votre simulation est prête."
        st.markdown(
            f"""
            <div class="sidebar-progress-head">
                <span>Avancement du dossier</span>
                <span>{progress_percent} %</span>
            </div>
            <div class="sidebar-progress-track">
                <div class="sidebar-progress-fill" style="width:{progress_percent}%"></div>
            </div>
            <div class="sidebar-progress-copy">{next_step}</div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown('<div class="sidebar-section-label">VOTRE PARCOURS</div>', unsafe_allow_html=True)
    with st.container(key="sidebar_nav"):
        if st.button(
            "01  Mon projet",
            icon=":material/home:",
            width="stretch",
            type="primary" if st.session_state.page == "Accueil" else "secondary",
            disabled=st.session_state.processing,
            key="sidebar_overview",
        ):
            _go_to("Accueil")
            st.rerun()

        

        if st.button(
            "02  Mes justificatifs", icon=":material/description:", width="stretch",
            type="primary" if st.session_state.page == "Extraction" else "secondary",
            disabled=st.session_state.processing or not account_ready,
            key="sidebar_documents",
        ):
            _go_to("Extraction")
            st.rerun()
        if missing_document_count:
            documents_hint = f"{missing_document_count} document{'s' if missing_document_count > 1 else ''} à ajouter"
        elif documents_ready:
            documents_hint = "Documents enregistrés"
        else:
            documents_hint = "Documents à compléter"
        st.markdown(f'<div class="sidebar-step-hint">{documents_hint}</div>', unsafe_allow_html=True)

        if st.button(
            "03  Vérifier mes informations", icon=":material/fact_check:", width="stretch",
            type="primary" if st.session_state.page == "Verification" else "secondary",
            disabled=st.session_state.processing or not documents_ready,
            key="sidebar_verification",
        ):
            _go_to("Verification")
            st.rerun()
        verification_hint = "Terminé" if dossier_complete else (
            "Prêt à vérifier" if documents_ready else "Disponible après les documents"
        )
        st.markdown(f'<div class="sidebar-step-hint">{verification_hint}</div>', unsafe_allow_html=True)

        if st.button(
            "04  Ma simulation", icon=":material/calculate:", width="stretch",
            type="primary" if st.session_state.page == "Simulation" else "secondary",
            disabled=st.session_state.processing or not dossier_complete,
            key="sidebar_simulation",
        ):
            _go_to("Simulation")
            st.rerun()
        simulation_hint = "Disponible" if dossier_complete else "Disponible après vérification"
        st.markdown(f'<div class="sidebar-step-hint">{simulation_hint}</div>', unsafe_allow_html=True)

    if st.button(
        "Estimation rapide",
        key="sidebar_quick",
        width="stretch",
        icon=":material/calculate:",
        disabled=st.session_state.processing,
    ):
        _go_to("Estimation")
        st.rerun()

    with st.container(key="sidebar_support"):
        if st.button(
            "Une question ? Demandez à Nour",
            icon=":material/help:",
            width="stretch",
            key="sidebar_help",
        ):
            st.session_state.assistant_open = True
            st.rerun()
        with st.expander("Confidentialité", icon=":material/shield:"):
            st.caption("Vos justificatifs servent uniquement à préparer votre simulation.")
            st.caption("Vous gardez le contrôle sur les informations enregistrées.")
        if st.button(
            "Espace conseiller",
            icon=":material/admin_panel_settings:",
            width="stretch",
            key="open_advisor_space",
        ):
            st.session_state.page = "Conseiller"
            st.rerun()
    if account_ready:
        profile = st.session_state.customer_profile
        display_name = " ".join(filter(None, (profile.get("prenom"), profile.get("nom")))).strip()
        initials = "".join(part[:1].upper() for part in display_name.split()[:2]) or "CL"
        safe_display_name = html.escape(display_name or "Mon compte")
        safe_email = html.escape(str(profile.get("email", "")))
        with st.container(key="sidebar_profile"):
            st.markdown(
                f"""
                <div class="sidebar-user-card">
                    <div class="sidebar-user-name">{initials} · {safe_display_name}</div>
                    <div class="sidebar-user-email">{safe_email}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            logout = st.button(
                "Se déconnecter",
                icon=":material/logout:",
                width="stretch",
                key="sidebar_logout",
            )
            if logout:
                for key in (
                    "documents", "current_doc_id", "confirmed_fields", "last_result",
                    "chat_history", "credit_profile", "customer_profile",
                    "compromis_skipped",
                ):
                    st.session_state.pop(key, None)
                st.session_state.account_created = False
                st.session_state.current_client_id = None
                st.session_state.page = "Accueil"
                st.rerun()




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
            "Données protégées · Validation par vos soins",
        )
        render_home_assurance_strip()
        st.stop()

    client_docs = current_client_documents()
    completed_types = completed_document_types(client_docs)
    required_types = {"carte_identite", "bulletin", "releve"}
    completed_required = len(required_types & completed_types)
    documents_ready = required_types.issubset(completed_types)
    _, summary_rows, dossier_complete, missing_items = dossier_readiness()
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
        hero_badge = "DOSSIER COMPLET · INFORMATIONS VÉRIFIÉES"
    elif completed_required:
        hero_title = "Reprenez votre projet là où vous l’avez laissé."
        hero_text = (
            "Votre dossier est sauvegardé. Finalisez les justificatifs et vérifiez "
            "les informations détectées avant de lancer la simulation."
        )
        hero_badge = f"{completed_required}/3 JUSTIFICATIFS TRAITÉS"
    else:
        hero_title = "Construisez votre projet immobilier en toute simplicité."
        hero_text = (
            "Déposez vos justificatifs, contrôlez les informations détectées et "
            "obtenez une estimation personnalisée de votre financement."
        )
        hero_badge = "PARCOURS SÉCURISÉ · VALIDATION PAR LE CLIENT"

    render_cam_hero(
        "Crédit habitat · Espace personnel",
        hero_title,
        hero_text,
        hero_badge,
    )
    render_home_assurance_strip()

    # -----------------------------------------------------
    # SYNTHÈSE OU FORMULAIRE DU PROJET
    # -----------------------------------------------------

    editing_project = st.session_state.get("editing_home_project", False)

    if saved_project and not editing_project:
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
                    st.session_state.editing_home_project = True
                    st.rerun()

            project_metrics = st.columns(4)
            project_metrics[0].metric(
                "Ville", saved_project.get("city") or "À préciser", border=True
            )
            project_metrics[1].metric(
                "Type de bien", saved_project.get("property_type") or "À préciser", border=True
            )
            project_metrics[2].metric(
                "Budget",
                f"{float(saved_project.get('purchase_price') or 0):,.0f} MAD",
                border=True,
            )
            project_metrics[3].metric(
                "Durée",
                f"{int(saved_project.get('duration_years') or 20)} ans",
                border=True,
            )

    if not saved_project or editing_project:
        with st.container(key="home_project_summary", border=True):
            st.markdown("### Personnaliser mon projet")
            st.caption("Ces informations seront reprises automatiquement dans vos simulations.")
            with st.form("housing_project_profile"):
                project_left, project_right = st.columns(2)
                city = project_left.text_input(
                    "Ville du projet", value=saved_project.get("city") or ""
                )
                property_options = ["Appartement", "Maison", "Terrain + construction", "Autre"]
                saved_type = saved_project.get("property_type") or property_options[0]
                property_type = project_right.selectbox(
                    "Type de bien", property_options,
                    index=property_options.index(saved_type) if saved_type in property_options else 0,
                )
                purchase_price = project_left.number_input(
                    "Budget estimé (MAD)", min_value=0.0,
                    value=float(saved_project.get("purchase_price") or 600000), step=10000.0,
                )
                contribution = project_right.number_input(
                    "Apport personnel (MAD)", min_value=0.0,
                    value=float(saved_project.get("contribution") or 100000), step=5000.0,
                )
                duration_years = st.slider(
                    "Durée souhaitée", 5, 30,
                    int(saved_project.get("duration_years") or 20), format="%d ans",
                )
                save_project_button = st.form_submit_button(
                    "Enregistrer mon projet", type="primary", width="stretch"
                )
            if save_project_button:
                if contribution > purchase_price:
                    st.error("L'apport ne peut pas dépasser le prix estimé du bien.")
                else:
                    save_project(
                        st.session_state.current_client_id, city.strip(), property_type,
                        purchase_price, contribution, duration_years,
                    )
                    st.session_state.editing_home_project = False
                    st.toast("Votre projet est enregistré.", icon=":material/check_circle:")
                    st.rerun()

    # -----------------------------------------------------
    # ACTIONS CONTEXTUELLES
    # -----------------------------------------------------

    if dossier_complete:
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
                "Votre budget, votre apport et la durée sont enregistrés."
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
# PAGE EXTRACTION AMÉLIORÉE AVEC GESTION MULTI-DOCUMENTS
# =========================================================

elif st.session_state.page == "Extraction":
    if not st.session_state.account_created:
        st.session_state.page = "Accueil"
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

    journey_step = credit_journey_step(client_docs)
    _, _, dossier_complete, _ = dossier_readiness()

    # Un dossier finalisé reste entièrement consultable depuis « Mes documents ».
    # L'étape 6 sert uniquement à afficher toutes les coches dans ce cas.
    render_credit_journey(6 if dossier_complete else journey_step)
    st.divider()
    
    with st.expander("Voir et modifier mes documents", expanded=dossier_complete):
        if client_docs:

            # Afficher les documents dans une grille
            cols = st.columns(2)
            for idx, (doc_id, doc_data) in enumerate(client_docs.items()):
                col = cols[idx % 2]
                with col:
                    is_active = doc_id == st.session_state.current_doc_id
                    status = doc_data.get('status', 'inconnu')

                    # Couleur selon le statut
                    status_color = {
                        'completed': '✅',
                        'processing': '⏳',
                        'error': '❌',
                        'inconnu': '⏸️'
                    }.get(status, '⏸️')

                    status_text = {
                        'completed': 'Traité',
                        'processing': 'En cours...',
                        'error': 'Erreur',
                        'inconnu': 'En attente'
                    }.get(status, 'En attente')

                    with st.container(border=True):
                        col_btn, col_status = st.columns([3, 1])
                        with col_btn:
                            if st.button(
                                f"📄 {doc_data.get('filename', 'Document')[:30]}...",
                                key=f"view_{doc_id}",
                                width="stretch",
                            ):
                                st.session_state.current_doc_id = doc_id
                                st.session_state.last_result = doc_data.get('result')
                                st.session_state.confirmed_fields = doc_data.get('confirmed_fields', {})
                                st.rerun()
                        with col_status:
                            st.caption(f"{status_color} {status_text}")

                        # Infos supplémentaires
                        st.caption(f"Type: {doc_data.get('type', 'Inconnu')}")
                        if doc_data.get('timestamp'):
                            st.caption(f"📅 {doc_data.get('timestamp')[:16]}")
                        if st.button(
                            "Supprimer ce justificatif",
                            icon=":material/delete:",
                            key=f"delete_card_{doc_id}",
                            width="stretch",
                        ):
                            delete_one_document_dialog(doc_id)

                    st.write("")  # Espacement

            if st.button(
                "Recommencer avec de nouveaux justificatifs",
                icon=":material/delete_sweep:",
                key="reset_all_documents",
            ):
                reset_documents_dialog()

            st.divider()

    selected = st.session_state.documents.get(st.session_state.current_doc_id)
    if selected and selected.get("status") == "completed" and selected.get("result"):
        render_guided_document_review(st.session_state.current_doc_id, selected, journey_step, advisor_id)
        st.stop()

    if journey_step >= 4:
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

    document_step = DOCUMENT_JOURNEY[journey_step]
    document_type = document_step["type"]

    st.subheader(f"Étape {journey_step + 1} — {document_step['title']}")
    st.write(document_step["instruction"])

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
                key=f"uploader_{st.session_state.current_client_id}_{document_type}",
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
            st.session_state.current_doc_id = None
            st.session_state.last_result = None
            st.session_state.confirmed_fields = {}
            save_document(
                st.session_state.current_client_id, doc_id,
                st.session_state.documents[doc_id],
            )
            st.session_state.journey_notice = (
                f"{document_step['title']} analysé et sauvegardé. Vous pouvez continuer "
                "avec le justificatif suivant."
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

    st.title("Vérifier mes informations")
    st.caption(
        "Retrouvez vos informations déjà corrigées. Vous pouvez les modifier avant votre "
        "simulation."
    )
    render_final_verification(
        client_docs,
        st.session_state.current_client_id,
        advisor_id,
        st.session_state.session_id,
    )
    if st.button("Retourner à mes documents", icon=":material/arrow_back:"):
        st.session_state.page = "Extraction"
        st.rerun()

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

    estimate = None
    capacity = None

    with simulation_tab:
         estimate = render_simulation(
        project=saved_project,
        key_prefix=(
            f"simulation_"
            f"{st.session_state.current_client_id}"
        ),
        income=income,
        existing_monthly_charges=existing_charges,
    )

    with capacity_tab:
         capacity = render_borrowing_capacity(
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

elif st.session_state.page == "Assistant":
    st.title("Comprendre mon crédit habitat")
    
    st.caption(
        "Posez une question sur les offres, les conditions et la préparation de votre projet."
    )
    
    # Actions rapides
    col_new, _ = st.columns([1, 3])
    with col_new:
        if st.button("🆕 Nouvelle conversation", width="stretch"):
            st.session_state.chat_history = []
            st.session_state.credit_profile = {}
            st.rerun()
    
    st.divider()
    
    # -----------------------------------------------------
    # QUESTIONS RAPIDES
    # -----------------------------------------------------
    
    st.caption("⚡ Questions rapides")
    
    quick_1, quick_2, quick_3 = st.columns(3)
    quick_question = None
    
    with quick_1:
        if st.button(
            "📋 Conditions d'éligibilité",
            width="stretch",
            help="Quelles sont les conditions d'éligibilité au crédit habitat ?"
        ):
            quick_question = "Quelles sont les conditions d'éligibilité au crédit habitat ?"
    
    with quick_2:
        if st.button(
            "📎 Documents nécessaires",
            width="stretch",
            help="Quels documents sont nécessaires pour constituer un dossier de crédit habitat ?"
        ):
            quick_question = "Quels documents sont nécessaires pour constituer un dossier de crédit habitat ?"
    
    with quick_3:
        if st.button(
            "💰 Taux du crédit",
            width="stretch",
            help="Quel est le taux d'intérêt du crédit habitat ?"
        ):
            quick_question = "Quel est le taux d'intérêt du crédit habitat ?"
    
    st.write("")
    
    # -----------------------------------------------------
    # HISTORIQUE
    # -----------------------------------------------------
    
    for exchange in st.session_state.chat_history:
        with st.chat_message("user"):
            st.write(exchange["question"])
        
        with st.chat_message("assistant"):
            if exchange.get("mode") == "guidance":
                st.badge(
                    "Accompagnement personnalisé",
                    color="green",
                    icon=":material/account_circle:",
                )
                st.write(exchange["answer"])
            elif exchange.get("in_scope", False):
                st.badge("Réponse documentée", color="green", icon=":material/library_books:")
                st.write(exchange["answer"])
                
                if exchange.get("sources"):
                    with st.expander("📖 Sources utilisées"):
                        for source in exchange["sources"]:
                            st.write(f"• {source}")
            else:
                st.badge("Question hors périmètre", color="orange")
                st.warning(exchange["answer"])
    
    # -----------------------------------------------------
    # QUESTION
    # -----------------------------------------------------
    
    question = st.chat_input("💬 Posez votre question...")
    
    if quick_question:
        question = quick_question
    
    # -----------------------------------------------------
    # EXECUTION
    # -----------------------------------------------------
    
    if question:
        with st.chat_message("user"):
            st.write(question)
        
        with st.chat_message("assistant"):
            with st.spinner("🔍 Recherche dans la documentation..."):
                try:
                    chat_result = get_orchestrator().handle_question(
                        question=question,
                        advisor_id=advisor_id,
                        session_id=st.session_state.session_id,
                        profile=st.session_state.credit_profile,
                        conversation_history=st.session_state.chat_history,
                    )
                except FileNotFoundError:
                    st.error(
                        "❌ Le vectorstore RAG n'existe pas encore. "
                        "Lancez `python -m rag.ingest` après avoir ajouté les documents dans `data/docs/`."
                    )
                    st.stop()
                except Exception as e:
                    st.error(f"❌ Erreur lors du traitement : {str(e)}")
                    st.stop()
            
            if chat_result.get("mode") == "guidance":
                st.badge(
                    "Accompagnement personnalisé",
                    color="green",
                    icon=":material/account_circle:",
                )
                st.write(chat_result["answer"])
            elif chat_result.get("in_scope", False):
                st.badge("Réponse documentée", color="green", icon=":material/library_books:")
                st.write(chat_result["answer"])
                
                if chat_result.get("sources"):
                    with st.expander("📖 Sources utilisées"):
                        for source in chat_result["sources"]:
                            st.write(f"• {source}")
            else:
                st.badge("Question hors périmètre", color="orange")
                st.warning(chat_result["answer"])
        
        # Ajouter à l'historique
        apply_assistant_result(chat_result)
        st.session_state.chat_history.append({
            "question": question,
            "answer": chat_result["answer"],
            "in_scope": chat_result.get("in_scope", False),
            "sources": chat_result.get("sources", []),
            "mode": chat_result.get("mode", "rag"),
            "profile_updates": chat_result.get("profile_updates", {}),
        })
        
        st.rerun()

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
