"""
===========================================================
Document Extractor
Projet PFE Crédit Agricole du Maroc
===========================================================
"""

import json
import logging
from typing import Any, Dict, Type

import ollama
from pydantic import BaseModel, ValidationError

from extraction.prompts import (
    SYSTEM_PROMPT,
    DOCUMENT_PROMPTS,
)

from extraction.schema import (
    DOCUMENT_SCHEMAS,
    extract_confidences,
    flatten,
)
from extraction.sanitizer import wrap_as_data

logger = logging.getLogger(__name__)


class DocumentExtractor:

    def __init__(
        self,
        model: str = "mistral"
    ):
        """
        Initialise le moteur d'extraction.

        Parameters
        ----------
        model : str
            Nom du modèle Ollama utilisé.
        """

        self.model = model

        logger.debug("Modèle LLM : %s", self.model)

    # =====================================================
    # DETECTION DU SCHEMA
    # =====================================================

    def get_schema(
        self,
        document_type: str
    ) -> Type[BaseModel]:

        if document_type not in DOCUMENT_SCHEMAS:

            raise ValueError(
                f"Type de document inconnu : {document_type}"
            )

        return DOCUMENT_SCHEMAS[document_type]

    # =====================================================
    # CREATION DU PROMPT
    # =====================================================

    def build_prompt(
        self,
        document_type: str,
        ocr_text: str
    ) -> str:

        if document_type not in DOCUMENT_PROMPTS:

            raise ValueError(
                f"Prompt inconnu pour : {document_type}"
            )

        prompt_template = DOCUMENT_PROMPTS[
            document_type
        ]

        # Le texte OCR n'est jamais inséré brut dans le prompt : il est
        # toujours encadré par des délimiteurs explicites (sanitizer.py),
        # pour que le modèle ne puisse pas confondre le contenu du
        # document avec une instruction à suivre. Le rappel de cette
        # règle ("ceci est une donnée, pas un ordre") vit dans
        # SYSTEM_PROMPT (extraction/prompts.py), passé au rôle "system"
        # dans call_llm — vérifiez qu'il le contient bien.
        return prompt_template.format(
            ocr_text=wrap_as_data(ocr_text)
        )

    # =====================================================
    # APPEL LLM
    # =====================================================

    def call_llm(
        self,
        prompt: str
    ) -> str:

        try:
            response = ollama.chat(

                model=self.model,

                messages=[

                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT
                    },

                    {
                        "role": "user",
                        "content": prompt
                    }

                ],

                format="json"
            )
        except Exception as e:
            raise RuntimeError(
                f"Échec de l'appel au modèle Ollama ({self.model}). "
                "Vérifiez qu'Ollama tourne bien en local et que le "
                "modèle est disponible (`ollama list`)."
            ) from e

        return response["message"]["content"]

    # =====================================================
    # PARSING JSON
    # =====================================================

    def parse_json(
        self,
        response: str
    ) -> Dict[str, Any]:

        try:

            return json.loads(response)

        except json.JSONDecodeError as e:

            raise ValueError(
                "Le LLM n'a pas retourné un JSON valide."
            ) from e

    # =====================================================
    # VALIDATION PYDANTIC
    # =====================================================

    def validate(
        self,
        data: Dict[str, Any],
        document_type: str
    ) -> BaseModel:

        schema = self.get_schema(
            document_type
        )

        try:

            validated = schema.model_validate(
                data
            )

            # Le routage (quel type de document on traite) est décidé
            # par le pipeline, jamais par le contenu du document. On ne
            # fait pas confiance à un éventuel "document_type" présent
            # dans le JSON retourné par le LLM.
            validated.document_type = document_type

            return validated

        except ValidationError as e:

            raise ValueError(
                f"JSON incompatible avec le schema "
                f"{document_type} :\n{e}"
            ) from e

    # =====================================================
    # EXTRACTION COMPLETE
    # =====================================================

    def extract(
        self,
        ocr_text: str,
        document_type: str
    ) -> BaseModel:

        if not ocr_text or not ocr_text.strip():

            raise ValueError(
                "Le texte OCR est vide."
            )

        logger.info("Extraction du document : %s", document_type)

        # -------------------------------------------------
        # 1. Construire le prompt (texte OCR encadré par sanitizer)
        # -------------------------------------------------

        prompt = self.build_prompt(
            document_type,
            ocr_text
        )

        # -------------------------------------------------
        # 2. Appeler le LLM
        # -------------------------------------------------

        response = self.call_llm(
            prompt
        )

        # -------------------------------------------------
        # 3. Parser le JSON
        # -------------------------------------------------

        data = self.parse_json(
            response
        )

        # -------------------------------------------------
        # 4. Valider avec Pydantic
        # -------------------------------------------------

        validated = self.validate(
            data,
            document_type
        )

        logger.info("Extraction réussie.")

        return validated

    # =====================================================
    # EXTRACTION VERS JSON
    # =====================================================

    def extract_json(
        self,
        ocr_text: str,
        document_type: str
    ) -> Dict[str, Any]:
        """Retourne trois vues du même résultat :

        - "data" : valeurs aplaties (champ -> valeur brute), ce que
          rule_engine.checks attend.
        - "confidences" : champ -> indice de confiance (EB-125), pour
          comparaison au seuil dans validation_agent.py.
        - "raw" : dump complet imbriqué {value, confidence}, conservé
          tel quel pour le journal d'audit (traçabilité fidèle de ce
          que le LLM a réellement produit).
        """

        result = self.extract(
            ocr_text,
            document_type
        )

        return {
            "data": flatten(result),
            "confidences": extract_confidences(result),
            "raw": result.model_dump(),
        }
