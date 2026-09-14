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
import json
import base64
import logging
import uuid
import time
import pickle
import hashlib
from pathlib import Path
from datetime import datetime

import streamlit as st
import streamlit.components.v1 as components

from config.settings import settings
from database import audit
from database.customer_accounts import (
    authenticate, create_customer, delete_all_documents, delete_document,
    load_documents, load_project, save_document, save_project,
)
from extraction.schema import DOCUMENT_SCHEMAS
from ui.document_review import render_document_review
from ui.simulation import render_simulation
from copy import deepcopy
from ui.client_summary import (
    build_client_summary, render_client_summary, render_final_verification,
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
    initial_sidebar_state="expanded",
)

# =========================================================
# CACHE
# =========================================================

@st.cache_resource
def get_orchestrator():
    """Créer l'orchestrator une seule fois (caché)"""
    from agents.orchestrator import Orchestrator
    return Orchestrator()
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
            background: #f7f9f8;
            border-right: 1px solid #dfe8e3;
            min-width: 310px;
            max-width: 310px;
            box-shadow: 8px 0 28px rgba(7, 59, 44, .06);
        }
        [data-testid="stSidebar"] > div:first-child {
            padding: 1.35rem 1.15rem 1.25rem;
        }
        [data-testid="stSidebar"] * {
            color: #173f32;
        }
        [data-testid="stSidebar"] [data-baseweb="input"] > div {
            background: #ffffff;
            border-color: #cadbd3;
        }
        [data-testid="stSidebar"] input {
            color: #173f32 !important;
        }
        [data-testid="stSidebar"] hr {
            border-color: #dfe8e3;
        }
        [data-testid="stSidebar"] .stButton > button {
            min-height: 3rem;
            border-radius: .75rem;
            border: 1px solid transparent;
            background: transparent;
            justify-content: flex-start;
            padding-inline: .85rem;
            font-weight: 650;
            box-shadow: none;
            transition: background .16s ease, border-color .16s ease;
        }
        [data-testid="stSidebar"] .stButton > button:hover {
            background: #edf5f1;
            border-color: #d3e5dc;
        }
        [data-testid="stSidebar"] .stButton > button[kind="primary"] {
            background: #086b48;
            border-color: #086b48;
        }
        [data-testid="stSidebar"] .stButton > button[kind="primary"] * {
            color: #ffffff !important;
            font-weight: 700;
        }
        .st-key-sidebar_brand {
            padding-bottom: 1rem;
            border-bottom: 1px solid #dfe8e3;
        }
        .st-key-sidebar_brand [data-testid="stImage"] img {
            border-radius: .6rem;
            background: #ffffff;
            padding: .22rem;
        }
        .st-key-sidebar_intro {
            padding: 1.1rem .15rem .45rem;
        }
        .st-key-sidebar_intro h2 {
            margin-bottom: .15rem;
            color: #073b2c;
        }
        .st-key-sidebar_intro p {
            color: #64776f !important;
        }
        .st-key-sidebar_progress {
            margin: .55rem 0 1rem;
            padding: .9rem 1rem;
            border: 1px solid #dce8e2;
            border-radius: .9rem;
            background: #ffffff;
        }
        .st-key-sidebar_progress [data-testid="stProgress"] > div > div {
            background: #0b8a5b;
        }
        .st-key-sidebar_nav {
            padding-top: .2rem;
        }
        .sidebar-step-hint {
            margin: -.45rem .85rem .5rem 2.85rem;
            color: #718078;
            font-size: .75rem;
            line-height: 1.25;
        }
        .st-key-sidebar_support {
            margin-top: 1.25rem;
            padding-top: 1rem;
            border-top: 1px solid #dfe8e3;
        }
        .st-key-sidebar_profile {
            margin-top: .8rem;
            padding-top: 1rem;
            border-top: 1px solid #dfe8e3;
        }
        .st-key-sidebar_profile p {
            margin-bottom: .15rem;
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
            [data-testid="stSidebar"] {
                min-width: min(330px, 88vw);
                max-width: min(330px, 88vw);
            }
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
        .st-key-home_offer_card [data-testid="stVerticalBlockBorderWrapper"],
        .st-key-home_estimate_card [data-testid="stVerticalBlockBorderWrapper"] {
            min-height: 245px;
            padding: .35rem;
        }
        .st-key-home_help_banner [data-testid="stVerticalBlockBorderWrapper"] {
            background: linear-gradient(100deg, #f1f8f5, #ffffff);
            border-color: rgba(0, 122, 77, .18);
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


def image_to_data_url(image_path):
    """Convertir une image locale en URL intégrable dans le carrousel HTML."""
    path = Path(image_path)
    if not path.is_file():
        return ""

    mime_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }
    mime_type = mime_types.get(path.suffix.lower(), "image/png")
    encoded_image = base64.b64encode(path.read_bytes()).decode("utf-8")
    return f"data:{mime_type};base64,{encoded_image}"


def render_offers_carousel():
    """Afficher trois offres avec une image centrale et deux aperçus latéraux."""
    offers = [
        {
            "image": image_to_data_url("assets/offres/offre_habitat.png"),
            "title": "Financez votre projet immobilier",
            "description": (
                "Découvrez une solution de financement adaptée à votre projet "
                "et à votre situation."
            ),
        },
        {
            "image": image_to_data_url("assets/offres/offre_financement.png"),
            "title": "Une simulation simple et personnalisée",
            "description": (
                "Estimez votre mensualité et préparez votre demande de crédit "
                "en quelques étapes."
            ),
        },
        {
            "image": image_to_data_url("assets/offres/accompagnement.png"),
            "title": "Un accompagnement à chaque étape",
            "description": (
                "Notre assistant vous aide à préparer vos documents et à "
                "vérifier vos informations."
            ),
        },
    ]
    offers = [offer for offer in offers if offer["image"]]

    if len(offers) < 3:
        st.warning(
            "Le carrousel nécessite les trois images dans le dossier "
            "assets/offres."
        )
        return

    carousel_html = """
<div class="offer-carousel" id="offerCarousel">
    <div class="carousel-stage">
        <div class="slides-container" id="slidesContainer"></div>
        <button class="carousel-arrow previous" id="previousSlide"
                aria-label="Offre précédente">&#10094;</button>
        <button class="carousel-arrow next" id="nextSlide"
                aria-label="Offre suivante">&#10095;</button>
        <div class="carousel-dots" id="carouselDots"></div>
    </div>
    <div class="carousel-information">
        <div class="carousel-title" id="carouselTitle"></div>
        <div class="carousel-description" id="carouselDescription"></div>
    </div>
</div>

<style>
    * { box-sizing: border-box; }
    html, body {
        margin: 0;
        background: transparent;
        font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    .offer-carousel { width: 100%; padding: 12px 0 4px; overflow: hidden; }
    .carousel-stage { position: relative; width: 100%; height: 455px; overflow: hidden; }
    .slides-container { position: relative; width: 100%; height: 100%; }
    .offer-slide {
        position: absolute;
        top: 25px;
        left: 50%;
        width: 76%;
        height: 390px;
        overflow: hidden;
        border-radius: 25px;
        background: #dfe9e4;
        opacity: 0;
        transform: translateX(-50%) scale(.70);
        transition: left 700ms cubic-bezier(.22, 1, .36, 1),
                    transform 700ms cubic-bezier(.22, 1, .36, 1),
                    opacity 500ms ease, filter 500ms ease;
        box-shadow: 0 16px 45px rgba(7, 59, 44, .16);
        will-change: left, transform, opacity;
    }
    .offer-slide img {
        display: block;
        width: 100%;
        height: 100%;
        object-fit: cover;
        user-select: none;
    }
    .offer-slide.is-center {
        left: 50%;
        z-index: 3;
        opacity: 1;
        transform: translateX(-50%) scale(1);
        filter: brightness(1) saturate(1);
        box-shadow: 0 25px 65px rgba(7, 59, 44, .24);
    }
    .offer-slide.is-left {
        left: 5%;
        z-index: 1;
        opacity: .55;
        transform: translateX(-50%) scale(.82);
        filter: brightness(.72) saturate(.78);
        cursor: pointer;
    }
    .offer-slide.is-right {
        left: 95%;
        z-index: 1;
        opacity: .55;
        transform: translateX(-50%) scale(.82);
        filter: brightness(.72) saturate(.78);
        cursor: pointer;
    }
    .offer-slide.is-hidden { opacity: 0; pointer-events: none; }
    .carousel-arrow {
        position: absolute;
        top: 48%;
        z-index: 10;
        width: 52px;
        height: 52px;
        padding: 0;
        border: 1px solid rgba(7, 59, 44, .12);
        border-radius: 50%;
        color: #073b2c;
        background: rgba(255, 255, 255, .94);
        font-size: 23px;
        cursor: pointer;
        transform: translateY(-50%);
        transition: transform 180ms ease, color 180ms ease,
                    background 180ms ease, box-shadow 180ms ease;
        box-shadow: 0 10px 30px rgba(7, 59, 44, .18);
    }
    .carousel-arrow:hover {
        color: #fff;
        background: #007a4d;
        transform: translateY(-50%) scale(1.08);
        box-shadow: 0 14px 35px rgba(7, 59, 44, .28);
    }
    .carousel-arrow.previous { left: 7%; }
    .carousel-arrow.next { right: 7%; }
    .carousel-dots {
        position: absolute;
        bottom: 5px;
        left: 50%;
        z-index: 10;
        display: flex;
        gap: 8px;
        transform: translateX(-50%);
    }
    .carousel-dot {
        width: 8px;
        height: 8px;
        padding: 0;
        border: 0;
        border-radius: 999px;
        background: rgba(7, 59, 44, .25);
        cursor: pointer;
        transition: width 250ms ease, background 250ms ease;
    }
    .carousel-dot.active { width: 27px; background: #007a4d; }
    .carousel-information { min-height: 92px; padding: 6px 20px 18px; text-align: center; }
    .carousel-title {
        color: #073b2c;
        font-size: 1.5rem;
        font-weight: 750;
        line-height: 1.3;
    }
    .carousel-description {
        max-width: 720px;
        margin: 8px auto 0;
        color: #52645d;
        font-size: 1rem;
        line-height: 1.55;
    }
    @media (max-width: 700px) {
        .carousel-stage { height: 345px; }
        .offer-slide { top: 20px; width: 84%; height: 285px; border-radius: 18px; }
        .offer-slide.is-left { left: 1%; }
        .offer-slide.is-right { left: 99%; }
        .carousel-arrow { width: 43px; height: 43px; font-size: 18px; }
        .carousel-arrow.previous { left: 3%; }
        .carousel-arrow.next { right: 3%; }
        .carousel-title { font-size: 1.25rem; }
        .carousel-description { font-size: .92rem; }
    }
</style>

<script>
    const offers = __OFFERS_DATA__;
    const container = document.getElementById("slidesContainer");
    const dotsContainer = document.getElementById("carouselDots");
    const title = document.getElementById("carouselTitle");
    const description = document.getElementById("carouselDescription");
    let activeSlide = 0;
    let automaticTimer;

    offers.forEach((offer, index) => {
        const slide = document.createElement("div");
        slide.className = "offer-slide";
        slide.dataset.index = index;
        const image = document.createElement("img");
        image.src = offer.image;
        image.alt = offer.title;
        image.draggable = false;
        slide.appendChild(image);
        container.appendChild(slide);

        const dot = document.createElement("button");
        dot.className = "carousel-dot";
        dot.setAttribute("aria-label", "Afficher l’offre " + (index + 1));
        dot.addEventListener("click", () => selectSlide(index));
        dotsContainer.appendChild(dot);
    });

    const slides = Array.from(document.querySelectorAll(".offer-slide"));
    const dots = Array.from(document.querySelectorAll(".carousel-dot"));

    function updateCarousel() {
        const previous = (activeSlide - 1 + offers.length) % offers.length;
        const next = (activeSlide + 1) % offers.length;
        slides.forEach((slide, index) => {
            slide.classList.remove("is-left", "is-center", "is-right", "is-hidden");
            if (index === activeSlide) slide.classList.add("is-center");
            else if (index === previous) slide.classList.add("is-left");
            else if (index === next) slide.classList.add("is-right");
            else slide.classList.add("is-hidden");
        });
        dots.forEach((dot, index) => {
            dot.classList.toggle("active", index === activeSlide);
        });
        title.textContent = offers[activeSlide].title;
        description.textContent = offers[activeSlide].description;
    }

    function restartTimer() {
        window.clearInterval(automaticTimer);
        automaticTimer = window.setInterval(showNext, 5500);
    }
    function selectSlide(index) {
        activeSlide = index;
        updateCarousel();
        restartTimer();
    }
    function showPrevious() {
        activeSlide = (activeSlide - 1 + offers.length) % offers.length;
        updateCarousel();
    }
    function showNext() {
        activeSlide = (activeSlide + 1) % offers.length;
        updateCarousel();
    }

    document.getElementById("previousSlide").addEventListener("click", () => {
        showPrevious();
        restartTimer();
    });
    document.getElementById("nextSlide").addEventListener("click", () => {
        showNext();
        restartTimer();
    });
    slides.forEach((slide) => {
        slide.addEventListener("click", () => {
            if (slide.classList.contains("is-left")) showPrevious();
            else if (slide.classList.contains("is-right")) showNext();
            restartTimer();
        });
    });

    updateCarousel();
    restartTimer();
</script>
"""

    carousel_html = carousel_html.replace(
        "__OFFERS_DATA__",
        json.dumps(offers, ensure_ascii=False),
    )
    components.html(carousel_html, height=585, scrolling=False)


def render_header():
    """Afficher l'identité institutionnelle."""
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
    return (
        required_types.issubset(completed_document_types(documents))
        and required_types.issubset(reviewed_document_types(documents))
    )


def credit_journey_step(documents=None):
    """Déterminer automatiquement la prochaine étape du parcours de crédit."""
    documents = documents if documents is not None else current_client_documents()
    completed_types = completed_document_types(documents)
    reviewed_types = reviewed_document_types(documents)

    for index, document_step in enumerate(DOCUMENT_JOURNEY[:3]):
        document_type = document_step["type"]
        if document_type not in completed_types or document_type not in reviewed_types:
            return index

    if not st.session_state.get("compromis_skipped", False):
        if "compromis" not in completed_types or "compromis" not in reviewed_types:
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
    """Afficher le contrôle humain obligatoire avant l'étape suivante."""
    result = document.get("result") or {}
    control_result = result.get("control_result", {})

    st.subheader(f"Informations détectées — {document.get('filename', 'Document')}")
    st.caption(
        "Relisez les informations, corrigez les valeurs nécessaires, puis utilisez "
        "le bouton Continuer en bas de cette étape."
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
        st.session_state.journey_notice = "Vos informations sont enregistrées."
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
    reviewed_types = reviewed_document_types(documents)
    missing.extend(
        f"Vérification du document : {label}"
        for doc_type, label in required_documents.items()
        if doc_type not in reviewed_types
    )
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
    reviewed_types = reviewed_document_types(documents)
    documents_ready = (
        missing_document_count == 0
        and required_types.issubset(reviewed_types)
    )

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
        st.markdown("**Avancement de votre projet**")
        st.progress(completed_steps / 4)
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
        st.caption(next_step)

    if st.button("Faire une estimation rapide", key="sidebar_quick", width="stretch",
                 icon=":material/calculate:", type="primary",
                 disabled=st.session_state.processing):
        _go_to("Estimation")
        st.rerun()
    st.caption("VOTRE PARCOURS")
    with st.container(key="sidebar_nav"):
        if st.button(
            "Accueil",
            icon=":material/home:",
            width="stretch",
            type="primary" if st.session_state.page == "Accueil" else "secondary",
            disabled=st.session_state.processing,
            key="sidebar_overview",
        ):
            _go_to("Accueil")
            st.rerun()

        if st.button(
            "1  Mon projet", icon=":material/home_work:", width="stretch",
            disabled=st.session_state.processing or not account_ready,
            key="sidebar_information",
        ):
            _go_to("Accueil")
            st.rerun()
        st.markdown(
            f'<div class="sidebar-step-hint">{"Terminé" if project_ready else "À compléter"}</div>',
            unsafe_allow_html=True,
        )

        if st.button(
            "2  Mes justificatifs", icon=":material/description:", width="stretch",
            type="primary" if st.session_state.page == "Extraction" else "secondary",
            disabled=st.session_state.processing or not account_ready,
            key="sidebar_documents",
        ):
            _go_to("Extraction")
            st.rerun()
        if missing_document_count:
            documents_hint = f"{missing_document_count} document{'s' if missing_document_count > 1 else ''} à ajouter"
        elif documents_ready:
            documents_hint = "Documents vérifiés"
        else:
            documents_hint = "Informations à vérifier"
        st.markdown(f'<div class="sidebar-step-hint">{documents_hint}</div>', unsafe_allow_html=True)

        if st.button(
            "3  Vérifier mes informations", icon=":material/fact_check:", width="stretch",
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
            "4  Voir ma simulation", icon=":material/calculate:", width="stretch",
            type="primary" if st.session_state.page == "Simulation" else "secondary",
            disabled=st.session_state.processing or not dossier_complete,
            key="sidebar_simulation",
        ):
            _go_to("Simulation")
            st.rerun()
        simulation_hint = "Disponible" if dossier_complete else "Disponible après vérification"
        st.markdown(f'<div class="sidebar-step-hint">{simulation_hint}</div>', unsafe_allow_html=True)

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

    if account_ready:
        profile = st.session_state.customer_profile
        display_name = " ".join(filter(None, (profile.get("prenom"), profile.get("nom")))).strip()
        initials = "".join(part[:1].upper() for part in display_name.split()[:2]) or "CL"
        with st.container(key="sidebar_profile"):
            identity_column, logout_column = st.columns([3.2, 1], vertical_alignment="center")
            with identity_column:
                st.markdown(f"**{initials} · {display_name or 'Mon compte'}**")
                st.caption(profile.get("email", ""))
            with logout_column:
                logout = st.button(
                    "Quitter",
                    icon=":material/logout:",
                    help="Se déconnecter",
                    key="sidebar_logout",
                )
            if logout:
                for key in (
                    "documents", "current_doc_id", "confirmed_fields", "last_result",
                    "chat_history", "customer_profile", "compromis_skipped",
                ):
                    st.session_state.pop(key, None)
                st.session_state.account_created = False
                st.session_state.current_client_id = None
                st.session_state.page = "Accueil"
                st.rerun()


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
                answer = get_orchestrator().handle_question(
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
            result = get_orchestrator().handle_document(
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

if "compromis_skipped" not in st.session_state:
    st.session_state.compromis_skipped = False

# L'ancienne page de chat est remplacée par l'assistant permanent à droite.
if st.session_state.page == "Assistant":
    st.session_state.page = "Accueil"

# =========================================================
# SIDEBAR AMÉLIORÉE AVEC GESTION CLIENT
# =========================================================

inject_app_styles()

with st.sidebar:
    # Identifiant conservé uniquement pour l'audit interne.
    advisor_id = f"client_portal_{st.session_state.session_id[:8]}"
    render_application_sidebar()

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

# =========================================================
# PAGE ACCUEIL
# =========================================================

if st.session_state.page == "Accueil":
    if not st.session_state.account_created:
        st.markdown(
            """
            <section class="ca-hero">
                <div class="ca-eyebrow"> ESPACE CLIENT</div>
                <h1>Commençons votre projet habitat.</h1>
                <p>Créez votre espace personnel pour sauvegarder vos justificatifs,
                reprendre votre parcours et affiner votre simulation.</p>
            </section>
            """,
            unsafe_allow_html=True,
        )
        render_offers_carousel()

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

    saved_project = load_project(st.session_state.current_client_id) or st.session_state.get("quick_project", {})
    with st.expander("Personnaliser mon projet habitat", expanded=False):
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
                value=float(saved_project.get("contribution", 100000)), step=5000.0,
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

    action_left, action_right = st.columns(2, gap="large")
    with action_left:
        with st.container(key="home_offer_card", border=True, height="stretch"):
            st.markdown("### Préparer mon dossier")
            st.write(
                "Ajoutez vos justificatifs pour obtenir une simulation basée sur "
                "votre situation personnelle."
            )
            st.caption("Carte d’identité · Bulletin de paie · Relevé bancaire")
            if st.button(
                "Commencer avec mes documents",
                icon=":material/arrow_forward:", type="primary", width="stretch",
                disabled=st.session_state.processing, key="home_start_documents",
            ):
                st.session_state.page = "Extraction"
                st.rerun()

    with action_right:
        with st.container(key="home_estimate_card", border=True, height="stretch"):
            st.markdown("### Estimer ma mensualité")
            st.write(
                "Obtenez immédiatement une première estimation à partir du prix, "
                "de votre apport et de la durée souhaitée."
            )
            st.caption("Rapide · Sans justificatif · Sans engagement")
            if st.button(
                "Faire une estimation rapide",
                icon=":material/calculate:", type="primary", width="stretch",
                disabled=st.session_state.processing, key="home_quick",
            ):
                st.session_state.page = "Estimation"
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

    # Si le document de l'étape a déjà été analysé, le sélectionner afin que
    # l'utilisateur puisse relire et corriger ses champs avant de continuer.
    if journey_step < len(DOCUMENT_JOURNEY):
        active_document_type = DOCUMENT_JOURNEY[journey_step]["type"]
        selected_document = st.session_state.documents.get(
            st.session_state.current_doc_id
        )
        if not selected_document:
            matching_documents = [
                (document_id, document)
                for document_id, document in client_docs.items()
                if document.get("type") == active_document_type
                and document.get("status") == "completed"
            ]
            matching_documents.sort(
                key=lambda item: item[1].get("timestamp") or "",
                reverse=True,
            )
            if matching_documents:
                selected_id, selected_document = matching_documents[0]
                st.session_state.current_doc_id = selected_id
                st.session_state.last_result = selected_document.get("result")
                st.session_state.confirmed_fields = selected_document.get(
                    "confirmed_fields", {}
                )

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
            "Vos justificatifs sont enregistrés. Cliquez sur un document ci-dessus "
            "pour revoir ou corriger ses informations."
        )
        action_left, action_right = st.columns(2)
        with action_left:
            if st.button(
                "Revoir mes informations",
                icon=":material/fact_check:",
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
            st.session_state.last_result = result
            st.session_state.confirmed_fields = {}
            save_document(
                st.session_state.current_client_id, doc_id,
                st.session_state.documents[doc_id],
            )
            st.session_state.journey_notice = (
                f"{document_step['title']} analysé avec succès. Vérifiez et "
                "corrigez maintenant les informations extraites avant de continuer."
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
    st.title("Estimer ma mensualité")
    st.caption("Aucun compte ni justificatif nécessaire pour cette première estimation.")
    estimate = render_simulation(key_prefix="quick")
    if st.button("Affiner avec mes documents", type="primary", key="quick_refine"):
        if estimate:
            st.session_state.quick_project = estimate
        st.session_state.page = "Extraction" if st.session_state.account_created else "Accueil"
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
    saved_project = load_project(st.session_state.current_client_id) or st.session_state.get("quick_project", {})
    estimate = render_simulation(saved_project, key_prefix=f"simulation_{st.session_state.current_client_id}")
    rows, _ = build_client_summary(client_docs)
    confirmed = {row["field"]: row["Valeur confirmée"] for row in rows if row["Statut"] == "Confirmé"}
    income = float(confirmed["salaire_net"]) + float(confirmed["revenus_complementaires"])
    if estimate and income > 0:
        ratio = (float(confirmed["charge_mensuelle_credits"]) + estimate["monthly_payment"]) / income
        st.metric("Taux d'endettement estimé", f"{ratio:.2%}")
    with st.expander("Ma situation vérifiée"):
        for row in rows:
            st.write(f"{row['Champ']} : {row['Valeur confirmée']}")
    if st.button("Modifier ma situation", key="simulation_edit"):
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
                    chat_result = get_orchestrator().handle_question(
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
st.caption("Crédit Agricole du Maroc — Assistant Crédit Habitat")

# =========================================================
# GESTION DES ERREURS GLOBALES
# =========================================================

if "error" in st.session_state:
    with st.sidebar:
        st.error(f"⚠️ {st.session_state.error}")
        if st.button("Effacer l'erreur"):
            del st.session_state.error
            st.rerun()
