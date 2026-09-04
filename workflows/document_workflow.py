"""
===========================================================
Document Workflow
Projet PFE Crédit Agricole du Maroc
===========================================================

Orchestration LangGraph du pipeline d'extraction documentaire :

    OCR -> Extraction (+ anti-injection) -> Validation
    (confiance EB-125, écart EB-108, plausibilité, sécurité)

Rien n'est jamais auto-validé ici (EB-106) : ce workflow produit
un résultat structuré avec un statut par champ, la décision finale
de confirmation reste entièrement du côté de l'interface / de
l'utilisateur humain.
"""

import logging
import hashlib
from pathlib import Path
from typing import Any, Dict, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from agents.extraction_agent import ExtractionAgent
from agents.ocr_agent import OCRAgent
from agents.validation_agent import ValidationAgent
from database import audit
from utils.file_validator import control_document
from extraction.provenance import page_text

audit.init_audit_table()

logger = logging.getLogger(__name__)


# =========================================================
# ETAT DU WORKFLOW
# =========================================================

class DocumentState(TypedDict, total=False):

    # Entrées
    pdf_path: str
    document_type: str
    declared_data: Dict[str, Any]
    advisor_id: str
    session_id: str

    # Sortie contrôle du document (EB-219)
    control_result: Dict[str, Any]

    # Sortie OCR
    ocr_text: str
    ocr_pages: list
    document_sha256: str

    # Sortie extraction
    extraction_data: Dict[str, Any]
    extraction_confidences: Dict[str, Optional[float]]
    extraction_raw: Dict[str, Any]
    extraction_security: Dict[str, Any]
    extraction_sources: Dict[str, Any]

    # Sortie validation
    validation_result: Dict[str, Any]


# =========================================================
# AGENTS (instanciés une fois, réutilisés à chaque appel)
# =========================================================

# Chargement paresseux : PaddleOCR (OCREngine) et le LLM ne se
# chargent qu'à la première utilisation réelle du pipeline, pas à
# l'import de ce module. Sans ça, démarrer l'application charge
# systématiquement OCR + LLM même pour une session qui n'utilisera
# que l'assistant conversationnel (rag_agent, module séparé).

_ocr_agent = None
_extraction_agent = None
_validation_agent = None


def get_ocr_agent() -> OCRAgent:
    global _ocr_agent
    if _ocr_agent is None:
        _ocr_agent = OCRAgent()
    return _ocr_agent


def get_extraction_agent() -> ExtractionAgent:
    global _extraction_agent
    if _extraction_agent is None:
        _extraction_agent = ExtractionAgent()
    return _extraction_agent


def get_validation_agent() -> ValidationAgent:
    global _validation_agent
    if _validation_agent is None:
        _validation_agent = ValidationAgent()
    return _validation_agent


# =========================================================
# NOEUDS
# =========================================================

def control_node(state: DocumentState) -> Dict[str, Any]:
    """EB-219 : taille et type réel du fichier, avant tout traitement."""

    logger.info("[Workflow] Étape contrôle du document : %s", state["pdf_path"])

    result = control_document(state["pdf_path"])

    if not result.valid:
        logger.warning(
            "[Workflow] Document rejeté au contrôle : %s", result.reason
        )

    return {
        "control_result": {"valid": result.valid, "reason": result.reason}
    }


def ocr_node(state: DocumentState) -> Dict[str, Any]:

    logger.info("[Workflow] Étape OCR : %s", state["pdf_path"])

    pages = get_ocr_agent().execute_pages(state["pdf_path"])
    return {"ocr_text": page_text(pages), "ocr_pages": pages,
            "document_sha256": hashlib.sha256(Path(state["pdf_path"]).read_bytes()).hexdigest()}


def extraction_node(state: DocumentState) -> Dict[str, Any]:

    logger.info(
        "[Workflow] Étape extraction : %s", state["document_type"]
    )

    result = get_extraction_agent().run(
        ocr_text=state["ocr_text"],
        document_type=state["document_type"],
        pages=state["ocr_pages"],
        document_path=state["pdf_path"],
        document_sha256=state["document_sha256"],
    )

    return {
        "extraction_data": result["data"],
        "extraction_confidences": result["confidences"],
        "extraction_raw": result["raw"],
        "extraction_security": result["security"],
        "extraction_sources": result["sources"],
    }


def validation_node(state: DocumentState) -> Dict[str, Any]:

    logger.info("[Workflow] Étape validation")

    result = get_validation_agent().run(
        document_type=state["document_type"],
        data=state["extraction_data"],
        confidences=state["extraction_confidences"],
        security=state["extraction_security"],
        declared_data=state.get("declared_data"),
        sources=state.get("extraction_sources"),
    )

    return {"validation_result": result}


def audit_node(state: DocumentState) -> Dict[str, Any]:
    """Noeud unique de journalisation (EB-228), utilisé aussi bien
    sur le chemin de rejet que sur le chemin de succès. Lit l'état
    final accumulé et écrit les événements pertinents — centralise
    la traçabilité plutôt que de l'éparpiller dans chaque agent
    métier, qui n'a pas à savoir comment/où elle est stockée."""

    advisor_id = state.get("advisor_id")
    session_id = state.get("session_id")
    document_path = state["pdf_path"]
    document_type = state.get("document_type")

    control_result = state["control_result"]

    if not control_result["valid"]:
        audit.log_document_rejected(
            document_path=document_path,
            reason=control_result["reason"],
            advisor_id=advisor_id,
            session_id=session_id,
        )
        return {}

    security = state.get("extraction_security", {})
    if security.get("suspicious"):
        audit.log_security_flag(
            document_path=document_path,
            document_type=document_type,
            matched_patterns=security.get("matched_patterns", []),
            advisor_id=advisor_id,
            session_id=session_id,
        )

    validation_result = state.get("validation_result")
    if validation_result:
        for field_name, decision in validation_result["fields"].items():
            audit.log_field_decision(
                document_path=document_path,
                document_type=document_type,
                field_name=field_name,
                value=decision["value"],
                status=decision["status"],
                reasons=decision["reasons"],
                source=decision.get("source"),
                advisor_id=advisor_id,
                session_id=session_id,
            )

    return {}


# =========================================================
# CONSTRUCTION DU GRAPHE
# =========================================================

graph = StateGraph(DocumentState)

graph.add_node("control", control_node)
graph.add_node("ocr", ocr_node)
graph.add_node("extraction", extraction_node)
graph.add_node("validation", validation_node)
graph.add_node("audit_rejection", audit_node)
graph.add_node("audit_success", audit_node)

graph.add_edge(START, "control")

graph.add_conditional_edges(
    "control",
    lambda state: "ocr" if state["control_result"]["valid"] else "rejected",
    {"ocr": "ocr", "rejected": "audit_rejection"},
)

graph.add_edge("ocr", "extraction")
graph.add_edge("extraction", "validation")
graph.add_edge("validation", "audit_success")

graph.add_edge("audit_rejection", END)
graph.add_edge("audit_success", END)

workflow = graph.compile()
