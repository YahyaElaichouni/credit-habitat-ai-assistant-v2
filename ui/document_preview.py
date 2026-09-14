"""Aperçu sécurisé des justificatifs PDF et image."""

from pathlib import Path

import fitz
import streamlit as st


SUPPORTED_IMAGES = {".png", ".jpg", ".jpeg"}


def resolve_preview_path(document_path):
    """Autoriser uniquement les fichiers du dossier data/uploads."""
    if not document_path:
        return None

    upload_root = Path("data/uploads").resolve()
    candidate = Path(document_path).resolve()

    try:
        candidate.relative_to(upload_root)
    except ValueError:
        return None

    return candidate if candidate.is_file() else None


def preferred_source_page(decisions):
    """Trouver la première page citée par l’extraction."""
    for decision in decisions.values():
        if not isinstance(decision, dict):
            continue

        source = decision.get("source") or {}
        page = source.get("page")

        if isinstance(page, int) and page > 0:
            return page

    return 1


def render_document_preview(
    document_path,
    document_id,
    preferred_page=1,
):
    """Afficher un PDF ou une image sans modifier le document."""
    path = resolve_preview_path(document_path)

    st.markdown("#### Votre justificatif")

    if path is None:
        st.info(
            "L’aperçu n’est pas disponible. "
            "Vous pouvez quand même vérifier les informations."
        )
        return

    suffix = path.suffix.lower()

    try:
        if suffix == ".pdf":
            _render_pdf(
                path,
                document_id,
                preferred_page,
            )

        elif suffix in SUPPORTED_IMAGES:
            st.image(
                path.read_bytes(),
                caption=path.name,
                width="stretch",
            )

        else:
            st.warning(
                "Ce format ne peut pas être affiché directement."
            )

    except (OSError, RuntimeError, ValueError) as exc:
        st.warning(
            "Impossible d’afficher l’aperçu du justificatif."
        )
        st.caption(str(exc))

    mime_type = {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }.get(suffix, "application/octet-stream")

    try:
        st.download_button(
            "Télécharger le document original",
            data=path.read_bytes(),
            file_name=path.name,
            mime=mime_type,
            width="stretch",
            key=f"download_original_{document_id}",
        )
    except OSError:
        st.warning("Le document original n’est plus accessible.")


def _render_pdf(path, document_id, preferred_page):
    """Transformer la page sélectionnée du PDF en image."""
    with fitz.open(path) as document:
        if document.needs_pass:
            st.warning(
                "Ce PDF est protégé par un mot de passe."
            )
            return

        page_count = document.page_count

        if page_count == 0:
            st.warning("Ce PDF ne contient aucune page.")
            return

        preferred_page = max(
            1,
            min(int(preferred_page or 1), page_count),
        )

        if page_count > 1:
            selected_page = st.selectbox(
                "Page affichée",
                options=list(range(1, page_count + 1)),
                index=preferred_page - 1,
                key=f"preview_page_{document_id}",
            )
        else:
            selected_page = 1
            st.caption("Page 1 sur 1")

        page = document.load_page(selected_page - 1)

        pixmap = page.get_pixmap(
            dpi=130,
            alpha=False,
        )

        st.image(
            pixmap.tobytes("png"),
            caption=f"{path.name} — page {selected_page}/{page_count}",
            width="stretch",
        )