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
from extraction.identity_mrz import fill_missing_identity_fields
from extraction.payroll_fallback import fill_missing_payroll_fields
from extraction.statement_fallback import fill_missing_statement_fields


logger = logging.getLogger(__name__)


class DocumentExtractor:

    def __init__(
        self,
        model: str = "mistral",
    ):
        """
        Initialise le moteur d'extraction.

        Parameters
        ----------
        model : str
            Nom du modèle Ollama utilisé.
        """

        self.model = model

        logger.debug(
            "Modèle LLM d'extraction : %s",
            self.model,
        )

    # =====================================================
    # DÉTECTION DU SCHÉMA
    # =====================================================

    def get_schema(
        self,
        document_type: str,
    ) -> Type[BaseModel]:
        """
        Retourner le schéma Pydantic associé au document.
        """

        if document_type not in DOCUMENT_SCHEMAS:
            raise ValueError(
                f"Type de document inconnu : {document_type}. "
                f"Types acceptés : {list(DOCUMENT_SCHEMAS.keys())}"
            )

        return DOCUMENT_SCHEMAS[document_type]

    # =====================================================
    # CRÉATION DU PROMPT
    # =====================================================

    def build_prompt(
        self,
        document_type: str,
        ocr_text: str,
    ) -> str:
        """
        Construire le prompt d'extraction.

        Le texte OCR est encadré afin qu'il soit considéré
        comme une donnée et jamais comme une instruction.
        """

        if document_type not in DOCUMENT_PROMPTS:
            raise ValueError(
                f"Prompt inconnu pour : {document_type}"
            )

        prompt_template = DOCUMENT_PROMPTS[
            document_type
        ]

        return prompt_template.format(
            ocr_text=wrap_as_data(ocr_text)
        )

    # =====================================================
    # APPEL DU LLM
    # =====================================================

    def call_llm(
        self,
        prompt: str,
        schema: Type[BaseModel],
    ) -> str:
        """
        Appeler Ollama avec une sortie JSON structurée.

        Le schéma Pydantic est directement transmis à Ollama.
        La température à zéro réduit les différences entre
        plusieurs analyses du même texte OCR.
        """

        json_schema = schema.model_json_schema()

        structured_prompt = (
            f"{prompt}\n\n"
            "CONTRAINTE DE SORTIE OBLIGATOIRE\n"
            "Retourne uniquement un objet JSON valide respectant "
            "exactement le schéma ci-dessous.\n"
            "N'ajoute aucun texte avant ou après le JSON.\n"
            "Quand une information n'est pas clairement présente "
            "dans le document, utilise null au lieu de l'inventer.\n\n"
            f"{json.dumps(json_schema, ensure_ascii=False)}"
        )

        try:
            response = ollama.chat(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT,
                    },
                    {
                        "role": "user",
                        "content": structured_prompt,
                    },
                ],

                # Le modèle doit respecter le schéma Pydantic.
                format=json_schema,

                # Configuration stable pour l'extraction documentaire.
                options={
                    "temperature": 0,
                    "top_p": 0.1,
                },
            )

        except Exception as error:
            logger.exception(
                "[DocumentExtractor] Échec de l'appel Ollama "
                "avec le modèle %s",
                self.model,
            )

            raise RuntimeError(
                f"Échec de l'appel au modèle Ollama ({self.model}). "
                "Vérifiez qu'Ollama tourne bien en local et que le "
                "modèle est disponible avec `ollama list`."
            ) from error

        content = response.get("message", {}).get("content")

        if not content or not content.strip():
            raise ValueError(
                "Le modèle Ollama a retourné une réponse vide."
            )

        return content

    # =====================================================
    # PARSING JSON
    # =====================================================

    def parse_json(
        self,
        response: str,
    ) -> Dict[str, Any]:
        """
        Convertir la réponse du LLM en dictionnaire Python.
        """

        try:
            parsed_data = json.loads(response)

        except json.JSONDecodeError as error:
            logger.error(
                "[DocumentExtractor] JSON invalide reçu : %s",
                response[:1000],
            )

            raise ValueError(
                "Le LLM n'a pas retourné un JSON valide."
            ) from error

        if not isinstance(parsed_data, dict):
            raise ValueError(
                "Le LLM doit retourner un objet JSON, "
                "et non une liste ou une valeur simple."
            )

        return parsed_data

    # =====================================================
    # VALIDATION PYDANTIC
    # =====================================================

    def validate(
        self,
        data: Dict[str, Any],
        document_type: str,
    ) -> BaseModel:
        """
        Valider les données extraites avec le schéma Pydantic.
        """

        schema = self.get_schema(
            document_type
        )

        try:
            validated = schema.model_validate(
                data
            )

            # Le type de document vient du pipeline.
            # Il ne doit jamais être choisi par le LLM.
            validated.document_type = document_type

            return validated

        except ValidationError as error:
            logger.error(
                "[DocumentExtractor] Données incompatibles avec "
                "le schéma %s : %s",
                document_type,
                error,
            )

            raise ValueError(
                f"JSON incompatible avec le schéma "
                f"{document_type} :\n{error}"
            ) from error

    # =====================================================
    # EXTRACTION COMPLÈTE
    # =====================================================

    def extract(
        self,
        ocr_text: str,
        document_type: str,
    ) -> BaseModel:
        """
        Extraire et valider les informations d'un document.
        """

        if not ocr_text or not ocr_text.strip():
            raise ValueError(
                "Le texte OCR est vide."
            )

        logger.info(
            "[DocumentExtractor] Début de l'extraction : %s",
            document_type,
        )

        # -------------------------------------------------
        # 1. Récupérer le schéma correspondant au document
        # -------------------------------------------------

        schema = self.get_schema(
            document_type
        )

        # -------------------------------------------------
        # 2. Construire le prompt
        # -------------------------------------------------

        prompt = self.build_prompt(
            document_type=document_type,
            ocr_text=ocr_text,
        )

        # -------------------------------------------------
        # 3. Appeler Ollama avec le schéma strict
        # -------------------------------------------------

        response = self.call_llm(
            prompt=prompt,
            schema=schema,
        )

        # -------------------------------------------------
        # 4. Convertir la réponse JSON
        # -------------------------------------------------

        data = self.parse_json(
            response
        )

        # -------------------------------------------------
        # 5. Appliquer les extracteurs déterministes
        # -------------------------------------------------
        #
        # Le LLM reste l'extracteur principal.
        # Les fallbacks complètent ou corrigent les champs
        # qui peuvent être retrouvés de manière fiable dans
        # le texte OCR.
        # -------------------------------------------------

        if document_type == "carte_identite":
            data = fill_missing_identity_fields(
                data,
                ocr_text,
            )

        elif document_type == "bulletin":
            data = fill_missing_payroll_fields(
                data,
                ocr_text,
            )

        elif document_type == "releve":
            data = fill_missing_statement_fields(
                data,
                ocr_text,
            )

        # -------------------------------------------------
        # 6. Validation finale avec Pydantic
        # -------------------------------------------------

        validated = self.validate(
            data=data,
            document_type=document_type,
        )

        logger.info(
            "[DocumentExtractor] Extraction terminée : %s",
            document_type,
        )

        return validated

    # =====================================================
    # EXTRACTION VERS JSON
    # =====================================================

    def extract_json(
        self,
        ocr_text: str,
        document_type: str,
    ) -> Dict[str, Any]:
        """
        Retourner trois représentations du résultat :

        - data : valeurs simples utilisées par le moteur de règles ;
        - confidences : indice de confiance de chaque champ ;
        - raw : structure complète avec valeur, confiance et source.
        """

        result = self.extract(
            ocr_text=ocr_text,
            document_type=document_type,
        )

        return {
            "data": flatten(result),
            "confidences": extract_confidences(result),
            "raw": result.model_dump(),
        }