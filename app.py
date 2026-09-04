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
from extraction.schema import DOCUMENT_SCHEMAS
from ui.document_review import render_declared_form, render_document_review
from ui.client_summary import render_client_summary

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
            max-width: 1280px;
            padding-top: 2rem;
            padding-bottom: 3rem;
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
    st.caption("CRÉDIT AGRICOLE DU MAROC  ·  ESPACE CONSEILLER")


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

if "current_client_id" not in st.session_state:
    st.session_state.current_client_id = ""

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

# =========================================================
# SIDEBAR AMÉLIORÉE AVEC GESTION CLIENT
# =========================================================

inject_app_styles()

with st.sidebar:
    st.markdown("## Crédit Habitat")
    st.caption("Assistant intelligent du conseiller")
    st.divider()

    st.markdown("**Espace de travail**")
    
    advisor_id = st.text_input(
        "Identifiant conseiller",
        value="conseiller_test",
        disabled=st.session_state.processing,
        help="Votre identifiant pour tracer les actions"
    )
    
    st.caption(f"🆔 Session : {st.session_state.session_id[:8]}...")
    
    st.divider()
    
    # Section Client
    st.markdown("**Dossier en cours**")
    
    client_id = st.text_input(
        "Identifiant client",
        value=st.session_state.current_client_id,
        placeholder="Entrez l'ID du client",
        key="active_client_input",
        disabled=st.session_state.processing,
        help="Les documents sont regroupés par client"
    )
    
    if client_id != st.session_state.current_client_id:
        st.session_state.current_client_id = client_id
        # Réinitialiser l'affichage lors du changement de client
        st.session_state.current_doc_id = None
        st.session_state.last_result = None
        st.session_state.confirmed_fields = {}
        st.rerun()
    
    st.divider()
    
    st.markdown("**Navigation**")
    
    if st.button("Accueil", icon=":material/home:", width="stretch", type="primary" if st.session_state.page == "Accueil" else "secondary", disabled=st.session_state.processing):
        st.session_state.page = "Accueil"
        st.rerun()
    
    if st.button("Analyse documentaire", icon=":material/description:", width="stretch", type="primary" if st.session_state.page == "Extraction" else "secondary", disabled=st.session_state.processing):
        st.session_state.page = "Extraction"
        st.rerun()
    
    if st.button("Assistant IA", icon=":material/chat:", width="stretch", type="primary" if st.session_state.page == "Assistant" else "secondary", disabled=st.session_state.processing):
        st.session_state.page = "Assistant"
        st.rerun()
    
    st.divider()
    
    with st.expander("Environnement", icon=":material/info:"):
        st.caption("Traitement local avec OCR et Ollama.")
        st.caption("Les valeurs extraites restent à confirmer par le conseiller.")
        st.caption("Apparence : menu ⋮ → Settings → Theme.")


    # Actions rapides
    st.markdown("**Gestion de la session**")
    
    if st.button("💾 Sauvegarder la session", width="stretch"):
        if save_session_state():
            st.success("✅ Session sauvegardée")
        else:
            st.error("❌ Erreur lors de la sauvegarde")
    
    if st.button("↩️ Restaurer la session", width="stretch"):
        if load_session_state(st.session_state.session_id):
            st.success("✅ Session restaurée")
            st.rerun()
        else:
            st.error("❌ Aucune session sauvegardée")
    
    st.divider()
    
    with st.expander("⚙️ Paramètres techniques"):
        st.caption(f"Confiance minimale : {settings.confidence_threshold}")
        st.caption(f"Écart maximal : {settings.discrepancy_threshold:.0%}")
        st.caption(f"Taille max : {settings.max_file_size_mb} Mo")
        st.caption(f"Similarité RAG : {settings.rag_similarity_threshold}")
    
    # Journal d'activité
    with st.expander("📋 Journal d'activité"):
        try:
            last_actions = audit.get_recent_actions(
                advisor_id=advisor_id,
                limit=10
            ) if hasattr(audit, 'get_recent_actions') else []
            
            if last_actions:
                for action in last_actions[:5]:
                    col_time, col_action = st.columns([1, 2])
                    with col_time:
                        st.caption(action.get('timestamp', '')[:10])
                    with col_action:
                        st.text(action.get('description', '')[:50])
            else:
                st.caption("Aucune activité récente")
        except Exception:
            st.caption("Journal non disponible")

# =========================================================
# APPLICATION DU THÈME
# =========================================================



# =========================================================
# RENDU DE L'EN-TÊTE
# =========================================================

render_header()

# =========================================================
# PAGE ACCUEIL
# =========================================================

if st.session_state.page == "Accueil":
    client_badge = (
        f'<span class="ca-tag">Dossier actif · {st.session_state.current_client_id}</span>'
        if st.session_state.current_client_id
        else '<span class="ca-tag">Renseignez un client pour démarrer</span>'
    )
    st.markdown(
        f"""
        <section class="ca-hero">
            <div class="ca-eyebrow">CRÉDIT HABITAT · PARCOURS ASSISTÉ</div>
            <h1>Un dossier plus clair,<br>une décision mieux préparée.</h1>
            <p>Centralisez les justificatifs, contrôlez les informations extraites
            et retrouvez rapidement les réponses utiles dans la documentation bancaire.</p>
            {client_badge}
        </section>
        """,
        unsafe_allow_html=True,
    )

    action_left, action_right = st.columns([1.15, 0.85], gap="large")
    with action_left.container(border=True, height="stretch"):
        st.markdown("### Préparer un dossier")
        st.write("Déposez les justificatifs du client et vérifiez chaque donnée avant son export.")
        st.caption("Pièce d'identité · Bulletin de paie · Relevé de compte · Compromis")
        if st.button(
            "Lancer une analyse",
            icon=":material/arrow_forward:",
            type="primary",
            width="stretch",
            disabled=st.session_state.processing,
        ):
            st.session_state.page = "Extraction"
            st.rerun()

    with action_right.container(border=True, height="stretch"):
        st.markdown("### Consulter l'assistant")
        st.write("Interrogez les documents de référence sur le crédit habitat.")
        st.caption("Réponses contextualisées avec sources documentaires")
        if st.button(
            "Ouvrir l'assistant",
            icon=":material/chat:",
            width="stretch",
            disabled=st.session_state.processing,
        ):
            st.session_state.page = "Assistant"
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
            "Revenus, charges et cohérence documentaire sont vérifiés avant toute décision du conseiller.",
            "TRANSPARENCE",
        )

    if not st.session_state.current_client_id:
        st.info(
            "Pour commencer une analyse, saisissez l'identifiant du client dans la barre latérale.",
            icon=":material/info:",
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
        st.markdown("**La décision reste humaine**")
        st.caption(
            "L'assistant prépare et justifie les informations. Le conseiller vérifie "
            "les sources et confirme les valeurs avant leur utilisation."
        )


# =========================================================
# PAGE EXTRACTION AMÉLIORÉE AVEC GESTION MULTI-DOCUMENTS
# =========================================================

elif st.session_state.page == "Extraction":
    st.title("Analyse documentaire")
    st.caption("Déposez une pièce, puis vérifiez les informations extraites avant de les exporter.")
    
    # Vérifier que le client est renseigné
    if not st.session_state.current_client_id:
        st.warning("⚠️ Veuillez d'abord renseigner un identifiant client dans la sidebar")
        st.stop()
    
    # Afficher le client actuel
    st.badge(f"Client : {st.session_state.current_client_id}", icon=":material/person:", color="green")
    
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
        st.subheader("Documents du client")
        
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
        
        uploaded_file = st.file_uploader(
            "Déposer un document",
            type=[ext.lstrip(".") for ext in settings.allowed_extensions],
            help=f"Formats acceptés : {', '.join(settings.allowed_extensions)}. Taille max : {settings.max_file_size_mb} MB",
            key=f"uploader_{st.session_state.current_client_id}"
        )
        
        if uploaded_file is not None:
            is_valid, message = validate_file(uploaded_file)
            if is_valid:
                st.success(f"✅ Document sélectionné : {uploaded_file.name}")
                st.caption(f"📦 Taille : {uploaded_file.size / 1024:.1f} KB")
            else:
                st.error(f"⚠️ {message}")
                uploaded_file = None
    
    with col_data:
        st.subheader("2. Informations déclarées")
        
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
            disabled=st.session_state.processing or uploaded_file is None,
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
        
        if uploaded_file is None:
            st.session_state.processing = False
            st.error("⚠️ Déposez un document avant de lancer l'analyse")
            st.stop()
        

        
        # Créer un ID unique pour ce document
        doc_id = str(uuid.uuid4())
        
        # Stocker le document dans la session
        st.session_state.documents[doc_id] = {
            "client_id": st.session_state.current_client_id,
            "type": document_type,
            "filename": uploaded_file.name,
            "timestamp": datetime.now().isoformat(),
            "status": "processing",
            "result": None,
            "confirmed_fields": {},
            "declared_data": declared_data
        }
        
        st.session_state.current_doc_id = doc_id
        
        # Sauvegarder le fichier
        saved_path = UPLOAD_DIR / f"{doc_id}{Path(uploaded_file.name).suffix.lower()}"
        st.session_state.documents[doc_id]["document_path"] = str(saved_path)
        
        # Traiter avec progression
        st.session_state.processing = True
        st.session_state.last_error = None
        
        try:
            saved_path.write_bytes(uploaded_file.getvalue())
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
            st.subheader(f"Résultats — {current_doc.get('filename', 'Document')}")
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
                        (col_2, "✅ Fiables", reliable),
                        (col_3, "⚠️ À vérifier", review),
                        (col_4, "❌ Absents", absent),
                    ]
                    
                    for column, label, value in metrics:
                        with column:
                            st.metric(label, value, border=True)

                    st.write("")
                    
                    if validation_result["needs_priority_review"]:
                        st.warning("🔴 Une revue prioritaire est recommandée.")
                    else:
                        st.success("✅ Aucun point critique détecté.")
                    
                    st.subheader("3. Vérifier et confirmer")
                    confirmations = current_doc.setdefault("confirmed_fields", {})
                    render_document_review(
                        result, current_doc["type"], st.session_state.current_doc_id,
                        advisor_id, st.session_state.session_id, confirmations,
                    )
                    st.session_state.confirmed_fields = confirmations
                    
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
                        st.session_state.current_doc_id = None
                        st.session_state.last_result = None
                        st.session_state.confirmed_fields = {}
                        st.rerun()

# =========================================================
# PAGE ASSISTANT AMÉLIORÉE
# =========================================================

elif st.session_state.page == "Assistant":
    st.title("Assistant documentaire")
    
    st.caption(
        "Posez une question sur les documents officiels indexés dans la base documentaire."
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

