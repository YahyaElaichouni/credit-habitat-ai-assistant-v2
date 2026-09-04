"""
===========================================================
Ingestion RAG
Projet PFE Crédit Agricole du Maroc
===========================================================

Lit les documents officiels de la banque (config.settings.documents_dir,
"data/docs" par défaut), les découpe en chunks, construit et
sauvegarde le vectorstore.

Extraction de texte natif (PyMuPDF get_text), pas d'OCR : ces
documents sont supposés numériques (offre, CGU, grille des taux),
pas scannés. Si un jour un document officiel n'a pas de couche
texte, ocr/ocr_engine.py peut être réutilisé en amont — mais ne
JAMAIS faire passer un document client par ce module d'ingestion
(cf. note d'isolation dans vectorstore.py).

Usage :
    python -m rag.ingest
"""

import logging
from pathlib import Path
from typing import Any, Dict, List

import fitz  # PyMuPDF

from config.settings import settings
from rag.vectorstore import VectorStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# =========================================================
# CHARGEMENT
# =========================================================

def load_pdf_text(pdf_path: Path) -> str:
    """Extrait le texte natif d'un PDF, bloc par bloc (~paragraphe),
    plutôt que page par page.

    page.get_text() (mode par défaut) ne sépare pas les paragraphes
    par une ligne vide — tout un article de CGU ressort comme un
    unique bloc de texte, ce qui casse split_text() (basé sur \\n\\n
    pour repérer les paragraphes) et produit des chunks coupés en
    plein milieu des phrases. Le mode "blocks" retourne chaque
    paragraphe/titre comme un élément séparé, qu'on rejoint ici avec
    \\n\\n pour reconstruire des frontières de paragraphes exploitables.
    """

    document = fitz.open(pdf_path)
    try:
        paragraphs = []
        for page in document:
            blocks = page.get_text("blocks")
            # Tri dans l'ordre de lecture : haut en bas, gauche à droite
            # (get_text("blocks") ne garantit pas cet ordre par défaut).
            blocks = sorted(blocks, key=lambda b: (round(b[1], 1), b[0]))
            for block in blocks:
                text = block[4].strip()
                if text:
                    paragraphs.append(text)
    finally:
        document.close()

    return "\n\n".join(paragraphs)


# =========================================================
# DECOUPAGE
# =========================================================

def split_text(
    text: str,
    chunk_size: int = None,
    chunk_overlap: int = None,
) -> List[str]:
    """Découpage simple par paragraphes, avec repli en blocs de
    taille fixe (+ chevauchement) pour les paragraphes trop longs.

    Volontairement fait maison plutôt que de dépendre de
    langchain-text-splitters : le comportement reste entièrement
    visible et explicable pour la soutenance, pour un besoin qui
    ne justifie pas une dépendance supplémentaire.
    """

    chunk_size = chunk_size or settings.rag_chunk_size
    chunk_overlap = chunk_overlap or settings.rag_chunk_overlap

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    chunks: List[str] = []
    current = ""

    for paragraph in paragraphs:

        if len(paragraph) > chunk_size:
            # Paragraphe à lui seul plus grand que chunk_size :
            # on le découpe en blocs de taille fixe avec chevauchement.
            if current:
                chunks.append(current)
                current = ""

            start = 0
            while start < len(paragraph):
                end = start + chunk_size
                chunks.append(paragraph[start:end])
                start = end - chunk_overlap

        elif len(current) + len(paragraph) + 1 <= chunk_size:
            current = f"{current}\n{paragraph}".strip()

        else:
            chunks.append(current)
            current = paragraph

    if current:
        chunks.append(current)

    return chunks


# =========================================================
# CONSTRUCTION DES CHUNKS AVEC METADATA
# =========================================================

def build_chunks_from_documents(documents_dir: Path = None) -> List[Dict[str, Any]]:

    documents_dir = Path(documents_dir or settings.documents_dir)

    pdf_files = sorted(documents_dir.glob("*.pdf"))

    if not pdf_files:
        raise FileNotFoundError(
            f"Aucun PDF trouvé dans {documents_dir}. Déposez-y les "
            "documents officiels de la banque (offre crédit habitat, "
            "CGU, grille des taux) avant de lancer l'ingestion."
        )

    all_chunks: List[Dict[str, Any]] = []

    for pdf_path in pdf_files:

        logger.info("Lecture : %s", pdf_path.name)
        text = load_pdf_text(pdf_path)

        if not text.strip():
            logger.warning(
                "%s ne contient aucun texte extractible (scanné ? "
                "vide ?) — ignoré. Passez-le par ocr/ocr_engine.py "
                "en amont si c'est un scan.",
                pdf_path.name,
            )
            continue

        text_chunks = split_text(text)

        for i, chunk_text in enumerate(text_chunks):
            all_chunks.append({
                "text": chunk_text,
                "source": pdf_path.name,
                "chunk_id": i,
            })

        logger.info("  -> %d chunks", len(text_chunks))

    return all_chunks


# =========================================================
# POINT D'ENTREE
# =========================================================

def run_ingestion() -> None:

    chunks = build_chunks_from_documents()

    store = VectorStore()
    store.build(chunks)
    store.save()

    logger.info(
        "Ingestion terminée : %d chunks indexés depuis %s",
        len(chunks), settings.documents_dir,
    )


if __name__ == "__main__":
    run_ingestion()
