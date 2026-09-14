"""
Contrôle de qualité d'un document avant OCR.

Détecte notamment :
- document flou ;
- image trop sombre ou surexposée ;
- contraste insuffisant ;
- résolution trop faible ;
- document vide ou illisible.
"""

from pathlib import Path
from typing import Dict, List

import cv2
import fitz
import numpy as np


MAX_PDF_PAGES_TO_CHECK = 3
PDF_PREVIEW_DPI = 150


def _decode_image(content: bytes) -> np.ndarray:
    """Décoder une image JPEG, PNG ou TIFF avec OpenCV."""
    array = np.frombuffer(content, dtype=np.uint8)
    image = cv2.imdecode(array, cv2.IMREAD_COLOR)

    if image is None:
        raise ValueError("L'image ne peut pas être lue.")

    return image


def _render_pdf_pages(content: bytes) -> List[np.ndarray]:
    """Transformer les premières pages d'un PDF en images OpenCV."""
    document = fitz.open(stream=content, filetype="pdf")
    pages = []

    try:
        if document.page_count == 0:
            raise ValueError("Le PDF ne contient aucune page.")

        page_limit = min(document.page_count, MAX_PDF_PAGES_TO_CHECK)

        for page_number in range(page_limit):
            page = document.load_page(page_number)
            pixmap = page.get_pixmap(dpi=PDF_PREVIEW_DPI, alpha=False)

            image = np.frombuffer(
                pixmap.samples,
                dtype=np.uint8,
            ).reshape(
                pixmap.height,
                pixmap.width,
                pixmap.n,
            )

            if pixmap.n == 1:
                image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
            else:
                image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)

            pages.append(image.copy())
    finally:
        document.close()

    return pages


def _normalize_for_measurement(gray: np.ndarray) -> np.ndarray:
    """Limiter la taille de calcul sans modifier le document original."""
    height, width = gray.shape[:2]
    longest_side = max(height, width)

    if longest_side <= 1600:
        return gray

    scale = 1600 / longest_side

    return cv2.resize(
        gray,
        None,
        fx=scale,
        fy=scale,
        interpolation=cv2.INTER_AREA,
    )


def _analyze_page(image: np.ndarray, page_number: int) -> Dict:
    """Calculer les indicateurs de qualité d'une page."""
    if image is None or image.size == 0:
        return {
            "page": page_number,
            "score": 0,
            "blocking": True,
            "issues": ["La page est vide ou illisible."],
        }

    height, width = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    measured_gray = _normalize_for_measurement(gray)

    brightness = float(np.mean(measured_gray))
    contrast = float(np.std(measured_gray))
    blur = float(cv2.Laplacian(measured_gray, cv2.CV_64F).var())

    score = 100
    issues = []
    critical_issues = 0

    # Document pratiquement uniforme : page blanche, noire ou illisible.
    if contrast < 8:
        score -= 70
        critical_issues += 1
        issues.append("La page paraît vide ou presque uniforme.")
    elif contrast < 25:
        score -= 20
        issues.append("Le contraste est faible.")

    # Mesure du flou.
    if blur < 25:
        score -= 45
        critical_issues += 1
        issues.append("Le document est fortement flou.")
    elif blur < 70:
        score -= 20
        issues.append("Le document est légèrement flou.")

    # Mesure de l'exposition.
    if brightness < 35:
        score -= 40
        critical_issues += 1
        issues.append("Le document est beaucoup trop sombre.")
    elif brightness < 55:
        score -= 15
        issues.append("Le document est un peu sombre.")
    elif brightness > 235:
        score -= 40
        critical_issues += 1
        issues.append("Le document est fortement surexposé.")
    elif brightness > 215:
        score -= 15
        issues.append("Le document est un peu trop clair.")

    # Résolution originale.
    shortest_side = min(height, width)

    if shortest_side < 450:
        score -= 35
        critical_issues += 1
        issues.append("La résolution est beaucoup trop faible.")
    elif shortest_side < 700:
        score -= 15
        issues.append("La résolution est faible.")

    score = max(0, min(100, round(score)))

    return {
        "page": page_number,
        "score": score,
        "blocking": score < 30 or critical_issues >= 2,
        "issues": issues,
        "metrics": {
            "width": width,
            "height": height,
            "brightness": round(brightness, 1),
            "contrast": round(contrast, 1),
            "sharpness": round(blur, 1),
        },
    }


def analyze_document_quality(content: bytes, filename: str) -> Dict:
    """
    Contrôler la qualité d'un document envoyé par l'utilisateur.

    Retourne un dictionnaire directement exploitable par Streamlit.
    """
    if not content:
        return {
            "status": "bad",
            "score": 0,
            "blocking": True,
            "message": "Le fichier est vide.",
            "issues": ["Sélectionnez un autre fichier."],
            "pages": [],
        }

    extension = Path(filename).suffix.lower()

    try:
        if extension == ".pdf":
            images = _render_pdf_pages(content)
        else:
            images = [_decode_image(content)]
    except Exception as error:
        return {
            "status": "bad",
            "score": 0,
            "blocking": True,
            "message": "Le document ne peut pas être analysé.",
            "issues": [str(error)],
            "pages": [],
        }

    page_results = [
        _analyze_page(image, page_number=index + 1)
        for index, image in enumerate(images)
    ]

    worst_score = min(page["score"] for page in page_results)
    blocking = any(page["blocking"] for page in page_results)

    issues = []

    for page in page_results:
        for issue in page["issues"]:
            if len(page_results) > 1:
                formatted_issue = f"Page {page['page']} : {issue}"
            else:
                formatted_issue = issue

            if formatted_issue not in issues:
                issues.append(formatted_issue)

    if blocking:
        status = "bad"
        message = (
            "La qualité est insuffisante pour garantir une lecture fiable. "
            "Veuillez reprendre une photo ou envoyer un meilleur scan."
        )
    elif worst_score < 75:
        status = "warning"
        message = (
            "Le document peut être analysé, mais sa qualité pourrait réduire "
            "la précision de la lecture."
        )
    else:
        status = "good"
        message = "La qualité du document est suffisante pour l'analyse."

    return {
        "status": status,
        "score": worst_score,
        "blocking": blocking,
        "message": message,
        "issues": issues,
        "pages": page_results,
    }