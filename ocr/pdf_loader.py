"""
===========================================================
PDF Loader
Convertit un PDF en images OpenCV
===========================================================
"""

from pathlib import Path
import fitz
import cv2
import numpy as np


class PDFLoader:

    def __init__(self, dpi=300):
        self.dpi = dpi

    def load(self, pdf_path):
        """
        Convertit toutes les pages d'un PDF
        en images OpenCV (RGB).
        """

        pdf_path = Path(pdf_path)

        if not pdf_path.exists():
            raise FileNotFoundError(f"{pdf_path} introuvable.")

        document = fitz.open(pdf_path)

        pages = []

        try:
            for page in document:

                pix = page.get_pixmap(dpi=self.dpi)

                img = np.frombuffer(
                    pix.samples,
                    dtype=np.uint8
                ).reshape(
                    pix.height,
                    pix.width,
                    pix.n
                )

                if pix.n == 4:
                    img = cv2.cvtColor(
                        img,
                        cv2.COLOR_RGBA2RGB
                    )
                elif pix.n == 1:
                    # Cas rare (PDF en niveaux de gris) : uniformiser
                    # vers 3 canaux pour que le reste du pipeline
                    # (preprocessing, PaddleOCR) reçoive toujours
                    # un format cohérent.
                    img = cv2.cvtColor(
                        img,
                        cv2.COLOR_GRAY2RGB
                    )

                # np.frombuffer crée un tableau en lecture seule, lié
                # à la mémoire interne de PyMuPDF. On copie explicitement
                # pour éviter tout comportement indéfini une fois que
                # `document` est fermé plus bas.
                pages.append(img.copy())

        finally:
            document.close()

        return pages
