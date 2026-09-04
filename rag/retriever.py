"""
===========================================================
Retriever RAG
Projet PFE Crédit Agricole du Maroc
===========================================================

Interface fine au-dessus de VectorStore : charge l'index une seule
fois (coûteux : modèle d'embeddings + index FAISS), expose
retrieve() pour l'agent, et centralise la décision "dans le
périmètre ou non" (EB-103) sur un seul critère : le score de
similarité du meilleur résultat, comparé au seuil configurable.
"""

import logging
from typing import Any, Dict, List, Optional

from config.settings import settings
from rag.vectorstore import VectorStore

logger = logging.getLogger(__name__)


class Retriever:

    def __init__(self):
        self.store = VectorStore()
        self.store.load()

    # =====================================================
    # RECHERCHE
    # =====================================================

    def retrieve(
        self, query: str, top_k: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Retourne les passages les plus proches de la requête,
        triés par score décroissant (déjà l'ordre retourné par FAISS)."""

        results = self.store.search(query, top_k=top_k)

        logger.info(
            "[Retriever] %d résultat(s) — meilleur score : %.3f",
            len(results),
            results[0]["score"] if results else 0.0,
        )

        return results

    # =====================================================
    # DECISION HORS-PERIMETRE (EB-103)
    # =====================================================

    def best_score(self, results: List[Dict[str, Any]]) -> float:
        return results[0]["score"] if results else 0.0

    def is_in_scope(self, results: List[Dict[str, Any]]) -> bool:
        """False si aucun résultat, ou si le meilleur score est sous
        le seuil configuré — dans les deux cas, le RAGAgent doit
        refuser plutôt que générer une réponse à partir de passages
        peu pertinents."""

        return self.best_score(results) >= settings.rag_similarity_threshold
