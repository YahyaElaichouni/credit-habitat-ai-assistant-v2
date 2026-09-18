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
import re
import statistics
import unicodedata

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

        # Les bulletins portrait de faible résolution contiennent plusieurs
        # tableaux avec une police minuscule. Si la lecture globale perd les
        # repères essentiels, relire trois bandes agrandies améliore la
        # détection sans modifier les autres types de documents.
        height, width = image.shape[:2]
        if document_type == "bulletin" and max(height, width) < 1500:
            expected = ("PERIODE", "MATRICULE", "DATE D'EMBAUCHE", "FONCTION", "NET A PAYER")
            normalized = processed_text.replace("É", "E").replace("À", "A")
            if sum(marker in normalized for marker in expected) < 3:
                regional_lines = self._read_bulletin_regions(image)
                if self._business_document_score(regional_lines, "bulletin") > self._business_document_score(processed_lines, "bulletin"):
                    logger.info("Bulletin petit : lecture ciblée des tableaux retenue")
                    processed_lines = regional_lines
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

    def _read_bulletin_regions(self, image):
        """OCR par bandes avec coordonnées remappées sur la page originale."""
        height, width = image.shape[:2]
        regions = ((0.00, 0.38), (0.32, 0.82), (0.74, 1.00))
        collected = []
        scale = 2.2
        for start_ratio, end_ratio in regions:
            y0, y1 = int(height * start_ratio), int(height * end_ratio)
            crop = image[y0:y1, :]
            enlarged = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
            lines = self._prediction_to_lines(self.reader.predict(enlarged))
            for line in lines:
                box = line.get("bbox")
                try:
                    line["bbox"] = [
                        [float(point[0]) / scale, float(point[1]) / scale + y0]
                        for point in box
                    ]
                except (TypeError, ValueError, IndexError):
                    pass
                collected.append(line)

        # Supprimer uniquement les vrais doublons créés par le chevauchement
        # des bandes. Une déduplication basée sur le texte seul supprimait des
        # libellés légitimes répétés plus bas dans le bulletin (par exemple
        # « Salaire brut » dans le détail puis dans la zone Cumuls).
        unique = []
        for line in sorted(collected, key=lambda item: float(item.get("confidence") or 0), reverse=True):
            normalized = " ".join(str(line.get("text") or "").upper().split())
            if not normalized:
                continue
            center = self._box_center(line.get("bbox"))
            duplicate = False
            for kept in unique:
                if normalized != kept["_normalized_text"]:
                    continue
                kept_center = kept["_center"]
                # Sans coordonnées fiables, conserver les deux occurrences :
                # supprimer une vraie ligne serait plus grave qu'un doublon.
                if center is None or kept_center is None:
                    continue
                if abs(center[0] - kept_center[0]) <= 14 and abs(center[1] - kept_center[1]) <= 14:
                    duplicate = True
                    break
            if duplicate:
                continue
            line = dict(line)
            line["_normalized_text"] = normalized
            line["_center"] = center
            unique.append(line)
        for line in unique:
            line.pop("_normalized_text", None)
            line.pop("_center", None)
        return unique

    @staticmethod
    def _box_center(box):
        try:
            points = list(box)
            xs = [float(point[0]) for point in points]
            ys = [float(point[1]) for point in points]
            return (sum(xs) / len(xs), sum(ys) / len(ys))
        except (TypeError, ValueError, IndexError, ZeroDivisionError):
            return None

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
                    "x_max": max(xs),
                    "x_center": (min(xs) + max(xs)) / 2,
                    "y": (y_min + y_max) / 2,
                    "y_min": y_min,
                    "y_max": y_max,
                    "height": max(1.0, y_max - y_min),
                })
            except (TypeError, ValueError, IndexError):
                fallback.append((index, text))

        if not positioned:
            return "\n".join(text for _, text in sorted(fallback))

        typical_height = statistics.median(item["height"] for item in positioned)
        tolerance = max(5.0, typical_height * 0.60)
        rows = []
        for item in sorted(positioned, key=lambda value: (value["y"], value["x"])):
            best_row = None
            best_distance = None
            # Chercher dans quelques lignes récentes évite qu'une cellule un
            # peu plus haute ou plus basse soit isolée de sa ligne visuelle.
            for row in reversed(rows[-4:]):
                overlap = max(
                    0.0,
                    min(item["y_max"], row["y_max"])
                    - max(item["y_min"], row["y_min"]),
                )
                overlap_ratio = overlap / max(1.0, min(item["height"], row["height"]))
                distance = abs(item["y"] - row["center"])
                if overlap_ratio >= 0.25 or distance <= tolerance:
                    if best_distance is None or distance < best_distance:
                        best_row = row
                        best_distance = distance

            if best_row is None:
                rows.append({
                    "center": item["y"],
                    "y_min": item["y_min"],
                    "y_max": item["y_max"],
                    "height": item["height"],
                    "items": [item],
                })
                continue

            best_row["items"].append(item)
            best_row["center"] = statistics.median(value["y"] for value in best_row["items"])
            best_row["y_min"] = min(value["y_min"] for value in best_row["items"])
            best_row["y_max"] = max(value["y_max"] for value in best_row["items"])
            best_row["height"] = statistics.median(value["height"] for value in best_row["items"])

        # Repérer les colonnes financières depuis l'en-tête, sans nom de
        # banque ni coordonnées codées en dur. Le texte seul ne permet pas de
        # distinguer un montant débit d'un montant crédit lorsque la cellule
        # vide opposée disparaît. On conserve donc ici l'information
        # géométrique avant de la perdre.
        debit_center = None
        credit_center = None
        for row in rows:
            row_debit = []
            row_credit = []
            for item in row["items"]:
                normalized = unicodedata.normalize(
                    "NFKD", str(item["text"] or "")
                ).encode("ascii", "ignore").decode().casefold()
                normalized = re.sub(r"[^a-z]+", " ", normalized).strip()
                if re.search(r"\bdebit\b", normalized):
                    row_debit.append(item["x_center"])
                if re.search(r"\bcredit\b", normalized):
                    row_credit.append(item["x_center"])

            # Les deux intitulés doivent appartenir à la même ligne
            # d'en-tête. Cette contrainte empêche de prendre, plus bas, les
            # mots « intérêts débiteurs » ou « règlement crédit carte »
            # pour les coordonnées des colonnes.
            if row_debit and row_credit:
                candidate_debit = statistics.median(row_debit)
                candidate_credit = statistics.median(row_credit)
                if candidate_debit < candidate_credit:
                    debit_center = candidate_debit
                    credit_center = candidate_credit
                    break

        financial_columns = (
            debit_center is not None
            and credit_center is not None
            and debit_center < credit_center
        )
        if financial_columns:
            gap = credit_center - debit_center
            debit_left = debit_center - (gap * 0.65)
            credit_left = (debit_center + credit_center) / 2

        amount_pattern = re.compile(
            r"^[+-]?\s*\d[\d .\u00a0]*[,.]\d{2}\s*(?:MAD|DH|DHS)?$",
            re.I,
        )

        rendered = []
        for row in sorted(rows, key=lambda value: value["center"]):
            cells = []
            for value in sorted(row["items"], key=lambda value: value["x"]):
                cell = value["text"]
                if financial_columns and amount_pattern.fullmatch(cell.strip()):
                    if value["x_center"] >= credit_left:
                        cell = f"CREDIT: {cell}"
                    elif value["x_center"] >= debit_left:
                        cell = f"DEBIT: {cell}"
                cells.append(cell)
            rendered.append(" | ".join(cells))
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
