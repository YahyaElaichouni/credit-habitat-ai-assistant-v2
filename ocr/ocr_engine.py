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


def _onnx_engine_config():
    """Employer CUDA quand il est disponible, sinon rester utilisable sur CPU."""
    try:
        import onnxruntime as ort

        available = ort.get_available_providers()
    except Exception as exc:
        logger.warning(
            "ONNX Runtime indisponible lors de la détection du GPU : %s",
            exc,
        )
        available = []

    if "CUDAExecutionProvider" in available:
        try:
            # Les wheels ``onnxruntime-gpu[cuda,cudnn]`` installent les DLL
            # NVIDIA dans site-packages, qui n'est pas ajouté au PATH par
            # Windows. Le préchargement doit donc précéder la création des
            # sessions PaddleOCR ; sinon ONNX annonce CUDA mais échoue ensuite
            # à créer le provider et retombe silencieusement sur le CPU.
            ort.preload_dlls(directory="")
            logger.info(
                "DLL CUDA/cuDNN préchargées — PaddleOCR utilisera "
                "CUDAExecutionProvider (GPU 0)"
            )
            return {
                "device_type": "gpu",
                "device_id": 0,
                "providers": ["CUDAExecutionProvider", "CPUExecutionProvider"],
            }
        except Exception as exc:
            logger.warning(
                "Préchargement CUDA/cuDNN impossible (%s) ; "
                "PaddleOCR utilisera le CPU",
                exc,
            )

    logger.info("PaddleOCR utilisera CPUExecutionProvider")
    return {
        "device_type": "cpu",
        "providers": ["CPUExecutionProvider"],
    }


class OCREngine:

    def __init__(self):

        logger.info("Chargement de PaddleOCR...")

        self.reader = PaddleOCR(
            lang="fr",
            ocr_version="PP-OCRv6",
            use_textline_orientation=False,
            engine="onnxruntime",
            engine_config=_onnx_engine_config(),
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

        height, width = image.shape[:2]
        original_lines = None

        # Les CNIE récentes ont des fonds colorés et des motifs de sécurité :
        # dans les jeux de test, la couleur gagne presque toujours contre la
        # binarisation. On commence donc par elle et on ne paie le coût d'une
        # seconde lecture que si les preuves identitaires restent pauvres.
        if document_type == "carte_identite":
            original = image
            if original.ndim == 2:
                original = cv2.cvtColor(original, cv2.COLOR_GRAY2RGB)
            original_lines = self._prediction_to_lines(
                self.reader.predict(original)
            )
            if self._identity_color_is_sufficient(original_lines):
                logger.info(
                    "CNIE : lecture couleur suffisante, binarisation évitée"
                )
                return original_lines
            logger.info(
                "CNIE : preuves couleur incomplètes, comparaison avec la binarisation"
            )

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
        # tableaux avec une police minuscule. Ne relire que la partie de page
        # susceptible de contenir les repères absents ; une relecture complète
        # reste disponible si cette passe ciblée n'apporte aucune amélioration.
        if document_type == "bulletin" and max(height, width) < 1500:
            normalized = processed_text.replace("É", "E").replace("À", "A")
            aliases = {
                "PERIODE": ("PERIODE", "PERIOD", "MOIS DE PAIE"),
                "DATE D'EMBAUCHE": (
                    "DATE D'EMBAUCHE", "DATE EMBAUCHE", "DATE D'ENTREE",
                    "DATE ENTREE", "ENTREE:", "HIRE DATE", "START DATE",
                ),
                "NET A PAYER": (
                    "NET A PAYER", "NET PAYE", "SALAIRE NET", "NET PAY",
                ),
            }
            missing_markers = tuple(
                marker
                for marker, variants in aliases.items()
                if not any(variant in normalized for variant in variants)
            )
            if missing_markers:
                initial_score = self._business_document_score(
                    processed_lines, "bulletin"
                )
                targeted_lines = self._read_bulletin_regions(
                    image, missing_markers=missing_markers
                )
                targeted_result = self._merge_ocr_lines(
                    processed_lines, targeted_lines
                )
                targeted_score = self._business_document_score(
                    targeted_result, "bulletin"
                )
                if targeted_score > initial_score:
                    logger.info(
                        "Bulletin petit : relecture ciblée retenue pour %s",
                        ", ".join(missing_markers),
                    )
                    processed_lines = targeted_result
                    processed_text = " ".join(
                        line["text"] for line in processed_lines
                    ).upper()
                else:
                    # Cas rare : document atypique ou champs situés hors des
                    # zones habituelles. On conserve alors le secours complet
                    # historique afin de ne pas dégrader la qualité.
                    full_regional_lines = self._read_bulletin_regions(image)
                    full_result = self._merge_ocr_lines(
                        processed_lines, full_regional_lines
                    )
                    if self._business_document_score(
                        full_result, "bulletin"
                    ) > initial_score:
                        logger.info(
                            "Bulletin petit : relecture complète de secours retenue"
                        )
                        processed_lines = full_result
                        processed_text = " ".join(
                            line["text"] for line in processed_lines
                        ).upper()

        # Les fonds colorés et les motifs de sécurité des CNIE peuvent perdre
        # des caractères lors de la binarisation. Pour ces pages seulement,
        # on compare avec la lecture de l'image originale et on conserve la
        # version qui contient le plus de repères identitaires utiles.
        identity_hint = (
            document_type == "carte_identite"
            or "CARTE NATIONALE" in processed_text
            or "IDMAR" in processed_text
            # Une face CNIE est paysage ; ce secours permet aussi l'usage
            # direct de l'OCREngine sans type explicite.
            or width / max(height, 1) >= 1.35
        )
        if identity_hint:
            if original_lines is None:
                original = image
                if original.ndim == 2:
                    original = cv2.cvtColor(original, cv2.COLOR_GRAY2RGB)
                original_lines = self._prediction_to_lines(
                    self.reader.predict(original)
                )
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
            statement_detail_score = (
                self._statement_detail_score(processed_lines)
                if document_type == "releve"
                else None
            )
            # Un relevé peut obtenir un excellent score global uniquement
            # grâce à son en-tête et à ses montants, tout en ayant perdu les
            # dates et libellés des opérations. C'était le cas des scans CIH :
            # le calcul recevait « CREDIT: 500,00 » sans « VIREMENT RECU ».
            # Dans ce cas, comparer aussi la lecture couleur complète.
            needs_original = processed_score < 18 or (
                document_type == "releve" and statement_detail_score < 12
            )
            if needs_original:
                original = image
                if original.ndim == 2:
                    original = cv2.cvtColor(original, cv2.COLOR_GRAY2RGB)
                original_lines = self._prediction_to_lines(self.reader.predict(original))
                original_score = self._business_document_score(
                    original_lines, document_type
                )
                original_detail_score = (
                    self._statement_detail_score(original_lines)
                    if document_type == "releve"
                    else None
                )
                if (
                    original_score > processed_score
                    or (
                        document_type == "releve"
                        and original_detail_score > statement_detail_score
                    )
                ):
                    logger.info(
                        "%s : lecture couleur retenue (score %.1f/%.1f, détail %s/%s)",
                        document_type, original_score, processed_score,
                        original_detail_score, statement_detail_score,
                    )
                    processed_lines = original_lines
                    processed_score = original_score
                    statement_detail_score = original_detail_score

            # Si la lecture globale reste pauvre en vraies opérations, relire
            # la page par bandes agrandies. Cette passe conserve les coordonnées
            # originales pour reconstruire correctement Débit et Crédit.
            if document_type == "releve" and statement_detail_score < 12:
                regional_lines = self._read_statement_regions(image)
                regional_detail_score = self._statement_detail_score(regional_lines)
                if regional_detail_score > statement_detail_score:
                    logger.info(
                        "Relevé : lecture agrandie par bandes retenue "
                        "(détail %.1f contre %.1f)",
                        regional_detail_score, statement_detail_score,
                    )
                    processed_lines = regional_lines

            # Dernière passe exclusivement réservée aux relevés : relire la
            # colonne CREDIT seule. Le recadrage supprime les libellés et les
            # traits voisins qui rendent les petits montants CIH difficiles à
            # reconnaître. Les coordonnées sont remappées sur la page afin de
            # rattacher chaque montant à sa ligne d'opération lors du rendu.
            if (
                document_type == "releve"
                and self._statement_credit_pass_needed(
                    processed_lines, image.shape[1]
                )
            ):
                credit_lines = self._read_statement_credit_column(
                    image, processed_lines
                )
                if credit_lines:
                    processed_lines = self._merge_statement_credit_lines(
                        processed_lines, credit_lines
                    )
            elif document_type == "releve":
                logger.info(
                    "Relevé : montants crédit déjà associés, passe ciblée évitée"
                )

        return processed_lines

    @classmethod
    def _statement_credit_geometry(cls, lines, image_width):
        """Localise la colonne CREDIT depuis les en-têtes Débit/Crédit."""
        headers = []
        for item in lines or []:
            text = unicodedata.normalize(
                "NFKD", str(item.get("text") or "")
            ).encode("ascii", "ignore").decode().casefold()
            text = re.sub(r"[^a-z]+", " ", text).strip()
            if not re.search(r"\b(?:debit|credit)\b", text):
                continue
            bounds = cls._box_bounds(item.get("bbox"))
            center = cls._box_center(item.get("bbox"))
            if bounds and center:
                headers.append((text, bounds, center))

        for debit_text, debit_bounds, debit_center in headers:
            if not re.search(r"\bdebit\b", debit_text):
                continue
            for credit_text, credit_bounds, credit_center in headers:
                if not re.search(r"\bcredit\b", credit_text):
                    continue
                typical_height = max(
                    debit_bounds[3] - debit_bounds[1],
                    credit_bounds[3] - credit_bounds[1],
                    1.0,
                )
                if (
                    debit_center[0] >= credit_center[0]
                    or abs(debit_center[1] - credit_center[1]) > typical_height * 1.8
                ):
                    continue
                gap = credit_center[0] - debit_center[0]
                x0 = max(0, int((debit_center[0] + credit_center[0]) / 2))
                x1 = min(
                    int(image_width),
                    int(credit_center[0] + max(gap * 0.80, typical_height * 3)),
                )
                y0 = max(0, int(max(debit_bounds[3], credit_bounds[3])))
                if x1 - x0 >= 20:
                    return x0, x1, y0
        return None

    @classmethod
    def _statement_credit_pass_needed(cls, lines, image_width):
        """Relire CREDIT seulement si une entrée détectée n'a pas de montant."""
        geometry = cls._statement_credit_geometry(lines, image_width)
        if geometry is None:
            return False
        x0, x1, y0 = geometry
        incoming_pattern = re.compile(
            r"\b(?:(?:virement|virt)\s+(?:recu|en\s+votre\s+faveur)|"
            r"reception\s+d\s+un\s+virement|versement|remise\s+(?:de\s+)?cheque)\b",
            re.I,
        )
        amount_pattern = re.compile(
            r"^[+-]?\s*\d[\d .\u00a0:]*[,.]\s*\d{2}\s*(?:MAD|DH|DHS)?$",
            re.I,
        )
        incoming_rows = []
        credit_rows = []
        for item in lines or []:
            text = str(item.get("text") or "").strip()
            normalized_text = unicodedata.normalize("NFKD", text).encode(
                "ascii", "ignore"
            ).decode()
            normalized_text = re.sub(r"[^a-zA-Z0-9]+", " ", normalized_text)
            center = cls._box_center(item.get("bbox"))
            bounds = cls._box_bounds(item.get("bbox"))
            if center is None or bounds is None or center[1] <= y0:
                continue
            row = (center[1], max(bounds[3] - bounds[1], 1.0))
            if incoming_pattern.search(normalized_text):
                incoming_rows.append(row)
            if x0 <= center[0] <= x1 and amount_pattern.fullmatch(text):
                credit_rows.append(row)

        if not incoming_rows:
            return False
        for incoming_y, incoming_height in incoming_rows:
            if not any(
                abs(incoming_y - amount_y)
                <= max(18.0, incoming_height * 2.2, amount_height * 2.2)
                for amount_y, amount_height in credit_rows
            ):
                return True
        return False

    def _read_statement_credit_column(self, image, reference_lines):
        """OCR agrandi de toutes les cellules monétaires de la colonne crédit."""
        height, width = image.shape[:2]
        geometry = self._statement_credit_geometry(reference_lines, width)
        if geometry is None:
            logger.info(
                "Relevé : en-têtes Débit/Crédit non localisés, "
                "passe ciblée ignorée"
            )
            return []

        x0, x1, y0 = geometry
        amount_pattern = re.compile(
            r"^[+-]?\s*\d[\d .\u00a0:]*[,.]\s*\d{2}\s*(?:MAD|DH|DHS)?$",
            re.I,
        )
        scale = 3.0
        # Des bandes qui se chevauchent limitent la taille d'inférence tout en
        # évitant de couper une opération située exactement sur une frontière.
        usable_height = max(height - y0, 1)
        ratios = ((0.00, 0.38), (0.30, 0.68), (0.60, 1.00))
        collected = []
        for start_ratio, end_ratio in ratios:
            band_y0 = y0 + int(usable_height * start_ratio)
            band_y1 = y0 + int(usable_height * end_ratio)
            crop = image[band_y0:band_y1, x0:x1]
            if crop.size == 0:
                continue
            enlarged = cv2.resize(
                crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC
            )
            for raw in self._prediction_to_lines(self.reader.predict(enlarged)):
                text = str(raw.get("text") or "").strip()
                # Corriger uniquement le ':' inséré au milieu d'un montant
                # (ex. 88:0,00 -> 880,00), jamais une date ou une heure.
                normalized = re.sub(
                    r"(?<=\d):(?=\d{1,3}[,.]\s*\d{2}$)", "", text
                )
                if not amount_pattern.fullmatch(normalized):
                    continue
                line = dict(raw)
                line["text"] = normalized
                try:
                    line["bbox"] = [
                        [float(point[0]) / scale + x0,
                         float(point[1]) / scale + band_y0]
                        for point in raw.get("bbox")
                    ]
                except (TypeError, ValueError, IndexError):
                    continue
                collected.append(line)

        # Dédupliquer les cellules relues dans le chevauchement des bandes.
        unique = []
        for line in sorted(
            collected,
            key=lambda item: float(item.get("confidence") or 0),
            reverse=True,
        ):
            center = self._box_center(line.get("bbox"))
            bounds = self._box_bounds(line.get("bbox"))
            if center is None or bounds is None:
                continue
            if any(
                self._boxes_same_region(bounds, kept["bounds"])
                or (
                    abs(center[0] - kept["center"][0]) <= 10
                    and abs(center[1] - kept["center"][1]) <= 8
                )
                for kept in unique
            ):
                continue
            unique.append({"line": line, "center": center, "bounds": bounds})
        logger.info(
            "Relevé : %d cellule(s) monétaire(s) relue(s) dans CREDIT",
            len(unique),
        )
        return [item["line"] for item in unique]

    @classmethod
    def _merge_statement_credit_lines(cls, base_lines, credit_lines):
        """Remplace les anciennes lectures de la même cellule puis fusionne."""
        result = list(base_lines or [])
        amount_pattern = re.compile(
            r"^[+-]?\s*\d[\d .\u00a0:]*[,.]\s*\d{2}\s*(?:MAD|DH|DHS)?$",
            re.I,
        )
        for credit in credit_lines or []:
            credit_center = cls._box_center(credit.get("bbox"))
            credit_bounds = cls._box_bounds(credit.get("bbox"))
            if credit_center is None or credit_bounds is None:
                continue
            filtered = []
            for existing in result:
                existing_text = str(existing.get("text") or "").strip()
                existing_center = cls._box_center(existing.get("bbox"))
                existing_bounds = cls._box_bounds(existing.get("bbox"))
                same_cell = (
                    amount_pattern.fullmatch(existing_text)
                    and existing_center is not None
                    and existing_bounds is not None
                    and (
                        cls._boxes_same_region(existing_bounds, credit_bounds)
                        or (
                            abs(existing_center[0] - credit_center[0]) <= 24
                            and abs(existing_center[1] - credit_center[1]) <= 8
                        )
                    )
                )
                if not same_cell:
                    filtered.append(existing)
            filtered.append(credit)
            result = filtered
        return result

    def _read_statement_regions(self, image):
        """Relit un relevé en bandes agrandies, en gardant sa géométrie."""
        height, _ = image.shape[:2]
        # Couverture complète : l'en-tête reste disponible pour le nom de la
        # banque et les bandes centrales renforcent les petites opérations.
        regions = ((0.00, 0.32), (0.25, 0.58), (0.51, 0.84), (0.77, 1.00))
        scale = 2.0
        collected = []
        for start_ratio, end_ratio in regions:
            y0, y1 = int(height * start_ratio), int(height * end_ratio)
            crop = image[y0:y1, :]
            enlarged = cv2.resize(
                crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC
            )
            lines = self._prediction_to_lines(self.reader.predict(enlarged))
            for line in lines:
                line = dict(line)
                box = line.get("bbox")
                try:
                    line["bbox"] = [
                        [float(point[0]) / scale, float(point[1]) / scale + y0]
                        for point in box
                    ]
                except (TypeError, ValueError, IndexError):
                    pass
                collected.append(line)

        # Les zones se chevauchent. La même cellule peut être reconnue deux
        # fois avec des textes légèrement différents (par exemple 2 000,00 et
        # 2 600,00). La comparaison doit donc d'abord être géométrique et non
        # textuelle ; la liste est triée par confiance afin de conserver la
        # meilleure lecture du même emplacement.
        unique = []
        for line in sorted(
            collected,
            key=lambda item: float(item.get("confidence") or 0),
            reverse=True,
        ):
            normalized = " ".join(str(line.get("text") or "").upper().split())
            center = self._box_center(line.get("bbox"))
            if not normalized:
                continue
            duplicate = False
            bounds = self._box_bounds(line.get("bbox"))
            for kept in unique:
                other = kept["center"]
                same_region = self._boxes_same_region(bounds, kept["bounds"])
                same_text_position = (
                    normalized == kept["normalized"]
                    and center and other
                    and abs(center[0] - other[0]) <= 12
                    and abs(center[1] - other[1]) <= 12
                )
                if same_region or same_text_position:
                    duplicate = True
                    break
            if not duplicate:
                unique.append({
                    "line": line,
                    "normalized": normalized,
                    "center": center,
                    "bounds": bounds,
                })
        return [item["line"] for item in unique]

    def _read_bulletin_regions(self, image, missing_markers=None):
        """Relit uniquement les zones utiles, ou toutes les bandes en secours."""
        height, width = image.shape[:2]
        missing = set(missing_markers or ())
        if missing:
            upper_markers = {
                "PERIODE", "DATE D'EMBAUCHE"
            }
            regions = []
            if missing & upper_markers:
                # Identité professionnelle, période et date d'embauche sont
                # généralement regroupées dans les deux premiers tiers.
                regions.append((0.00, 0.70))
            if "NET A PAYER" in missing:
                # Le net se trouve habituellement dans la moitié inférieure.
                regions.append((0.48, 1.00))
            regions = tuple(regions)
        else:
            regions = ((0.00, 0.38), (0.32, 0.82), (0.74, 1.00))
        collected = []
        combined_pass = len(regions) == 2
        if combined_pass:
            # Lorsque le haut et le bas sont tous deux nécessaires, leurs deux
            # grandes zones se chevauchent fortement. Une seule passe plafonnée
            # traite moins de pixels et évite une seconde inférence PaddleOCR.
            regions = ((0.00, 1.00),)
        for start_ratio, end_ratio in regions:
            y0, y1 = int(height * start_ratio), int(height * end_ratio)
            crop = image[y0:y1, :]
            # Le plafond évite les images OCR surdimensionnées lorsque le
            # document source est déjà assez grand.
            longest_side = max(crop.shape[:2])
            max_scale = 1.6 if combined_pass else 2.2
            max_side = 1600.0 if combined_pass else 1500.0
            scale = min(max_scale, max_side / max(longest_side, 1))
            scale = max(scale, 1.0)
            enlarged = cv2.resize(
                crop,
                None,
                fx=scale,
                fy=scale,
                interpolation=cv2.INTER_CUBIC,
            )
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

    @classmethod
    def _merge_ocr_lines(cls, base_lines, extra_lines):
        """Fusionne deux lectures en conservant la meilleure par zone."""
        candidates = list(base_lines or []) + list(extra_lines or [])
        kept = []
        for line in sorted(
            candidates,
            key=lambda item: float(item.get("confidence") or 0),
            reverse=True,
        ):
            text = str(line.get("text") or "").strip()
            bounds = cls._box_bounds(line.get("bbox"))
            if not text:
                continue
            if bounds is not None and any(
                cls._boxes_same_region(bounds, item["bounds"])
                for item in kept
                if item["bounds"] is not None
            ):
                continue
            kept.append({"line": dict(line), "bounds": bounds})
        return [item["line"] for item in kept]

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
    def _box_bounds(box):
        try:
            points = list(box)
            xs = [float(point[0]) for point in points]
            ys = [float(point[1]) for point in points]
            return min(xs), min(ys), max(xs), max(ys)
        except (TypeError, ValueError, IndexError):
            return None

    @staticmethod
    def _boxes_same_region(first, second):
        """Détecte deux lectures du même bloc dans des bandes superposées."""
        if first is None or second is None:
            return False
        ax0, ay0, ax1, ay1 = first
        bx0, by0, bx1, by1 = second
        intersection_w = max(0.0, min(ax1, bx1) - max(ax0, bx0))
        intersection_h = max(0.0, min(ay1, by1) - max(ay0, by0))
        intersection = intersection_w * intersection_h
        smaller = min(max((ax1 - ax0) * (ay1 - ay0), 1.0),
                      max((bx1 - bx0) * (by1 - by0), 1.0))
        return intersection / smaller >= 0.72

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

    @classmethod
    def _identity_color_is_sufficient(cls, lines):
        """Évite la variante binarisée seulement avec une vraie preuve CNIE."""

        text = " ".join(str(line.get("text") or "") for line in lines).upper()
        normalized = unicodedata.normalize("NFKD", text).encode(
            "ascii", "ignore"
        ).decode()
        has_identity_marker = any(marker in normalized for marker in (
            "CARTE NATIONALE", "IDMAR", "ROYAUME DU MAROC", "IDENTITE",
        ))
        has_identifier = bool(re.search(r"\b[A-Z]{1,2}\s*\d{5,8}\b", normalized))
        has_full_date = bool(re.search(r"\b\d{2}[./-]\d{2}[./-]\d{4}\b", normalized))
        return (
            len(normalized.strip()) >= 100
            and has_identity_marker
            and has_identifier
            and has_full_date
            and cls._identity_score(lines) >= 9.0
        )

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
    def _statement_detail_score(lines):
        """Mesure la présence d'opérations exploitables, pas seulement de montants."""
        text = "\n".join(str(line.get("text") or "") for line in lines)
        normalized = unicodedata.normalize("NFKD", text).encode(
            "ascii", "ignore"
        ).decode().lower()
        dates = len(re.findall(r"(?<!\d)\d{1,2}\s*[./-]\s*\d{1,2}(?!\d)", normalized))
        operation_words = len(re.findall(
            r"\b(?:virement|virt|versement|retrait|paiement|prelevement|"
            r"commission|frais|echeance|remboursement|recu|emis)\w*\b",
            normalized,
        ))
        descriptions = sum(
            1 for line in normalized.splitlines()
            if len(re.findall(r"[a-z]{3,}", line)) >= 2
        )
        # Plusieurs dates ET plusieurs libellés sont nécessaires au calcul.
        # Les plafonds empêchent un long pied de page d'écraser le diagnostic.
        return min(dates, 8) + min(operation_words, 8) + min(descriptions, 8) / 2

    @staticmethod
    def lines_to_layout_text(lines, document_type=None):
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
        normalized_labels = {
            re.sub(
                r"[^a-z]+",
                " ",
                unicodedata.normalize("NFKD", item["text"])
                .encode("ascii", "ignore")
                .decode()
                .casefold(),
            ).strip()
            for item in positioned
        }
        statement_layout = document_type == "releve" or (
            document_type is None
            and any(re.search(r"\bdebit\b", label) for label in normalized_labels)
            and any(re.search(r"\bcredit\b", label) for label in normalized_labels)
        )
        # La tolérance stricte évite de fusionner deux opérations CIH, mais
        # elle ne doit pas modifier la reconstruction historique des bulletins.
        tolerance_factor = 0.38 if statement_layout else 0.60
        tolerance = max(3.0, typical_height * tolerance_factor)
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
                if overlap_ratio >= 0.55 or distance <= tolerance:
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
            pages.append({
                "page": number,
                "text": self.lines_to_layout_text(
                    lines, document_type=document_type
                ),
            })
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
