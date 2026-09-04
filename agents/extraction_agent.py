"""
===========================================================
Extraction Agent
Projet PFE Crédit Agricole du Maroc
===========================================================
"""

import logging
from typing import Any, Dict

from config.settings import settings
from extraction.extractor import DocumentExtractor
from extraction.sanitizer import scan_for_injection
from extraction.provenance import verify_sources
from rule_engine.checks import RULES

logger = logging.getLogger(__name__)


class ExtractionAgent:

    def __init__(self, model: str = settings.llm_model):

        logger.debug("Initialisation de l'Extraction Agent (%s)", model)

        self.extractor = DocumentExtractor(
            model=model
        )

    # =====================================================
    # EXTRACTION
    # =====================================================

    def run(
        self,
        ocr_text: str,
        document_type: str,
        pages=None,
        document_path=None,
        document_sha256=None,
    ) -> Dict[str, Any]:
        """
        Reçoit le texte OCR et retourne les données structurées,
        accompagnées du résultat du scan anti-injection.

        Retourne un dict :
            {
                "data": {...},          # valeurs aplaties, pour rule_engine
                "confidences": {...},   # champ -> confiance (EB-125)
                "raw": {...},           # dump imbriqué complet, pour l'audit
                "security": {
                    "suspicious": bool,
                    "matched_patterns": [...]
                }
            }
        """

        if not ocr_text:
            raise ValueError(
                "Le texte OCR est vide."
            )

        if not document_type:
            raise ValueError(
                "Le type de document est obligatoire."
            )

        if document_type not in RULES:
            raise ValueError(
                f"Type de document inconnu : {document_type} "
                f"(attendu parmi {list(RULES.keys())})"
            )

        # Isolation donnée / instruction : le texte OCR n'est jamais
        # envoyé tel quel, il est d'abord scanné. L'encadrement effectif
        # (délimiteurs) est appliqué dans extractor.py au moment de la
        # construction du prompt — ce scan sert ici à la traçabilité
        # et à la décision de revue humaine prioritaire.
        scan_result = scan_for_injection(ocr_text)

        if scan_result.suspicious:
            logger.warning(
                "[ExtractionAgent] Motifs suspects détectés (%s) "
                "pour un document de type %s",
                scan_result.matched_patterns,
                document_type,
            )

        logger.info("[ExtractionAgent] Traitement : %s", document_type)

        try:
            extraction_result = self.extractor.extract_json(
                ocr_text=ocr_text,
                document_type=document_type
            )
        except Exception:
            logger.exception(
                "[ExtractionAgent] Échec de l'extraction pour %s",
                document_type,
            )
            raise

        logger.info("[ExtractionAgent] Extraction terminée.")

        return {
            **extraction_result,  # data / confidences / raw
            "sources": verify_sources(
                extraction_result["raw"], pages or [], document_path, document_sha256
            ),
            "security": {
                "suspicious": scan_result.suspicious,
                "matched_patterns": scan_result.matched_patterns,
            },
        }
