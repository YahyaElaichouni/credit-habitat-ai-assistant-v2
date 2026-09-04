"""
===========================================================
PDF Utilities
Projet PFE Crédit Agricole du Maroc
===========================================================
"""

from pathlib import Path
import fitz
import cv2
import numpy as np


# ==========================================================
# PDF -> Images
# ==========================================================

def pdf_to_images(pdf_path, dpi=200):
    """
    Convertit toutes les pages d'un PDF en images OpenCV.

    Retour :
        list[np.ndarray]
    """

    pdf = fitz.open(pdf_path)

    images = []

    for page in pdf:

        pix = page.get_pixmap(dpi=dpi)

        img = np.frombuffer(
            pix.samples,
            dtype=np.uint8
        ).reshape(
            pix.height,
            pix.width,
            pix.n
        )

        # RGBA -> RGB

        if pix.n == 4:

            img = cv2.cvtColor(
                img,
                cv2.COLOR_RGBA2RGB
            )

        images.append(img)

    pdf.close()

    return images


# ==========================================================
# Images -> PDF
# ==========================================================

def images_to_pdf(images, output_pdf):

    pdf = fitz.open()

    for img in images:

        success, buffer = cv2.imencode(
            ".png",
            cv2.cvtColor(
                img,
                cv2.COLOR_RGB2BGR
            )
        )

        img_bytes = buffer.tobytes()

        h, w = img.shape[:2]

        page = pdf.new_page(
            width=w,
            height=h
        )

        page.insert_image(
            fitz.Rect(
                0,
                0,
                w,
                h
            ),
            stream=img_bytes
        )

    pdf.save(output_pdf)

    pdf.close()


# ==========================================================
# Apply augmentation
# ==========================================================

def process_pdf(
    input_pdf,
    output_pdf,
    augmentation_function,
    **kwargs
):
    """
    Charge un PDF,
    applique une augmentation,
    sauvegarde un nouveau PDF.
    """

    images = pdf_to_images(input_pdf)

    augmented = []

    for img in images:

        img_aug = augmentation_function(
            img,
            **kwargs
        )

        augmented.append(img_aug)

    images_to_pdf(
        augmented,
        output_pdf
    )


# ==========================================================
# Batch processing
# ==========================================================

def process_folder(
    input_folder,
    output_folder,
    augmentation_function,
    suffix,
    **kwargs
):

    input_folder = Path(input_folder)

    output_folder = Path(output_folder)

    output_folder.mkdir(
        parents=True,
        exist_ok=True
    )

    pdfs = sorted(
        input_folder.glob("*.pdf")
    )

    print(f"\n{len(pdfs)} PDF trouvés")

    for pdf in pdfs:

        output_pdf = output_folder / (
            pdf.stem +
            f"_{suffix}.pdf"
        )

        process_pdf(
            pdf,
            output_pdf,
            augmentation_function,
            **kwargs
        )

        print(
            f"✔ {output_pdf.name}"
        )

    print(
        "\nTraitement terminé."
    )
