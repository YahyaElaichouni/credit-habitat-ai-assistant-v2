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
import statistics

import cv2
from paddleocr import PaddleOCR

from ocr.pdf_loader import PDFLoader
from ocr.preprocessing import ImagePreprocessor

logger = logging.getLogger(__name__)


class OCREngine:

    def __init__(self):

        logger.info("Chargement de PaddleOCR...")

        self.reader = PaddleOCR(
            # Les tableaux du bulletin et du relevé comportent de petits
            # caractères : le modèle mobile les perdait. On conserve donc le
            # modèle précis et on gagne le temps sur la résolution d'entrée
            # (voir HybridReader), sans sacrifier les champs métier.
            lang="fr",
            ocr_version="PP-OCRv6",
            use_textline_orientation=False,
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

    def image_to_text(self, image, document_type=None):
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

        processed_lines = self._prediction_to_lines(self.reader.predict(processed))
        processed_text = " ".join(line["text"] for line in processed_lines).upper()

        # Les fonds colorés et les motifs de sécurité des CNIE peuvent perdre
        # des caractères lors de la binarisation. Pour ces pages seulement,
        # on compare avec la lecture de l'image originale et on conserve la
        # version qui contient le plus de repères identitaires utiles.
        height, width = image.shape[:2]
        identity_hint = (
            document_type == "carte_identite"
            or "CARTE NATIONALE" in processed_text
            or "IDMAR" in processed_text
            # Une face CNIE est paysage ; ce secours permet aussi l'usage
            # direct de l'OCREngine sans type explicite.
            or width / max(height, 1) >= 1.35
        )
        if identity_hint:
            original = image
            if original.ndim == 2:
                original = cv2.cvtColor(original, cv2.COLOR_GRAY2RGB)
            original_lines = self._prediction_to_lines(self.reader.predict(original))
            if self._identity_score(original_lines) > self._identity_score(processed_lines):
                logger.info("CNIE : lecture couleur originale retenue plutôt que la binarisation")
                return original_lines

        # Les filigranes des bulletins et les traits des relevés peuvent être
        # détériorés par Otsu. Une deuxième lecture couleur n'est lancée que
        # si trop peu de repères attendus ont survécu, puis la meilleure des
        # deux versions est conservée.
        if document_type in {"bulletin", "releve"}:
            processed_score = self._business_document_score(
                processed_lines, document_type
            )
            if processed_score < 18:
                original = image
                if original.ndim == 2:
                    original = cv2.cvtColor(original, cv2.COLOR_GRAY2RGB)
                original_lines = self._prediction_to_lines(self.reader.predict(original))
                original_score = self._business_document_score(
                    original_lines, document_type
                )
                if original_score > processed_score:
                    logger.info(
                        "%s : lecture couleur retenue (score %.1f contre %.1f)",
                        document_type, original_score, processed_score,
                    )
                    return original_lines

        return processed_lines

    @staticmethod
    def _prediction_to_lines(raw_result):
        if not raw_result:
            return []
        page_result = raw_result[0]
        texts = page_result.get("rec_texts", [])
        scores = page_result.get("rec_scores", [])
        polys = page_result.get("dt_polys", page_result.get("rec_polys", [None] * len(texts)))
        return [
            {"text": text, "confidence": float(score), "bbox": box}
            for text, score, box in zip(texts, scores, polys)
            if str(text).strip()
        ]

    @staticmethod
    def _identity_score(lines):
        text = " ".join(str(line.get("text") or "") for line in lines).upper()
        score = min(len(text), 600) / 100
        for marker in ("CARTE NATIONALE", "IDMAR", "VALABLE", "ADRESSE", "NÉ", "NE A"):
            if marker in text:
                score += 3
        score += 2 * len(__import__("re").findall(r"\b[A-Z]{1,2}\d{5,8}\b", text))
        score += len(__import__("re").findall(r"\b\d{2}[./-]\d{2}[./-]\d{4}\b", text))
        return score

    @staticmethod
    def _business_document_score(lines, document_type):
        """Score de complétude, utilisé uniquement pour choisir une variante OCR."""
        import re

        text = " ".join(str(line.get("text") or "") for line in lines).upper()
        markers = {
            "bulletin": (
                "BULLETIN", "SALAIRE", "BRUT", "NET", "RETENUES",
                "COMPTE", "GAINS", "DEDUCTIONS",
            ),
            "releve": (
                "RELEVE", "COMPTE", "DEBIT", "CREDIT", "SOLDE",
                "MOUVEMENT", "OPERATION",
            ),
        }[document_type]
        marker_score = 4 * sum(marker in text for marker in markers)
        amount_score = min(
            len(re.findall(r"\b\d[\d ]*[,.]\d{2}\b", text)), 12
        )
        readable_lines = min(len(lines), 30) / 5
        return marker_score + amount_score + readable_lines

    @staticmethod
    def lines_to_layout_text(lines):
        """Reconstruire les lignes visuelles et conserver l'ordre des colonnes.

        PaddleOCR retourne souvent chaque cellule d'un tableau comme un bloc
        séparé. Une concaténation naïve détruit l'association entre les
        cellules. Les blocs proches verticalement sont regroupés puis triés
        de gauche à droite. Le séparateur vertical rend les colonnes explicites
        pour l'extracteur et reste vérifiable par la provenance.
        """
        positioned = []
        fallback = []
        for index, item in enumerate(lines or []):
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            box = item.get("bbox")
            try:
                points = list(box)
                xs = [float(point[0]) for point in points]
                ys = [float(point[1]) for point in points]
                y_min, y_max = min(ys), max(ys)
                positioned.append({
                    "text": text,
                    "x": min(xs),
                    "y": (y_min + y_max) / 2,
                    "height": max(1.0, y_max - y_min),
                })
            except (TypeError, ValueError, IndexError):
                fallback.append((index, text))

        if not positioned:
            return "\n".join(text for _, text in sorted(fallback))

        typical_height = statistics.median(item["height"] for item in positioned)
        tolerance = max(8.0, typical_height * 0.65)
        rows = []
        for item in sorted(positioned, key=lambda value: (value["y"], value["x"])):
            if not rows or abs(item["y"] - rows[-1]["center"]) > tolerance:
                rows.append({"center": item["y"], "items": [item]})
            else:
                row = rows[-1]
                row["items"].append(item)
                row["center"] = sum(value["y"] for value in row["items"]) / len(row["items"])

        rendered = [
            " | ".join(value["text"] for value in sorted(row["items"], key=lambda value: value["x"]))
            for row in rows
        ]
        rendered.extend(text for _, text in sorted(fallback))
        return "\n".join(rendered)

    # =====================================================
    # PDF -> Texte
    # =====================================================

    def pdf_to_text(self, pdf_path):
        return "\n\n".join(p["text"] for p in self.document_to_pages(pdf_path))

    def document_to_pages(self, document_path, document_type=None):
        """Conserve les limites de pages, y compris les pages sans texte."""
        pages = []
        for number, image in enumerate(self.loader.load(document_path), start=1):
            lines = (
                self.image_to_text(image)
                if document_type is None
                else self.image_to_text(image, document_type=document_type)
            )
            pages.append({"page": number, "text": self.lines_to_layout_text(lines)})
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
