"""Composants visuels réutilisables de la page d'accueil."""

import base64
import html
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
