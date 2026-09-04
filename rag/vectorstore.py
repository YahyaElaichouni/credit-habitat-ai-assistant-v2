"""
===========================================================
Vectorstore RAG
Projet PFE Crédit Agricole du Maroc
===========================================================

Couche fine autour de FAISS + sentence-transformers, volontairement
sans passer par les wrappers LangChain (VectorStore, Document...) :
le fonctionnement reste entièrement visible et explicable, ce qui
compte pour une soutenance.

Isolation stricte (rappel) : ce vectorstore n'indexe QUE les
documents officiels de la banque (config.settings.documents_dir).
Il ne doit jamais recevoir de document déposé par un client — ceux-ci
passent par le pipeline d'extraction (extraction/, pas rag/), qui
ne les indexe jamais ici. C'est la principale ligne de défense
contre l'injection : mélanger les deux romprait cette isolation.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

from config.settings import settings

logger = logging.getLogger(__name__)

INDEX_FILENAME = "index.faiss"
METADATA_FILENAME = "metadata.json"


class VectorStore:

    def __init__(self, model_name: Optional[str] = None):
        self.model_name = model_name or settings.rag_embedding_model
        logger.info("Chargement du modèle d'embeddings : %s", self.model_name)
        self.model = SentenceTransformer(self.model_name)

        self.index: Optional[faiss.Index] = None
        self.metadata: List[Dict[str, Any]] = []

    # =====================================================
    # CONSTRUCTION
    # =====================================================

    def build(self, chunks: List[Dict[str, Any]]) -> None:
        """Construit l'index à partir d'une liste de chunks
        {text, source, chunk_id, ...}."""

        if not chunks:
            raise ValueError(
                "Aucun chunk fourni : impossible de construire un "
                "index vide."
            )

        texts = [c["text"] for c in chunks]

        logger.info("Calcul des embeddings pour %d chunks...", len(texts))
        embeddings = self.model.encode(
            texts,
            normalize_embeddings=True,  # nécessaire pour que le produit
            show_progress_bar=False,     # scalaire équivale à un cosinus
        )
        embeddings = np.asarray(embeddings, dtype="float32")

        dimension = embeddings.shape[1]
        # IndexFlatIP : recherche exacte (pas d'approximation), adaptée
        # à un volume de documents bancaires raisonnable (quelques
        # dizaines à centaines de documents). À revoir vers un index
        # approximatif (IVF, HNSW) seulement si le volume grossit
        # significativement.
        self.index = faiss.IndexFlatIP(dimension)
        self.index.add(embeddings)

        self.metadata = chunks
        logger.info("Index construit : %d vecteurs, dimension %d",
                    self.index.ntotal, dimension)

    # =====================================================
    # PERSISTENCE
    # =====================================================

    def save(self, directory: Optional[Path] = None) -> None:
        if self.index is None:
            raise RuntimeError("Aucun index à sauvegarder — appelez build() d'abord.")

        directory = Path(directory or settings.vectorstore_dir)
        directory.mkdir(parents=True, exist_ok=True)

        faiss.write_index(self.index, str(directory / INDEX_FILENAME))

        with open(directory / METADATA_FILENAME, "w", encoding="utf-8") as f:
            json.dump(self.metadata, f, ensure_ascii=False, indent=2)

        logger.info("Vectorstore sauvegardé dans %s", directory)

    def load(self, directory: Optional[Path] = None) -> None:
        directory = Path(directory or settings.vectorstore_dir)
        index_path = directory / INDEX_FILENAME
        metadata_path = directory / METADATA_FILENAME

        if not index_path.exists() or not metadata_path.exists():
            raise FileNotFoundError(
                f"Vectorstore introuvable dans {directory}. "
                "Lancez rag/ingest.py d'abord pour construire l'index "
                "à partir des documents officiels."
            )

        self.index = faiss.read_index(str(index_path))

        with open(metadata_path, encoding="utf-8") as f:
            self.metadata = json.load(f)

        logger.info(
            "Vectorstore chargé depuis %s (%d vecteurs)",
            directory, self.index.ntotal
        )

    # =====================================================
    # RECHERCHE
    # =====================================================

    def search(self, query: str, top_k: Optional[int] = None) -> List[Dict[str, Any]]:
        """Retourne les top_k chunks les plus proches de la requête,
        chacun enrichi d'un score de similarité cosinus (entre -1 et 1,
        en pratique proche de [0, 1] pour du texte)."""

        if self.index is None:
            raise RuntimeError(
                "Vectorstore non chargé — appelez load() ou build() "
                "avant de chercher."
            )

        top_k = top_k or settings.rag_top_k

        query_embedding = self.model.encode(
            [query], normalize_embeddings=True
        )
        query_embedding = np.asarray(query_embedding, dtype="float32")

        scores, indices = self.index.search(query_embedding, top_k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx == -1:  # FAISS retourne -1 si moins de top_k résultats existent
                continue
            results.append({
                **self.metadata[idx],
                "score": float(score),
            })

        return results
