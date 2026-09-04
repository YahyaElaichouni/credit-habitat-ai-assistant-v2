"""
===========================================================
Image Augmentations
Projet PFE Crédit Agricole du Maroc
===========================================================
"""

import cv2
import numpy as np
import random


# ==========================================================
# BLUR
# ==========================================================

def apply_blur(image, level="medium"):
    """
    Flou gaussien
    """

    kernels = {
        "easy": (9, 9),
        "medium": (17, 17),
        "hard": (31, 31)
    }

    kernel = kernels.get(level, (17, 17))

    return cv2.GaussianBlur(image, kernel, 0)


# ==========================================================
# ROTATION
# ==========================================================

def apply_rotation(image):

    h, w = image.shape[:2]

    angle = random.uniform(-7, 7)

    matrix = cv2.getRotationMatrix2D(
        (w / 2, h / 2),
        angle,
        1
    )

    rotated = cv2.warpAffine(
        image,
        matrix,
        (w, h),
        borderValue=(255, 255, 255)
    )

    return rotated


# ==========================================================
# GAUSSIAN NOISE
# ==========================================================

def apply_noise(image):

    noise = np.random.normal(
        0,
        15,
        image.shape
    ).astype(np.int16)

    noisy = image.astype(np.int16) + noise

    noisy = np.clip(
        noisy,
        0,
        255
    ).astype(np.uint8)

    return noisy


# ==========================================================
# DARK DOCUMENT
# ==========================================================

def apply_dark(image):

    alpha = random.uniform(0.55, 0.80)

    beta = random.randint(-60, -20)

    return cv2.convertScaleAbs(
        image,
        alpha=alpha,
        beta=beta
    )


# ==========================================================
# LOW CONTRAST
# ==========================================================

def apply_low_contrast(image):

    alpha = random.uniform(0.40, 0.70)

    beta = random.randint(20, 40)

    return cv2.convertScaleAbs(
        image,
        alpha=alpha,
        beta=beta
    )


# ==========================================================
# JPEG COMPRESSION
# ==========================================================

def apply_jpeg_compression(image):

    quality = random.randint(10, 35)

    _, encoded = cv2.imencode(
        ".jpg",
        image,
        [
            int(cv2.IMWRITE_JPEG_QUALITY),
            quality
        ]
    )

    decoded = cv2.imdecode(
        encoded,
        1
    )

    return decoded


# ==========================================================
# SHADOW
# ==========================================================

def apply_shadow(image):

    shadow = image.copy()

    h, w = shadow.shape[:2]

    x = random.randint(0, int(w * 0.5))

    cv2.rectangle(
        shadow,
        (x, 0),
        (w, h),
        (40, 40, 40),
        -1
    )

    alpha = 0.35

    return cv2.addWeighted(
        shadow,
        alpha,
        image,
        1 - alpha,
        0
    )


# ==========================================================
# SALT & PEPPER
# ==========================================================

def apply_salt_pepper(image, amount=0.004):

    output = image.copy()

    h, w = output.shape[:2]

    num = int(amount * h * w)

    # Blanc

    for _ in range(num):

        y = random.randint(0, h - 1)

        x = random.randint(0, w - 1)

        output[y, x] = (255, 255, 255)

    # Noir

    for _ in range(num):

        y = random.randint(0, h - 1)

        x = random.randint(0, w - 1)

        output[y, x] = (0, 0, 0)

    return output


# ==========================================================
# RANDOM AUGMENTATION
# ==========================================================

AUGMENTATIONS = {

    "blur": apply_blur,

    "rotation": apply_rotation,

    "noise": apply_noise,

    "dark": apply_dark,

    "low_contrast": apply_low_contrast,

    "jpeg": apply_jpeg_compression,

    "shadow": apply_shadow,

    "salt_pepper": apply_salt_pepper

}
