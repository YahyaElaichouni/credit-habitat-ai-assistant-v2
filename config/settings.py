"""
===========================================================
Chargement de la configuration
Projet PFE Crédit Agricole du Maroc
===========================================================

Point d'entrée unique pour accéder aux seuils/paramètres du
projet. N'importez jamais une valeur seuil en dur ailleurs :
passez toujours par `settings` défini ici.

Usage :
    from config.settings import settings

    if confidence < settings.confidence_threshold:
        ...
"""

from dataclasses import dataclass
from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).parent / "settings.yaml"


@dataclass(frozen=True)
class Settings:

    confidence_threshold: float
    discrepancy_threshold: float

    max_file_size_mb: int
    allowed_extensions: tuple

    llm_model: str

    ocr_dpi: int

    rag_embedding_model: str
    rag_chunk_size: int
    rag_chunk_overlap: int
    rag_top_k: int
    rag_similarity_threshold: float

    documents_dir: Path
    samples_dir: Path
    database_path: Path
    vectorstore_dir: Path

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024


def load_settings(config_path: Path = CONFIG_PATH) -> Settings:
    """Charge et valide settings.yaml.

    Échoue volontairement fort (exception explicite) plutôt que de
    retomber silencieusement sur des valeurs par défaut : dans un
    contexte bancaire, un seuil de confiance ou d'écart mal
    configuré doit être visible immédiatement, pas caché derrière
    un défaut discret.
    """

    if not config_path.exists():
        raise FileNotFoundError(
            f"Fichier de configuration introuvable : {config_path}. "
            "Le projet ne doit jamais tourner avec des seuils par "
            "défaut implicites."
        )

    with open(config_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    try:
        return Settings(
            confidence_threshold=float(
                raw["extraction"]["confidence_threshold"]
            ),
            discrepancy_threshold=float(
                raw["extraction"]["discrepancy_threshold"]
            ),
            max_file_size_mb=int(
                raw["document"]["max_file_size_mb"]
            ),
            allowed_extensions=tuple(
                raw["document"]["allowed_extensions"]
            ),
            llm_model=raw["llm"]["model"],
            ocr_dpi=int(raw["ocr"]["dpi"]),
            rag_embedding_model=raw["rag"]["embedding_model"],
            rag_chunk_size=int(raw["rag"]["chunk_size"]),
            rag_chunk_overlap=int(raw["rag"]["chunk_overlap"]),
            rag_top_k=int(raw["rag"]["top_k"]),
            rag_similarity_threshold=float(raw["rag"]["similarity_threshold"]),
            documents_dir=Path(raw["paths"]["documents_dir"]),
            samples_dir=Path(raw["paths"]["samples_dir"]),
            database_path=Path(raw["paths"]["database_path"]),
            vectorstore_dir=Path(raw["paths"]["vectorstore_dir"]),
        )
    except KeyError as e:
        raise KeyError(
            f"Clé manquante dans {config_path} : {e}. "
            "Comparez avec la structure attendue dans settings.py."
        ) from e


# Chargé une seule fois à l'import, réutilisé partout dans le projet.
settings = load_settings()
