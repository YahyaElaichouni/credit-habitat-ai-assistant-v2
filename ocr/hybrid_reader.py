"""Lecture page par page : texte PDF natif, sinon OCR à résolution inchangée."""
import logging
import unicodedata
from time import perf_counter

import fitz

logger = logging.getLogger(__name__)


def usable_native_text(text):
    """Heuristique prudente, pas une garantie de justesse sémantique."""
    chars = [c for c in text if not c.isspace()]
    if len(chars) < 40 or sum(c.isalnum() for c in chars) < 20:
        return False
    bad = sum(c == '\ufffd' or unicodedata.category(c).startswith('C') for c in chars)
    return bad == 0 and '(cid:' not in text.lower()


class HybridReader:
    def __init__(self, ocr_factory=None, dpi=300):
        self._factory = ocr_factory
        self._ocr = None
        self.dpi = dpi

    def _get_ocr(self):
        # Aucun import PaddleOCR ni chargement de modèle pour un PDF numérique.
        if self._ocr is None:
            if self._factory is None:
                from ocr.ocr_engine import OCREngine
                self._ocr = OCREngine()
            else:
                self._ocr = self._factory()
        return self._ocr

    def document_to_pages(self, document_path):
        started = perf_counter()
        pages = []
        native_count = 0
        with fitz.open(document_path) as document:
            if document.needs_pass:
                raise ValueError('Document protégé par mot de passe.')
            total = len(document)
            for number, page in enumerate(document, start=1):
                tick = perf_counter()
                text = ''
                native = False
                if document.is_pdf:
                    try:
                        text = page.get_text('text', sort=True)
                        # Un scan avec seulement un titre numérique ne doit pas
                        # être pris pour une page entièrement textuelle.
                        area = max(page.rect.get_area(), 1)
                        image_area = sum(
                            (fitz.Rect(info['bbox']) & page.rect).get_area()
                            for info in page.get_image_info()
                        )
                        native = usable_native_text(text) and image_area / area < 0.20
                    except Exception:
                        logger.warning('Lecture native impossible page %d ; recours OCR.', number,
                                       exc_info=True)
                if native:
                    native_count += 1
                    mode = 'texte direct'
                else:
                    logger.info('Lecture page %d/%d — OCR en cours', number, total)
                    import numpy as np
                    pix = page.get_pixmap(dpi=self.dpi, colorspace=fitz.csRGB, alpha=False)
                    image = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                        pix.height, pix.width, 3).copy()
                    lines = self._get_ocr().image_to_text(image)
                    text = '\n'.join(line['text'] for line in lines)
                    mode = 'OCR'
                # Même contrat que l'ancien lecteur, pages vides comprises.
                pages.append({'page': number, 'text': text})
                logger.info('Lecture page %d/%d — %s — %d caractères — %.2f s',
                            number, total, mode, len(text), perf_counter() - tick)
        logger.info('Lecture terminée : %d pages directes, %d pages OCR — %.2f s',
                    native_count, len(pages) - native_count, perf_counter() - started)
        return pages

    def pdf_to_text(self, document_path):
        return '\n\n'.join(page['text'] for page in self.document_to_pages(document_path))
