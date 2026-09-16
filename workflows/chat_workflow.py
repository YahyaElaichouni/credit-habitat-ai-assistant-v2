"""
===========================================================
Chat Workflow
Projet PFE Crédit Agricole du Maroc
===========================================================

Orchestration LangGraph du pipeline conversationnel :

    Message -> Conseiller guidé -> RAG si nécessaire -> Audit

EB-102 : réponses sourcées, ancrées dans les documents officiels.
EB-103 : refus explicite et redirection si hors périmètre.
EB-228 : chaque échange est tracé dans le journal d'audit.
"""

import logging
from typing import Any, Dict, List, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from agents.guidance_agent import GuidanceAgent
from agents.rag_agent import RAGAgent
from database import audit

logger = logging.getLogger(__name__)


# =========================================================
# ETAT DU WORKFLOW
# =========================================================

class ChatState(TypedDict, total=False):

    # Entrées
    question: str
    advisor_id: str
    session_id: str
    profile: Dict[str, Any]
    conversation_history: List[Dict[str, Any]]

    # Routage et sortie
    mode: str
    answer: str
    in_scope: bool
    sources: List[str]
    passages: List[Dict[str, Any]]
    profile_updates: Dict[str, Any]
    missing_fields: List[str]
    next_field: Optional[str]
    profile_complete: bool


# =========================================================
# AGENT (instancié une fois, réutilisé à chaque appel)
# =========================================================

# Chargement paresseux : RAGAgent instancie SentenceTransformer
# (bge-m3) et charge l'index FAISS — coûteux. On ne paie ce coût
# qu'à la première question posée, pas à l'import du module (donc
# pas si la session n'utilise que le pipeline d'extraction).

_rag_agent = None
_guidance_agent = None


def get_rag_agent() -> RAGAgent:
    global _rag_agent
    if _rag_agent is None:
        _rag_agent = RAGAgent()
    return _rag_agent


def get_guidance_agent() -> GuidanceAgent:
    global _guidance_agent
    if _guidance_agent is None:
        _guidance_agent = GuidanceAgent()
    return _guidance_agent


# =========================================================
# NOEUDS
# =========================================================

def guidance_node(state: ChatState) -> Dict[str, Any]:
    logger.info("[Workflow] Étape accompagnement : %s", state["question"])

    return get_guidance_agent().run(
        message=state["question"],
        profile=state.get("profile", {}),
        conversation_history=state.get("conversation_history", []),
    )


def route_after_guidance(state: ChatState) -> str:
    return "rag" if state.get("mode") == "rag" else "audit"


def rag_node(state: ChatState) -> Dict[str, Any]:

    logger.info("[Workflow] Étape RAG : %s", state["question"])

    result = get_rag_agent().run(state["question"])

    return {
        "mode": "rag",
        "answer": result["answer"],
        "in_scope": result["in_scope"],
        "sources": result["sources"],
        "passages": result["passages"],
    }


def audit_node(state: ChatState) -> Dict[str, Any]:

    audit.log_chat_interaction(
        question=state["question"],
        answer=state["answer"],
        in_scope=state["in_scope"],
        sources=state["sources"],
        advisor_id=state.get("advisor_id"),
        session_id=state.get("session_id"),
    )

    return {}


# =========================================================
# CONSTRUCTION DU GRAPHE
# =========================================================

graph = StateGraph(ChatState)

graph.add_node("guidance", guidance_node)
graph.add_node("rag", rag_node)
graph.add_node("audit", audit_node)

graph.add_edge(START, "guidance")
graph.add_conditional_edges(
    "guidance",
    route_after_guidance,
    {
        "rag": "rag",
        "audit": "audit",
    },
)
graph.add_edge("rag", "audit")
graph.add_edge("audit", END)

workflow = graph.compile()
