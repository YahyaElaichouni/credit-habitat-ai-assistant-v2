"""
===========================================================
OCR Engine - PaddleOCR
Projet PFE Crédit Agricole du Maroc
===========================================================

NOTE IMPORTANTE : écrit pour l'API PaddleOCR 3.x (.predict(),
résultat sous forme de dict avec les clés "rec_texts"/"rec_scores").
Si `check_paddleocr_version.py` montre un format différent chez vous,
adaptez la méthode `image_to_text()` en conséquence.
"""

import logging

import cv2
from paddleocr import PaddleOCR

from ocr.pdf_loader import PDFLoader
from ocr.preprocessing import ImagePreprocessor

logger = logging.getLogger(__name__)


class OCREngine:

    def __init__(self):

        logger.info("Chargement de PaddleOCR...")

        self.reader = PaddleOCR(
            lang="fr",
            use_textline_orientation=True,
            engine="onnxruntime",
            # Ces deux étapes ajoutent chacune un modèle d'inférence
            # supplémentaire par page (PP-LCNet_x1_0_doc_ori, UVDoc) et
            # ne sont utiles que pour des scans de travers ou déformés.
            # Pour des documents déjà à plat et correctement orientés
            # (cas courant pour un scan/photo de CIN, bulletin...), les
            # désactiver réduit sensiblement le temps d'OCR par page.
            # Réactivez-les si vos documents de test sont réellement
            # tournés ou déformés.
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
        )

        self.loader = PDFLoader()

        self.preprocessor = ImagePreprocessor()

        logger.info("PaddleOCR prêt.")

    # =====================================================
    # OCR sur une image
    # =====================================================

    def image_to_text(self, image):
        """Prétraite l'image puis lance l'OCR.

        Retourne une liste de dicts {text, confidence, bbox},
        indépendamment du format de retour interne de PaddleOCR
        (isolé ici pour que le reste du code n'en dépende pas).
        """

        processed = self.preprocessor.preprocess(image)

        # Le pipeline interne de PaddleOCR (correction d'orientation,
        # redressement du document) attend une image à 3 canaux, même
        # si le contenu est en niveaux de gris. Notre préprocesseur
        # produit une image à un seul canal (grayscale/binarisée) :
        # on la reconvertit avant transmission, sinon PaddleOCR échoue
        # avec "IndexError: tuple index out of range" (img.shape[2]).
        if processed.ndim == 2:
            processed = cv2.cvtColor(processed, cv2.COLOR_GRAY2RGB)

        raw_result = self.reader.predict(processed)

        if not raw_result:
            return []

        page_result = raw_result[0]

        texts = page_result.get("rec_texts", [])
        scores = page_result.get("rec_scores", [])
        polys = page_result.get(
            "dt_polys",
            page_result.get("rec_polys", [None] * len(texts))
        )

        lines = []
        for text, score, box in zip(texts, scores, polys):
            lines.append({
                "text": text,
                "confidence": float(score),
                "bbox": box,
            })

        return lines

    # =====================================================
    # PDF -> Texte
    # =====================================================

    def pdf_to_text(self, pdf_path):
        return "\n\n".join(p["text"] for p in self.document_to_pages(pdf_path))

    def document_to_pages(self, document_path):
        """Conserve les limites de pages, y compris les pages sans texte."""
        pages = []
        for number, image in enumerate(self.loader.load(document_path), start=1):
            lines = self.image_to_text(image)
            pages.append({"page": number, "text": "\n".join(x["text"] for x in lines)})
        return pages

    # =====================================================
    # PDF -> JSON
    # =====================================================

    def pdf_to_json(self, pdf_path):

        pages = self.loader.load(pdf_path)

        document = []

        for page_number, image in enumerate(pages):

            lines = self.image_to_text(image)

            for line in lines:
                document.append({
                    "page": page_number + 1,
                    "text": line["text"],
                    "confidence": line["confidence"],
                    "bbox": line["bbox"],
                })

        return document
