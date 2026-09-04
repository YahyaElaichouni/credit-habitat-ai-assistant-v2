"""
===========================================================
Contrôle des fichiers déposés
Projet PFE Crédit Agricole du Maroc
===========================================================

EB-219 : taille maximale et type réel du fichier (pas seulement
son extension), à exécuter avant tout traitement OCR/extraction.
Correspond à l'étape "Contrôle du document" du pipeline (juste
après l'upload, avant l'OCR).

On ne fait jamais confiance à l'extension d'un fichier : un
fichier nommé "bulletin.pdf" qui ne commence pas par les octets
magiques d'un vrai PDF est rejeté, qu'il s'agisse d'une erreur de
l'utilisateur ou d'une tentative de déguiser un fichier.
"""

from pathlib import Path
from typing import NamedTuple, Optional

from config.settings import settings

# Signature binaire (octets de tête) de chaque format autorisé.
# Volontairement pas de dépendance externe (type python-magic, qui
# nécessite libmagic côté système et complique l'installation sous
# Windows) : ces formats ont des signatures simples et stables.
_MAGIC_SIGNATURES = {
    ".pdf": (b"%PDF-",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
}


class FileControlResult(NamedTuple):
    valid: bool
    reason: Optional[str]


# =========================================================
# TAILLE
# =========================================================

def check_file_size(path: Path) -> FileControlResult:

    size = path.stat().st_size

    if size == 0:
        return FileControlResult(False, "Fichier vide.")

    if size > settings.max_file_size_bytes:
        size_mb = size / (1024 * 1024)
        return FileControlResult(
            False,
            f"Fichier trop volumineux ({size_mb:.1f} Mo, "
            f"maximum {settings.max_file_size_mb} Mo)."
        )

    return FileControlResult(True, None)


# =========================================================
# TYPE REEL (octets magiques, pas l'extension)
# =========================================================

def check_file_type(path: Path) -> FileControlResult:

    extension = path.suffix.lower()

    if extension not in settings.allowed_extensions:
        return FileControlResult(
            False,
            f"Extension non autorisée : {extension} "
            f"(autorisées : {', '.join(settings.allowed_extensions)})."
        )

    signatures = _MAGIC_SIGNATURES.get(extension)

    if signatures is None:
        # Extension déclarée autorisée dans settings.yaml mais sans
        # signature connue ici : on refuse explicitement plutôt que
        # de laisser passer un type non vérifié en silence.
        return FileControlResult(
            False,
            f"Aucune signature binaire connue pour {extension}. "
            "Ajoutez-la dans _MAGIC_SIGNATURES avant d'autoriser ce type."
        )

    with open(path, "rb") as f:
        header = f.read(16)

    if not any(header.startswith(sig) for sig in signatures):
        return FileControlResult(
            False,
            f"Le contenu du fichier ne correspond pas à un "
            f"{extension} valide (extension usurpée ou fichier "
            "corrompu)."
        )

    return FileControlResult(True, None)


# =========================================================
# POINT D'ENTREE
# =========================================================

def control_document(path_str: str) -> FileControlResult:
    """Taille + type réel. À appeler avant tout traitement."""

    path = Path(path_str)

    if not path.exists():
        return FileControlResult(False, f"{path} introuvable.")

    size_check = check_file_size(path)
    if not size_check.valid:
        return size_check

    type_check = check_file_type(path)
    if not type_check.valid:
        return type_check

    return FileControlResult(True, None)
