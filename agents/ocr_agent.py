"""Agent de lecture hybride, compatible avec execute et execute_pages."""
import logging

from ocr.hybrid_reader import HybridReader

logger = logging.getLogger(__name__)


class OCRAgent:
    def __init__(self):
        self.ocr = HybridReader()

    def execute_pages(self, pdf_path: str):
        return self.ocr.document_to_pages(pdf_path)

    def execute(self, pdf_path: str) -> str:
        logger.info('[OCRAgent] Lecture du document : %s', pdf_path)
        text = self.ocr.pdf_to_text(pdf_path)
        logger.info('[OCRAgent] Lecture terminée (%d caractères).', len(text))
        return text