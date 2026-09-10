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

import json
import logging
import math
import uuid
import time
import pickle
import hashlib
from pathlib import Path
from datetime import datetime

import streamlit as st

from agents.orchestrator import Orchestrator
from config.settings import settings
from database import audit
from database.customer_accounts import (
    authenticate, create_customer, delete_all_documents, delete_document,
    load_documents, load_project, save_document, save_project,
)
from extraction.schema import DOCUMENT_SCHEMAS
from ui.document_review import render_declared_form, render_document_review
from ui.client_summary import build_client_summary, render_client_summary

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
    initial_sidebar_state="expanded",
)

# =========================================================
# CACHE
# =========================================================

@st.cache_resource
def get_orchestrator():
    """Créer l'orchestrator une seule fois (caché)"""
    return Orchestrator()

# =========================================================
# DESIGN - STYLES AMÉLIORÉS
# =========================================================

def inject_app_styles():
    """Appliquer une identité visuelle moderne sans modifier les widgets métier."""
    st.markdown(
        """
        <style>
        :root {
            --ca-green: #007a4d;
            --ca-dark: #073b2c;
            --ca-soft: #edf7f2;
            --ca-border: rgba(15, 63, 47, 0.12);
        }
        .stApp {
            background:
                radial-gradient(circle at 86% 3%, rgba(0, 122, 77, .08), transparent 25rem),
                #f7faf8;
        }
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #073b2c 0%, #0a4b38 55%, #062f24 100%);
            border-right: 0;
        }
        [data-testid="stSidebar"] * {
            color: #f4fbf7;
        }
        [data-testid="stSidebar"] [data-baseweb="input"] > div {
            background: rgba(255,255,255,.10);
            border-color: rgba(255,255,255,.22);
        }
        [data-testid="stSidebar"] input {
            color: #ffffff !important;
        }
        [data-testid="stSidebar"] hr {
            border-color: rgba(255,255,255,.15);
        }
        [data-testid="stSidebar"] .stButton > button {
            min-height: 2.75rem;
            border-radius: .85rem;
            border: 1px solid rgba(255,255,255,.16);
            background: rgba(255,255,255,.06);
            justify-content: flex-start;
            transition: transform .16s ease, background .16s ease, border-color .16s ease;
        }
        [data-testid="stSidebar"] .stButton > button:hover {
            transform: translateX(3px);
            background: rgba(255,255,255,.14);
            border-color: rgba(255,255,255,.30);
        }
        [data-testid="stSidebar"] .stButton > button[kind="primary"] {
            background: #ffffff;
            border-color: #ffffff;
        }
        [data-testid="stSidebar"] .stButton > button[kind="primary"] * {
            color: #073b2c !important;
            font-weight: 700;
        }
        .block-container {
            max-width: 1180px;
            padding-top: 2rem;
            padding-bottom: 3rem;
        }
        .st-key-assistant_dock {
            position: fixed;
            right: 1.25rem;
            bottom: 1.25rem;
            width: min(410px, calc(100vw - 2.5rem));
            max-height: min(760px, calc(100vh - 2.5rem));
            z-index: 9999;
            background-color: #edf7f2 !important;
            border-radius: 1.35rem;
            overflow: hidden;
            box-shadow: 0 22px 65px rgba(7, 59, 44, 0.24);
        }
        .st-key-assistant_dock > div,
        .st-key-assistant_dock [data-testid="stVerticalBlockBorderWrapper"] {
            min-width: 0;
        }
        .st-key-assistant_dock [data-testid="stVerticalBlockBorderWrapper"] {
            overflow: hidden;
            background: #edf7f2;
            border: 1px solid rgba(0, 122, 77, .18);
            border-radius: 1.35rem;
            box-shadow: 0 22px 65px rgba(7, 59, 44, .24);
            backdrop-filter: blur(16px);
        }
        .st-key-assistant_launcher {
            position: fixed;
            right: 1.25rem;
            bottom: 1.25rem;
            width: 235px;
            z-index: 9999;
        }
        .st-key-assistant_launcher button {
            min-height: 3.5rem;
            border: 0;
            border-radius: 999px;
            color: #ffffff;
            background: linear-gradient(120deg, #073b2c 0%, #007a4d 100%);
            box-shadow: 0 14px 35px rgba(7, 59, 44, .28);
            font-weight: 750;
        }
        .st-key-assistant_launcher button:hover {
            transform: translateY(-2px);
            box-shadow: 0 18px 42px rgba(7, 59, 44, .34);
        }
        .st-key-assistant_close button {
            width: 2.55rem;
            min-width: 2.55rem;
            height: 2.55rem;
            min-height: 2.55rem;
            padding: 0;
            border-radius: 999px;
            font-size: 1.35rem;
            line-height: 1;
        }
        .st-key-assistant_dock [data-testid="stChatMessage"] {
            padding-block: .7rem;
        }
        .st-key-assistant_dock [data-testid="stChatInput"] {
            border-radius: 1rem;
        }
        .st-key-journey_step button {
            min-height: 3.2rem;
        }
        @media (max-width: 700px) {
            .st-key-assistant_dock {
                right: .65rem;
                left: .65rem;
                bottom: .65rem;
                width: auto;
                max-height: calc(100vh - 1.3rem);
            }
            .st-key-assistant_launcher {
                right: .75rem;
                bottom: .75rem;
                width: min(225px, calc(100vw - 1.5rem));
            }
        }
        .ca-hero {
            padding: 2.1rem 2.2rem;
            border-radius: 1.35rem;
            background: linear-gradient(120deg, #073b2c 0%, #007a4d 68%, #1d9d69 100%);
            color: white;
            box-shadow: 0 18px 46px rgba(7,59,44,.18);
            margin-bottom: 1.4rem;
        }
        .ca-eyebrow {
            font-size: .76rem;
            font-weight: 800;
            letter-spacing: .12em;
            opacity: .78;
            margin-bottom: .55rem;
        }
        .ca-hero h1 {
            color: white;
            font-size: clamp(2rem, 4vw, 3.2rem);
            line-height: 1.05;
            margin: 0 0 .7rem;
        }
        .ca-hero p {
            max-width: 760px;
            font-size: 1.05rem;
            opacity: .9;
            margin: 0;
        }
        .ca-section-title {
            margin: 2.1rem 0 .25rem;
            color: #073b2c;
            font-size: 1.5rem;
            font-weight: 800;
        }
        .journey-note {
            padding: .85rem 1rem;
            border-radius: .9rem;
            background: #edf7f2;
            border: 1px solid rgba(0,122,77,.16);
            color: #164a38;
        }
        .ca-article {
            min-height: 235px;
            padding: 1.35rem;
            border-radius: 1.1rem;
            background: rgba(255,255,255,.92);
            border: 1px solid var(--ca-border);
            box-shadow: 0 10px 28px rgba(7,59,44,.07);
        }
        .ca-article:hover {
            transform: translateY(-3px);
            box-shadow: 0 16px 36px rgba(7,59,44,.11);
            transition: all .18s ease;
        }
        .ca-article .icon {
            display: inline-grid;
            place-items: center;
            width: 2.55rem;
            height: 2.55rem;
            border-radius: .8rem;
            background: var(--ca-soft);
            font-size: 1.25rem;
        }
        .ca-article h3 {
            color: #073b2c;
            margin: .95rem 0 .45rem;
            font-size: 1.08rem;
        }
        .ca-article p {
            color: #52645d;
            font-size: .92rem;
            line-height: 1.55;
        }
        .ca-tag {
            display: inline-block;
            margin-top: .7rem;
            color: #007a4d;
            font-size: .78rem;
            font-weight: 800;
        }
        div[data-testid="stMetric"] {
            background: rgba(255,255,255,.92);
            border: 1px solid var(--ca-border);
            border-radius: 1rem;
            padding: .75rem 1rem;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-color: var(--ca-border);
            border-radius: 1rem;
            background: rgba(255,255,255,.88);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_header():
    """Afficher l'identité institutionnelle."""
    logo = Path("assets/logo_ca.jpg")
    if logo.is_file():
        st.logo(str(logo), size="large")
    st.caption("CRÉDIT AGRICOLE DU MAROC  ·  MON PROJET HABITAT")


def render_article_card(icon, title, text, tag):
    """Afficher une carte éditoriale compacte sur l'accueil."""
    st.markdown(
        f"""
        <article class="ca-article">
            <div class="icon">{icon}</div>
            <h3>{title}</h3>
            <p>{text}</p>
            <span class="ca-tag">{tag}</span>
        </article>
        """,
        unsafe_allow_html=True,
    )


def _go_to(page):
    st.session_state.page = page


def current_client_documents():
    return {
        doc_id: document for doc_id, document in st.session_state.documents.items()
        if document.get("client_id") == st.session_state.current_client_id
    }


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


def render_customer_journey():
    """Parcours permanent : le client sait toujours où il se trouve."""
    documents, _, dossier_complete, _ = dossier_readiness()
    account_ready = st.session_state.account_created
    has_documents = bool(documents)
    has_result = st.session_state.last_result is not None
    current_page = st.session_state.page

    st.caption("VOTRE PARCOURS DE SIMULATION")
    steps = st.columns(5, gap="small")
    definitions = [
        ("1. Mon espace", "Accueil", True, not account_ready, ":material/person:"),
        ("2. Mon offre", "Accueil", account_ready, account_ready and current_page == "Accueil", ":material/home:"),
        ("3. Mes documents", "Extraction", account_ready, current_page == "Extraction" and not has_result, ":material/upload_file:"),
        ("4. Vérification", "Extraction", has_documents, current_page == "Extraction" and has_result, ":material/fact_check:"),
        ("5. Ma simulation", "Simulation", dossier_complete, current_page == "Simulation", ":material/calculate:"),
    ]
    for column, (label, page, enabled, active, icon) in zip(steps, definitions):
        with column:
            st.button(
                label,
                icon=icon,
                type="primary" if active else "secondary",
                disabled=st.session_state.processing or not enabled,
                width="stretch",
                key=f"journey_{label}",
                on_click=_go_to,
                args=(page,),
            )

    completed = int(account_ready) + int(has_documents) + int(has_result) + int(dossier_complete)
    st.progress(completed / 4, text=f"Progression du dossier : {completed}/4 étapes terminées")


def render_assistant_dock(advisor_id):
    """Afficher un assistant flottant lisible sur ordinateur et mobile."""
    robot_path = Path(__file__).resolve().parent / "assets" / "assistant_habitat_robot.png"
    assistant_avatar = str(robot_path) if robot_path.exists() else ":material/smart_toy:"

    if not st.session_state.assistant_open:
        with st.container(key="assistant_launcher"):
            if st.button(
                "Nour · Assistant habitat",
                icon=":material/smart_toy:",
                key="open_assistant_dock",
                width="stretch",
                help="Ouvrir votre assistant virtuel",
            ):
                st.session_state.assistant_open = True
                st.rerun()
        return

    with st.container(key="assistant_dock", border=True):
        avatar_col, title_col, close_col = st.columns(
            [1.2, 5.6, 1],
            vertical_alignment="center",
        )
        with avatar_col:
            if robot_path.exists():
                st.image(str(robot_path), width=54)
            else:
                st.markdown(":material/smart_toy:")
        with title_col:
            st.markdown("**Nour, votre assistant habitat**")
            st.caption("En ligne · Je vous accompagne étape par étape")
        with close_col:
            if st.button(
                "×",
                key="assistant_close",
                help="Fermer l’assistant",
                width="content",
            ):
                st.session_state.assistant_open = False
                st.rerun()

        history = st.session_state.chat_history[-6:]
        if not history:
            st.write("Bonjour ! Comment puis-je vous aider dans votre projet immobilier ?")
            suggestions = {
                "Documents à préparer": "Quels documents dois-je préparer pour ma simulation ?",
                "Estimer ma mensualité": "Comment est calculée la mensualité de mon crédit habitat ?",
                "Étapes de la simulation": "Quelles sont les étapes pour obtenir ma simulation ?",
            }
            selected = st.pills(
                "Questions suggérées",
                list(suggestions),
                label_visibility="collapsed",
                key="assistant_dock_suggestions",
            )
            suggested_question = suggestions.get(selected)
        else:
            suggested_question = None
            with st.container(height=320, border=False):
                for exchange in history:
                    with st.chat_message("user", avatar=":material/person:"):
                        st.write(exchange["question"])
                    with st.chat_message("assistant", avatar=assistant_avatar):
                        st.write(exchange["answer"])

        question = st.chat_input(
            "Posez votre question…",
            key="assistant_dock_input",
            disabled=st.session_state.processing,
            submit_mode="disable",
        )
        question = question or suggested_question
        if not question:
            return

        with st.spinner("Nour prépare votre réponse…"):
            try:
                answer = orchestrator.handle_question(
                    question=question,
                    advisor_id=advisor_id,
                    session_id=st.session_state.session_id,
                )
            except FileNotFoundError:
                st.error("La base documentaire n’est pas encore disponible.")
                return
            except Exception as exc:
                logging.exception("Assistant indisponible")
                st.error(f"L’assistant est momentanément indisponible : {exc}")
                return

        st.session_state.chat_history.append({
            "question": question,
            "answer": answer["answer"],
            "in_scope": answer.get("in_scope", False),
            "sources": answer.get("sources", []),
        })
        st.rerun()


# =========================================================
# FONCTIONS UTILITAIRES
# =========================================================


def validate_file(uploaded_file):
    """Valider le fichier uploadé"""
    if uploaded_file is None:
        return False, "Aucun fichier sélectionné"
    
    # Vérifier la taille
    if uploaded_file.size > settings.max_file_size_mb * 1024 * 1024:
        return False, f"Fichier trop volumineux (max {settings.max_file_size_mb} MB)"
    
    # Vérifier l'extension
    file_ext = Path(uploaded_file.name).suffix.lower()
    if file_ext not in settings.allowed_extensions:
        return False, f"Format non supporté. Formats acceptés : {', '.join(settings.allowed_extensions)}"
    
    # Vérifier le type MIME (optionnel)
    try:
        import magic
        mime = magic.from_buffer(uploaded_file.getvalue(), mime=True)
        allowed_mime = ['application/pdf', 'image/jpeg', 'image/png', 'image/tiff']
        if mime not in allowed_mime:
            return False, f"Type MIME non supporté : {mime}"
    except Exception:
        # Si python-magic n'est pas disponible, on ignore cette vérification
        pass
    
    return True, "OK"


def count_pdf_pages(uploaded_file):
    """Compter les pages d'un PDF envoyé sans l'écrire sur le disque."""
    import fitz

    document = fitz.open(stream=uploaded_file.getvalue(), filetype="pdf")
    try:
        return document.page_count
    finally:
        document.close()


def save_document_files(uploaded_files, document_type, doc_id):
    """Sauvegarder un document simple ou fusionner le recto-verso d'une CNIE."""
    files = list(uploaded_files or [])
    if not files:
        raise ValueError("Aucun fichier à sauvegarder")

    if len(files) == 1:
        extension = Path(files[0].name).suffix.lower()
        saved_path = UPLOAD_DIR / f"{doc_id}{extension}"
        saved_path.write_bytes(files[0].getvalue())
        return saved_path

    if document_type != "carte_identite" or len(files) != 2:
        raise ValueError("Seule la carte d'identité accepte deux fichiers")

    # PyMuPDF permet de produire un PDF unique quelle que soit la combinaison
    # choisie par l'utilisateur : image+image, PDF+image ou PDF+PDF.
    import fitz

    saved_path = UPLOAD_DIR / f"{doc_id}.pdf"
    combined = fitz.open()
    try:
        for uploaded in files:
            extension = Path(uploaded.name).suffix.lower().lstrip(".")
            source = fitz.open(stream=uploaded.getvalue(), filetype=extension)
            try:
                if source.is_pdf:
                    combined.insert_pdf(source)
                else:
                    image_pdf = fitz.open("pdf", source.convert_to_pdf())
                    try:
                        combined.insert_pdf(image_pdf)
                    finally:
                        image_pdf.close()
            finally:
                source.close()

        if combined.page_count != 2:
            raise ValueError(
                "Le document recto-verso doit produire exactement deux pages "
                f"(pages détectées : {combined.page_count})"
            )
        combined.save(saved_path, garbage=4, deflate=True)
    finally:
        combined.close()
    return saved_path

def save_session_state():
    """Sauvegarder l'état de la session"""
    try:
        session_dir = Path("data/sessions")
        session_dir.mkdir(parents=True, exist_ok=True)
        
        session_file = session_dir / f"session_{st.session_state.session_id}.pkl"
        with open(session_file, "wb") as f:
            # Exclure les objets non sérialisables
            state_to_save = {
                k: v for k, v in st.session_state.items()
                if not k.startswith("_") and not callable(v)
            }
            pickle.dump(state_to_save, f)
        return True
    except Exception as e:
        logging.error(f"Erreur lors de la sauvegarde de la session : {e}")
        return False

def load_session_state(session_id):
    """Restaurer l'état de la session"""
    try:
        session_file = Path("data/sessions") / f"session_{session_id}.pkl"
        if session_file.exists():
            with open(session_file, "rb") as f:
                saved_state = pickle.load(f)
                for key, value in saved_state.items():
                    if key not in ["orchestrator", "_orchestrator"]:
                        st.session_state[key] = value
            return True
    except Exception as e:
        logging.error(f"Erreur lors de la restauration de la session : {e}")
    return False



def request_document_analysis():
    """Verrouiller avant le rendu ; un second clic ne crée aucune demande."""
    if not st.session_state.processing:
        st.session_state.processing = True
        st.session_state.analysis_requested = True


def process_document_with_progress(file_path, document_type, declared_data, advisor_id, session_id):
    """Indicateur réel d'activité, sans pourcentage simulé."""
    with st.status("Analyse du document en cours", expanded=True) as status:
        st.write("Lecture OCR, extraction et vérifications. Le délai dépend du nombre de pages.")
        st.caption("Patientez sans relancer l'analyse ; les résultats apparaîtront à la fin.")
        try:
            result = orchestrator.handle_document(
                pdf_path=str(file_path), document_type=document_type,
                advisor_id=advisor_id, session_id=session_id, declared_data=declared_data,
            )
        except Exception:
            status.update(label="L'analyse n'a pas abouti", state="error")
            raise
        status.update(label="Analyse terminée — résultats prêts à vérifier", state="complete", expanded=False)
        return result


def get_document_summary(doc_data):
    """Obtenir un résumé du document pour l'affichage"""
    filename = doc_data.get('filename', 'Document')
    doc_type = doc_data.get('type', 'Inconnu')
    status = doc_data.get('status', 'inconnu')
    
    status_icon = {
        'completed': '✅',
        'processing': '⏳',
        'error': '❌',
        'inconnu': '⏸️'
    }.get(status, '⏸️')
    
    return f"{status_icon} {filename} ({doc_type})"

# =========================================================
# INITIALISATION
# =========================================================

UPLOAD_DIR = Path("data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

orchestrator = get_orchestrator()

# =========================================================
# SESSION STATE - INITIALISATION AMÉLIORÉE
# =========================================================

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

if "documents" not in st.session_state:
    st.session_state.documents = {}  # Structure: {doc_id: {"type": ..., "data": ...}}

if "current_doc_id" not in st.session_state:
    st.session_state.current_doc_id = None

if "current_client_id" not in st.session_state or not st.session_state.current_client_id:
    # Identifiant technique interne : le client n'a rien à saisir pour démarrer.
    st.session_state.current_client_id = f"client-{st.session_state.session_id[:8]}"

if "confirmed_fields" not in st.session_state:
    st.session_state.confirmed_fields = {}

if "last_result" not in st.session_state:
    st.session_state.last_result = None

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

if "page" not in st.session_state:
    st.session_state.page = "Accueil"

if "theme" not in st.session_state:
    st.session_state.theme = "light"

if "processing" not in st.session_state:
    st.session_state.processing = False

if "last_error" not in st.session_state:
    st.session_state.last_error = None

if "assistant_open" not in st.session_state:
    st.session_state.assistant_open = False

if "account_created" not in st.session_state:
    st.session_state.account_created = False

if "customer_profile" not in st.session_state:
    st.session_state.customer_profile = {}

# L'ancienne page de chat est remplacée par l'assistant permanent à droite.
if st.session_state.page == "Assistant":
    st.session_state.page = "Accueil"

# =========================================================
# SIDEBAR AMÉLIORÉE AVEC GESTION CLIENT
# =========================================================

inject_app_styles()

with st.sidebar:
    st.markdown("## Crédit Habitat")
    if st.session_state.account_created:
        st.caption(f"Bonjour {st.session_state.customer_profile.get('prenom', '')}")
    else:
        st.caption("Créez votre espace pour commencer")
    st.divider()

    # Identifiant conservé uniquement pour l'audit interne.
    advisor_id = f"client_portal_{st.session_state.session_id[:8]}"
    st.markdown("**Accès rapide**")
    
    if st.button("Mon projet", icon=":material/home:", width="stretch", type="primary" if st.session_state.page == "Accueil" else "secondary", disabled=st.session_state.processing):
        st.session_state.page = "Accueil"
        st.rerun()
    
    if st.button("Mes documents", icon=":material/description:", width="stretch", type="primary" if st.session_state.page == "Extraction" else "secondary", disabled=st.session_state.processing or not st.session_state.account_created):
        st.session_state.page = "Extraction"
        st.rerun()

    _, _, simulation_ready, _ = dossier_readiness()
    if st.button("Ma simulation", icon=":material/calculate:", width="stretch", type="primary" if st.session_state.page == "Simulation" else "secondary", disabled=st.session_state.processing or not simulation_ready):
        st.session_state.page = "Simulation"
        st.rerun()
    
    with st.expander("Confidentialité", icon=":material/lock:"):
        st.caption("Vos justificatifs servent uniquement à préparer cette simulation.")
        st.caption("Vous gardez le contrôle : chaque information doit être vérifiée avant utilisation.")

    if st.session_state.account_created:
        st.markdown("**Mon compte**")
        st.caption(st.session_state.customer_profile.get("email", ""))
        if st.button("Se déconnecter", icon=":material/logout:", width="stretch"):
            for key in (
                "documents", "current_doc_id", "confirmed_fields", "last_result",
                "chat_history", "customer_profile",
            ):
                st.session_state.pop(key, None)
            st.session_state.account_created = False
            st.session_state.current_client_id = None
            st.session_state.page = "Accueil"
            st.rerun()

# L'assistant public est rendu avant le contenu protégé. Il reste donc
# accessible sur la page de connexion et avant la création d'un compte.
render_assistant_dock(advisor_id)

# =========================================================
# APPLICATION DU THÈME
# =========================================================



# =========================================================
# RENDU DE L'EN-TÊTE
# =========================================================

render_header()
render_customer_journey()

# =========================================================
# PAGE ACCUEIL
# =========================================================

if st.session_state.page == "Accueil":
    if not st.session_state.account_created:
        st.markdown(
            """
            <section class="ca-hero">
                <div class="ca-eyebrow">ÉTAPE 1 · ESPACE CLIENT</div>
                <h1>Commençons votre projet habitat.</h1>
                <p>Créez votre espace personnel pour sauvegarder vos justificatifs,
                reprendre votre parcours et accéder à votre simulation.</p>
            </section>
            """,
            unsafe_allow_html=True,
        )
        login_tab, signup_tab = st.tabs(["Se connecter", "Créer un compte"])
        with login_tab:
            with st.form("customer_login", border=True):
                login_email = st.text_input("Adresse e-mail", key="login_email")
                login_password = st.text_input("Mot de passe", type="password", key="login_password")
                login_submit = st.form_submit_button("Se connecter", type="primary", width="stretch")
                if login_submit:
                    customer = authenticate(login_email, login_password)
                    if customer is None:
                        st.error("Adresse e-mail ou mot de passe incorrect.")
                    else:
                        st.session_state.customer_profile = {
                            "prenom": customer["first_name"], "nom": customer["last_name"],
                            "email": customer["email"], "telephone": customer["phone"],
                        }
                        st.session_state.current_client_id = customer["id"]
                        st.session_state.documents = load_documents(customer["id"])
                        st.session_state.account_created = True
                        st.rerun()
        with signup_tab:
            with st.form("customer_signup", border=True):
                left, right = st.columns(2)
                prenom = left.text_input("Prénom *", key="signup_first_name")
                nom = right.text_input("Nom *", key="signup_last_name")
                email = left.text_input("Adresse e-mail *", key="signup_email")
                telephone = right.text_input("Téléphone *", key="signup_phone")
                password = left.text_input("Mot de passe *", type="password", key="signup_password")
                confirmation = right.text_input("Confirmer le mot de passe *", type="password",
                                                key="signup_password_confirmation")
                consent = st.checkbox(
                    "J'accepte que mes informations soient utilisées pour préparer cette simulation."
                )
                submitted = st.form_submit_button(
                    "Créer mon compte", type="primary", width="stretch"
                )
                if submitted:
                    if password != confirmation:
                        st.error("Les deux mots de passe ne correspondent pas.")
                    elif not consent:
                        st.error("Votre accord est nécessaire pour poursuivre.")
                    else:
                        try:
                            customer = create_customer(email, password, prenom, nom, telephone)
                        except ValueError as exc:
                            st.error(str(exc))
                        else:
                            st.session_state.customer_profile = {
                                "prenom": customer["first_name"], "nom": customer["last_name"],
                                "email": customer["email"], "telephone": customer["phone"],
                            }
                            st.session_state.current_client_id = customer["id"]
                            st.session_state.documents = load_documents(customer["id"])
                            st.session_state.account_created = True
                            st.rerun()
        st.caption("Vos identifiants sont enregistrés localement ; le mot de passe n'est jamais stocké en clair.")
        st.stop()

    client_badge = '<span class="ca-tag">SIMULATION PERSONNELLE ET NON CONTRACTUELLE</span>'
    st.markdown(
        f"""
        <section class="ca-hero">
            <div class="ca-eyebrow">CRÉDIT HABITAT · PARCOURS ASSISTÉ</div>
            <h1>Construisez votre projet immobilier<br>en toute simplicité.</h1>
            <p>Déposez vos justificatifs, vérifiez les informations détectées et obtenez
            une première estimation de votre capacité de financement.</p>
            {client_badge}
        </section>
        """,
        unsafe_allow_html=True,
    )

    saved_project = load_project(st.session_state.current_client_id) or {}
    with st.expander("Personnaliser mon projet habitat", expanded=not bool(saved_project)):
        with st.form("housing_project_profile"):
            project_left, project_right = st.columns(2)
            city = project_left.text_input("Ville du projet", value=saved_project.get("city") or "")
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
                "Durée souhaitée", 5, 30, int(saved_project.get("duration_years") or 20),
                format="%d ans",
            )
            if st.form_submit_button("Enregistrer mon projet", type="primary", width="stretch"):
                if contribution > purchase_price:
                    st.error("L'apport ne peut pas dépasser le prix estimé du bien.")
                else:
                    save_project(
                        st.session_state.current_client_id, city.strip(), property_type,
                        purchase_price, contribution, duration_years,
                    )
                    st.success("Votre projet est enregistré dans votre compte.")

    action_left, action_right = st.columns([1.15, 0.85], gap="large")
    with action_left.container(border=True, height="stretch"):
        st.markdown("### Une offre adaptée à votre projet")
        st.write("Estimez un financement pour l'acquisition de votre logement, avec une durée et une mensualité adaptées à votre situation.")
        st.caption("Pièce d'identité · Bulletin de paie · Relevé de compte · Compromis")
        if st.button(
            "Simuler mon crédit habitat",
            icon=":material/arrow_forward:",
            type="primary",
            width="stretch",
            disabled=st.session_state.processing,
        ):
            st.session_state.page = "Extraction"
            st.rerun()

    with action_right.container(border=True, height="stretch"):
        st.markdown("### Comprendre le crédit habitat")
        st.write("Posez vos questions sur les offres, les étapes et les documents nécessaires.")
        st.caption("Réponses contextualisées avec sources documentaires")
        if st.button(
            "Poser une question",
            icon=":material/chat:",
            width="stretch",
            disabled=st.session_state.processing,
        ):
            st.session_state.assistant_open = True
            st.rerun()

    st.markdown('<div class="ca-section-title">À découvrir</div>', unsafe_allow_html=True)
    st.caption("Des repères simples pour mieux comprendre le parcours et préparer le projet immobilier.")
    article_1, article_2, article_3 = st.columns(3, gap="medium")
    with article_1:
        render_article_card(
            "🏠",
            "Bien préparer son projet habitat",
            "Budget, apport, durée et mensualité : les points à clarifier avant de constituer un dossier.",
            "GUIDE PRATIQUE",
        )
    with article_2:
        render_article_card(
            "📄",
            "Les pièces à fournir",
            "Découvrez les justificatifs utiles et pourquoi leur lisibilité accélère l'étude du financement.",
            "DOSSIER CLIENT",
        )
    with article_3:
        render_article_card(
            "🛡️",
            "Comprendre l'étude du dossier",
            "Découvrez comment vos revenus, vos charges et votre apport influencent une simulation.",
            "TRANSPARENCE",
        )

    st.markdown('<div class="ca-section-title">Activité de la session</div>', unsafe_allow_html=True)
    docs = st.session_state.documents
    cols = st.columns(3)
    cols[0].metric("Documents déposés", len(docs), border=True)
    cols[1].metric(
        "Analyses terminées",
        sum(d.get("status") == "completed" for d in docs.values()),
        border=True,
    )
    cols[2].metric("Questions posées", len(st.session_state.chat_history), border=True)

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
    st.title("Mes justificatifs")
    st.caption("Déposez chaque justificatif, contrôlez son statut, puis vérifiez les informations détectées.")
    reset_notice = st.session_state.pop("documents_reset_notice", None)
    if reset_notice:
        st.success(reset_notice, icon=":material/check_circle:")
    
    # -----------------------------------------------------
    # LISTE DES DOCUMENTS DU CLIENT
    # -----------------------------------------------------
    
    client_docs = {
        doc_id: doc_data 
        for doc_id, doc_data in st.session_state.documents.items()
        if doc_data.get("client_id") == st.session_state.current_client_id
    }
    
    if client_docs:
        render_client_summary(client_docs)
        summary_rows, _ = build_client_summary(client_docs)
        render_conflict_resolution(client_docs, summary_rows, advisor_id)
        st.subheader("Mes documents")
        
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
                
                st.write("")  # Espacement

        with st.container(horizontal=True, horizontal_alignment="right"):
            if st.button(
                "Recommencer avec de nouveaux justificatifs",
                icon=":material/delete_sweep:",
                key="reset_all_documents",
            ):
                reset_documents_dialog()
        
        st.divider()
    
    # -----------------------------------------------------
    # AJOUTER UN NOUVEAU DOCUMENT
    # -----------------------------------------------------
    
    st.subheader("1. Déposer un justificatif")
    
    col_upload, col_data = st.columns([1.1, 0.9], gap="large")
    
    with col_upload:
        document_type = st.selectbox(
            "Type de document",
            options=list(DOCUMENT_SCHEMAS.keys()),
            help="Sélectionnez le type de document pour optimiser l'extraction",
            key="doc_type_select"
        )
        
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
    
    with col_data:
        st.subheader("2. Vérification facultative")
        st.caption("Vous pouvez laisser cette partie vide : le document sera analysé automatiquement.")
        with st.expander("Comparer avec les informations que je connais"):
            declared_data = render_declared_form(document_type, st.session_state.current_client_id)
    
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
    col_buttons = st.columns([1, 1])
    with col_buttons[0]:
        st.button(
            "🚀 Lancer l'analyse",
            type="primary",
            width="stretch",
            disabled=st.session_state.processing or not upload_ready,
            key="launch_document_analysis",
            on_click=request_document_analysis,
        )
    with col_buttons[1]:
        if st.button("🔄 Réinitialiser l'affichage", width="stretch", disabled=st.session_state.processing):
            st.session_state.current_doc_id = None
            st.session_state.last_result = None
            st.session_state.confirmed_fields = {}
            st.rerun()
    
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
            st.session_state.last_result = result
            st.session_state.confirmed_fields = {}
            save_document(
                st.session_state.current_client_id, doc_id,
                st.session_state.documents[doc_id],
            )
            
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
    # RESULTATS DU DOCUMENT SÉLECTIONNÉ
    # -----------------------------------------------------
    
    # Si un document est sélectionné, afficher ses résultats
    if st.session_state.current_doc_id and st.session_state.last_result:
        current_doc = st.session_state.documents.get(st.session_state.current_doc_id)
        
        if current_doc:
            st.divider()
            
            # En-tête du document
            st.subheader(f"Informations détectées — {current_doc.get('filename', 'Document')}")
            st.caption(f"Type: {current_doc.get('type', 'Inconnu')} | {current_doc.get('timestamp', '')[:16]}")
            
            result = st.session_state.last_result
            control_result = result.get("control_result", {})
            
            if not control_result.get("valid", False):
                st.error(f"🚫 Document rejeté : {control_result.get('reason', 'Raison inconnue')}")
            else:
                security = result.get("extraction_security", {})
                
                if security.get("suspicious"):
                    st.warning(
                        "⚠️ Motifs nécessitant une attention : "
                        f"{', '.join(security.get('matched_patterns', []))}"
                    )
                
                validation_result = result.get("validation_result")
                
                if validation_result:
                    fields = validation_result["fields"]
                    
                    total = len(fields)
                    reliable = sum(1 for field in fields.values() if field["status"] == "pre_rempli")
                    review = sum(1 for field in fields.values() if field["status"] == "signale")
                    absent = sum(1 for field in fields.values() if field["status"] == "absent")
                    
                    # Métriques
                    col_1, col_2, col_3, col_4 = st.columns(4)
                    
                    metrics = [
                        (col_1, "📊 Champs détectés", total),
                        (col_2, "Déjà renseignés", reliable),
                        (col_3, "À vérifier", review),
                        (col_4, "À compléter", absent),
                    ]
                    
                    for column, label, value in metrics:
                        with column:
                            st.metric(label, value, border=True)

                    st.write("")
                    
                    if validation_result["needs_priority_review"]:
                        st.warning("Certaines informations demandent votre attention avant de continuer.")
                    else:
                        st.success("Les informations principales ont été détectées.")
                    
                    st.subheader("3. Vérifier mes informations")
                    confirmations = current_doc.setdefault("confirmed_fields", {})
                    render_document_review(
                        result, current_doc["type"], st.session_state.current_doc_id,
                        advisor_id, st.session_state.session_id, confirmations,
                    )
                    st.session_state.confirmed_fields = confirmations
                    save_document(
                        st.session_state.current_client_id,
                        st.session_state.current_doc_id,
                        current_doc,
                    )

                    _, _, dossier_complete, missing_for_simulation = dossier_readiness()
                    if not dossier_complete:
                        st.info(
                            "La simulation sera accessible après vérification de : "
                            + ", ".join(missing_for_simulation)
                        )
                    if st.button(
                        "Continuer vers ma simulation",
                        icon=":material/arrow_forward:",
                        type="primary",
                        width="stretch",
                        disabled=not dossier_complete,
                        key=f"continue_simulation_{st.session_state.current_doc_id}",
                    ):
                        st.session_state.page = "Simulation"
                        st.rerun()
                    
                    # Sections détaillées
                    with st.expander("📄 Voir le texte OCR"):
                        st.text(result.get("ocr_text", ""))
                    
                    with st.expander("⚙️ Détail du moteur de règles"):
                        st.json(validation_result["rule_engine"])
                    
                    with st.expander("📊 Détail des écarts"):
                        st.json(validation_result["discrepancies"])
                    
                    # Bouton pour supprimer le document
                    if st.button("🗑️ Supprimer ce document", width="stretch"):
                        if st.session_state.current_doc_id in st.session_state.documents:
                            del st.session_state.documents[st.session_state.current_doc_id]
                        delete_document(
                            st.session_state.current_client_id,
                            st.session_state.current_doc_id,
                        )
                        st.session_state.current_doc_id = None
                        st.session_state.last_result = None
                        st.session_state.confirmed_fields = {}
                        st.rerun()

# =========================================================
# PAGE SIMULATION CLIENT
# =========================================================

elif st.session_state.page == "Simulation":
    client_docs, readiness_rows, dossier_complete, missing_for_simulation = dossier_readiness()
    if not st.session_state.account_created:
        st.session_state.page = "Accueil"
        st.rerun()
    if not dossier_complete:
        st.title("Votre simulation n'est pas encore disponible")
        st.warning(
            "Vérifiez d'abord les informations indispensables : "
            + ", ".join(missing_for_simulation or ["revenu, ancienneté et charges en cours"])
        )
        if st.button("Retourner à mes documents", type="primary", width="stretch"):
            st.session_state.page = "Extraction"
            st.rerun()
        st.stop()
    st.title("Ma simulation de crédit habitat")
    st.caption("Modifiez les hypothèses pour obtenir une estimation immédiate et non contractuelle.")

    if client_docs:
        render_client_summary(client_docs)
    else:
        st.info("Vous pouvez simuler dès maintenant, puis ajouter vos justificatifs pour compléter l'analyse.")

    with st.container(border=True):
        st.markdown("### Mon projet")
        saved_project = load_project(st.session_state.current_client_id) or {}
        project_left, project_right = st.columns(2)
        with project_left:
            property_value = st.number_input(
                "Prix du bien (MAD)", min_value=0.0,
                value=float(saved_project.get("purchase_price") or 600000),
                step=10000.0, format="%.2f", key="simulation_property_value",
            )
            contribution = st.number_input(
                "Mon apport personnel (MAD)", min_value=0.0,
                value=float(saved_project.get("contribution") or 100000),
                step=5000.0, format="%.2f", key="simulation_contribution",
            )
        with project_right:
            duration_years = st.slider(
                "Durée souhaitée", min_value=5, max_value=30,
                value=int(saved_project.get("duration_years") or 20),
                format="%d ans", key="simulation_duration",
            )
            annual_rate = st.number_input(
                "Taux annuel indicatif (%)", min_value=0.0, max_value=20.0,
                value=4.50, step=0.05, format="%.2f", key="simulation_rate",
                help="Saisissez un taux indicatif. Le taux définitif dépendra de l'offre de la banque.",
            )

    financed_amount = max(property_value - contribution, 0.0)
    months = duration_years * 12
    monthly_rate = annual_rate / 1200
    if financed_amount == 0:
        monthly_payment = total_cost = 0.0
    elif monthly_rate == 0:
        monthly_payment = financed_amount / months
        total_cost = 0.0
    else:
        monthly_payment = financed_amount * monthly_rate / (1 - math.pow(1 + monthly_rate, -months))
        total_cost = monthly_payment * months - financed_amount

    result_1, result_2, result_3 = st.columns(3)
    result_1.metric("Montant à financer", f"{financed_amount:,.2f} MAD", border=True)
    result_2.metric("Mensualité estimée", f"{monthly_payment:,.2f} MAD", border=True)
    result_3.metric("Coût estimé des intérêts", f"{total_cost:,.2f} MAD", border=True)

    if client_docs:
        rows, _ = build_client_summary(client_docs)
        confirmed = {
            row["field"]: row["Valeur confirmée"]
            for row in rows if row["Statut"] == "Confirmé"
        }
        income = confirmed.get("salaire_net")
        current_charges = confirmed.get("charge_mensuelle_credits")
        if income not in (None, 0) and current_charges is not None:
            projected_ratio = (float(current_charges) + monthly_payment) / float(income)
            st.metric("Taux d'endettement projeté", f"{projected_ratio:.2%}", border=True)
            st.caption(
                "Calcul indicatif : (charges de crédits actuelles + mensualité estimée) ÷ revenu mensuel net vérifié."
            )
        else:
            st.info("Vérifiez votre bulletin de paie et votre relevé pour afficher le taux d'endettement projeté.")

    st.warning(
        "Cette simulation est informative. Elle ne constitue ni une offre, ni un accord de crédit. "
        "Le taux, l'assurance, les frais et l'acceptation dépendent de l'étude complète par la banque."
    )


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
            if exchange.get("in_scope", False):
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
                    chat_result = orchestrator.handle_question(
                        question=question,
                        advisor_id=advisor_id,
                        session_id=st.session_state.session_id,
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
            
            if chat_result.get("in_scope", False):
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
        st.session_state.chat_history.append({
            "question": question,
            "answer": chat_result["answer"],
            "in_scope": chat_result.get("in_scope", False),
            "sources": chat_result.get("sources", []),
        })
        
        st.rerun()

# L'assistant est rendu après le contenu mais reste fixé à droite par CSS.

# =========================================================
# FOOTER
# =========================================================

st.divider()
st.caption(
    f"🏦 Crédit Agricole du Maroc — PFE 2026 | "
    f"Session : {st.session_state.session_id[:8]} | "
    f"v1.3.0 | Documents : {len(st.session_state.documents)}"
)

# =========================================================
# GESTION DES ERREURS GLOBALES
# =========================================================

if "error" in st.session_state:
    with st.sidebar:
        st.error(f"⚠️ {st.session_state.error}")
        if st.button("Effacer l'erreur"):
            del st.session_state.error
            st.rerun()
