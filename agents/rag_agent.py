"""
===========================================================
RAG Agent
Projet PFE Crédit Agricole du Maroc
===========================================================

Génère une réponse ancrée dans les documents officiels de la
banque (EB-102), ou refuse explicitement avec redirection si la
question sort du périmètre couvert (EB-103) — décision prise
avant tout appel au LLM, sur le seul score de similarité du
retriever (cf. rag/retriever.py::is_in_scope).
"""

import logging
from typing import Any, Dict

import ollama

from config.settings import settings
from rag.prompts import SYSTEM_PROMPT, build_user_prompt
from rag.retriever import Retriever

logger = logging.getLogger(__name__)

REFUSAL_MESSAGE = (
    "Je n'ai pas trouvé d'information fiable sur ce sujet dans la "
    "documentation disponible. Je vous invite à contacter un "
    "conseiller pour obtenir une réponse précise."
)


class RAGAgent:

    def __init__(self, model: str = None):
        self.model = model or settings.llm_model
        self.retriever = Retriever()

    # =====================================================
    # POINT D'ENTREE
    # =====================================================

    def run(self, query: str) -> Dict[str, Any]:

        if not query or not query.strip():
            raise ValueError("La question est vide.")

        results = self.retriever.retrieve(query)

        # Décision hors-périmètre AVANT tout appel LLM : si les
        # passages les plus proches ne sont pas assez pertinents, on
        # ne prend même pas le risque de générer une réponse
        # approximative à partir de contenu non pertinent.
        if not self.retriever.is_in_scope(results):
            logger.info(
                "[RAGAgent] Question hors périmètre (score=%.3f) : %s",
                self.retriever.best_score(results), query,
            )
            return {
                "answer": REFUSAL_MESSAGE,
                "in_scope": False,
                "sources": [],
                "passages": results,
            }

        prompt = build_user_prompt(query, results)

        try:
            response = ollama.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
            )
        except Exception as e:
            raise RuntimeError(
                f"Échec de l'appel au modèle Ollama ({self.model}). "
                "Vérifiez qu'Ollama tourne bien en local et que le "
                "modèle est disponible (`ollama list`)."
            ) from e

        answer = response["message"]["content"]
        sources = sorted({p["source"] for p in results})

        logger.info("[RAGAgent] Réponse générée — sources : %s", sources)

        return {
            "answer": answer,
            "in_scope": True,
            "sources": sources,
            "passages": results,
        }
