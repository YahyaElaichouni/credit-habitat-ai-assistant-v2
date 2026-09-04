"""
===========================================================
Orchestrateur
Projet PFE Crédit Agricole du Maroc
===========================================================

Point d'entrée unique du système : distingue une demande de
traitement de document (upload) d'une question conversationnelle,
et route vers le workflow LangGraph approprié.

Le routage est volontairement simple, sans LLM : la distinction
entre les deux fonctionnalités est déjà faite par l'appelant
(bouton "Déposer un document" vs zone de question dans
l'interface). Un LLM n'apporterait rien ici, et introduirait une
dépendance et une latence inutiles pour une décision qui doit de
toute façon rester déterministe — même principe que pour
rule_engine (aucune décision structurante confiée au LLM quand une
logique simple suffit).

L'orchestrateur ne réimplémente aucune logique métier : il délègue
entièrement à document_workflow / chat_workflow, déjà testés
indépendamment.
"""

import logging
from typing import Any, Dict, Optional

from workflows.chat_workflow import workflow as chat_workflow
from workflows.document_workflow import workflow as document_workflow

logger = logging.getLogger(__name__)


class Orchestrator:

    # =====================================================
    # PIPELINE DOCUMENT (EB-104 à EB-125)
    # =====================================================

    def handle_document(
        self,
        pdf_path: str,
        document_type: str,
        advisor_id: str,
        session_id: str,
        declared_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Route vers le pipeline d'extraction documentaire
        (contrôle -> OCR -> extraction -> validation -> audit)."""

        logger.info(
            "[Orchestrator] Requête document : %s (%s)",
            pdf_path, document_type,
        )

        return document_workflow.invoke({
            "pdf_path": pdf_path,
            "document_type": document_type,
            "declared_data": declared_data or {},
            "advisor_id": advisor_id,
            "session_id": session_id,
        })

    # =====================================================
    # PIPELINE CONVERSATIONNEL (EB-102, EB-103)
    # =====================================================

    def handle_question(
        self,
        question: str,
        advisor_id: str,
        session_id: str,
    ) -> Dict[str, Any]:
        """Route vers le pipeline conversationnel RAG
        (retrieval -> décision de périmètre -> génération -> audit)."""

        logger.info("[Orchestrator] Requête conversationnelle : %s", question)

        return chat_workflow.invoke({
            "question": question,
            "advisor_id": advisor_id,
            "session_id": session_id,
        })
