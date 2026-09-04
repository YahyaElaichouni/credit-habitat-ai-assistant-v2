"""
Lancez ce script une seule fois pour vérifier le format exact
retourné par VOTRE version installée de PaddleOCR, avant d'adopter
le correctif d'ocr_engine.py.

Usage : python check_paddleocr_version.py chemin/vers/une_image.png
"""

import sys
import paddleocr

print("Version PaddleOCR installée :", paddleocr.__version__)

if len(sys.argv) < 2:
    print("Donnez un chemin d'image en argument pour tester le format "
          "de sortie réel.")
    sys.exit(0)

ocr = paddleocr.PaddleOCR(
    lang="fr",
    use_textline_orientation=True,
)

result = ocr.predict(sys.argv[1])

print("\nType du résultat :", type(result))
print("Longueur :", len(result))

first = result[0]
print("\nType du premier élément :", type(first))

if hasattr(first, "keys"):
    print("Clés disponibles :", list(first.keys()))
    if "rec_texts" in first:
        print("\nExemple rec_texts[:3] :", first["rec_texts"][:3])
    if "rec_scores" in first:
        print("Exemple rec_scores[:3] :", first["rec_scores"][:3])
else:
    print("Format inattendu, contenu brut :", first)
