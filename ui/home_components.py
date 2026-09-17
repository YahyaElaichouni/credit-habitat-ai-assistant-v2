"""Composants visuels réutilisables de la page d'accueil."""

import base64
import html
import json
from pathlib import Path

import streamlit as st

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
    st.iframe(carousel_html, height=585)

def render_home_assurance_strip():
    """Afficher les trois garanties principales sous le parcours d'accueil."""
    items = (
        ("⌑", "Données traitées localement", "Vos documents restent dans l'environnement de démonstration."),
        ("◷", "Reprenez à tout moment", "Votre projet et votre progression sont enregistrés."),
        ("⌂", "Simulation immédiate", "Comparez plusieurs scénarios de financement sans engagement."),
    )
    with st.container(key="cam_assurance_strip"):
        columns = st.columns(3, gap=None)
        for column, (icon, title, description) in zip(columns, items):
            with column:
                st.markdown(
                    f"""
                    <article class="cam-assurance-item">
                        <div class="cam-assurance-icon">{icon}</div>
                        <div>
                            <strong>{html.escape(title)}</strong>
                            <p>{html.escape(description)}</p>
                        </div>
                    </article>
                    """,
                    unsafe_allow_html=True,
                )


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
