"""Services de dépôt et d'analyse documentaire utilisés par l'interface."""

from pathlib import Path

import streamlit as st

from config.settings import settings


UPLOAD_DIR = Path("data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@st.cache_resource
def get_orchestrator():
    """Créer et réutiliser l'orchestrateur et ses modèles lourds."""
    from agents.orchestrator import Orchestrator

    return Orchestrator()


def validate_file(uploaded_file):
    """Valider la taille, l'extension et, si disponible, le type MIME."""
    if uploaded_file is None:
        return False, "Aucun fichier sélectionné"
    if uploaded_file.size > settings.max_file_size_bytes:
        return False, f"Fichier trop volumineux (max {settings.max_file_size_mb} MB)"

    extension = Path(uploaded_file.name).suffix.lower()
    if extension not in settings.allowed_extensions:
        accepted = ", ".join(settings.allowed_extensions)
        return False, f"Format non supporté. Formats acceptés : {accepted}"

    try:
        import magic

        mime = magic.from_buffer(uploaded_file.getvalue(), mime=True)
        if mime not in {"application/pdf", "image/jpeg", "image/png", "image/tiff"}:
            return False, f"Type MIME non supporté : {mime}"
    except ImportError:
        pass
    return True, "OK"


def count_pdf_pages(uploaded_file):
    """Compter les pages d'un PDF sans l'écrire sur le disque."""
    import fitz

    document = fitz.open(stream=uploaded_file.getvalue(), filetype="pdf")
    try:
        return document.page_count
    finally:
        document.close()


def save_document_files(uploaded_files, document_type, document_id):
    """Sauvegarder un document ou fusionner les deux faces d'une CNIE."""
    files = list(uploaded_files or [])
    if not files:
        raise ValueError("Aucun fichier à sauvegarder")
    if len(files) == 1:
        extension = Path(files[0].name).suffix.lower()
        saved_path = UPLOAD_DIR / f"{document_id}{extension}"
        saved_path.write_bytes(files[0].getvalue())
        return saved_path
    if document_type != "carte_identite" or len(files) != 2:
        raise ValueError("Seule la carte d'identité accepte deux fichiers")

    import fitz

    saved_path = UPLOAD_DIR / f"{document_id}.pdf"
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


def request_document_analysis():
    """Verrouiller l'analyse avant le rerun déclenché par le bouton."""
    if not st.session_state.processing:
        st.session_state.processing = True
        st.session_state.analysis_requested = True


def process_document_with_progress(
    file_path,
    document_type,
    declared_data,
    advisor_id,
    session_id,
):
    """Exécuter le pipeline en affichant un état d'avancement réel."""
    with st.status("Analyse du document en cours", expanded=True) as status:
        st.write("Lecture OCR, extraction et vérifications. Le délai dépend du nombre de pages.")
        st.caption("Patientez sans relancer l'analyse ; les résultats apparaîtront à la fin.")
        try:
            result = get_orchestrator().handle_document(
                pdf_path=str(file_path),
                document_type=document_type,
                advisor_id=advisor_id,
                session_id=session_id,
                declared_data=declared_data,
            )
        except Exception:
            status.update(label="L'analyse n'a pas abouti", state="error")
            raise
        status.update(
            label="Analyse terminée — résultats prêts à vérifier",
            state="complete",
            expanded=False,
        )
        return result
