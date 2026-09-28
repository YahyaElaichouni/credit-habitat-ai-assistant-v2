"""
===========================================================
Document Extractor
Projet PFE Crédit Agricole du Maroc
===========================================================
"""

import json
import logging
from copy import deepcopy
from functools import lru_cache
from typing import Any, Dict, Type

import ollama
from pydantic import BaseModel, ValidationError

from extraction.prompts import (
    SYSTEM_PROMPT,
    DOCUMENT_PROMPTS,
    RELEVE_TRANSACTIONS_FALLBACK_PROMPT,
)
from extraction.schema import (
    DOCUMENT_SCHEMAS,
    LLM_DOCUMENT_SCHEMAS,
    ReleveTransactionsFallbackSchema,
    extract_confidences,
    flatten,
)
from extraction.sanitizer import wrap_as_data
from extraction.identity_mrz import fill_missing_identity_fields
from extraction.payroll_fallback import fill_missing_payroll_fields
from extraction.statement_fallback import fill_missing_statement_fields


logger = logging.getLogger(__name__)


# Un appel Ollama n'est évité que lorsque toutes les données normalement
# demandées au modèle sont déjà retrouvées avec une citation exploitable.
# Cette règle volontairement conservatrice accélère les documents lisibles
# sans réduire les informations produites pour les documents difficiles.
_DETERMINISTIC_REQUIRED_FIELDS = {
    "bulletin": (
        "nom", "prenom", "employeur", "poste",
        "date_embauche", "periode", "salaire_net",
    ),
    "releve": ("banque", "periode_debut", "periode_fin"),
}


def _proven_field(field: Any, minimum_confidence: float = 0.70) -> bool:
    """Vrai si une valeur déterministe possède une preuve OCR suffisante."""

    if not isinstance(field, dict) or field.get("value") in (None, "", []):
        return False
    try:
        confidence = float(field.get("confidence"))
    except (TypeError, ValueError):
        return False
    source = field.get("source")
    return (
        confidence >= minimum_confidence
        and isinstance(source, dict)
        and type(source.get("page")) is int
        and bool(str(source.get("quote") or "").strip())
    )


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

    def get_llm_schema(
        self,
        document_type: str,
    ) -> Type[BaseModel]:
        """Retourner le schéma compact envoyé à Ollama.

        Le schéma final reste celui de ``DOCUMENT_SCHEMAS``. Cette séparation
        évite notamment de demander au modèle de recopier toutes les lignes
        d'un relevé alors qu'elles sont déjà analysées depuis l'OCR.
        """

        if document_type not in LLM_DOCUMENT_SCHEMAS:
            raise ValueError(f"Type de document inconnu : {document_type}")
        return LLM_DOCUMENT_SCHEMAS[document_type]

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
                keep_alive="30m",

                # Configuration stable pour l'extraction documentaire.
                options={
                    "temperature": 0,
                    "top_p": 0.1,
                },
            )
            logger.info(
            "Ollama — chargement %.2f s | prompt %.2f s | "
            "génération %.2f s | %s tokens",
            response.get("load_duration", 0) / 1_000_000_000,
            response.get("prompt_eval_duration", 0) / 1_000_000_000,
            response.get("eval_duration", 0) / 1_000_000_000,
            response.get("eval_count", 0),
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

    @staticmethod
    def _deterministic_extract(
        ocr_text: str,
        document_type: str,
    ) -> Dict[str, Any]:
        """Extraire d'abord les champs prouvables sans modèle génératif."""

        seed = {"document_type": document_type}
        if document_type == "carte_identite":
            return fill_missing_identity_fields(seed, ocr_text)
        if document_type == "bulletin":
            return fill_missing_payroll_fields(seed, ocr_text)
        if document_type == "releve":
            return fill_missing_statement_fields(seed, ocr_text)
        return seed

    @staticmethod
    def _deterministic_result_is_complete(
        data: Dict[str, Any],
        document_type: str,
    ) -> bool:
        required = _DETERMINISTIC_REQUIRED_FIELDS.get(document_type)
        return bool(required) and all(_proven_field(data.get(name)) for name in required)

    @staticmethod
    def _complete_with_deterministic_rules(
        data: Dict[str, Any],
        ocr_text: str,
        document_type: str,
    ) -> Dict[str, Any]:
        if document_type == "carte_identite":
            return fill_missing_identity_fields(data, ocr_text)
        if document_type == "bulletin":
            return fill_missing_payroll_fields(data, ocr_text)
        if document_type == "releve":
            return fill_missing_statement_fields(data, ocr_text)
        return data

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

        # Les règles rapides passent avant Ollama. Le modèle n'est sauté que
        # si elles ont retrouvé l'intégralité du schéma utile avec une preuve
        # OCR. Dans tous les autres cas, l'ancien chemin LLM reste inchangé.
        deterministic = self._deterministic_extract(ocr_text, document_type)
        if self._deterministic_result_is_complete(deterministic, document_type):
            logger.info(
                "[DocumentExtractor] Extraction déterministe complète : "
                "appel Ollama évité pour %s",
                document_type,
            )
            data = deterministic
        else:
            llm_schema = self.get_llm_schema(document_type)
            prompt = self.build_prompt(
                document_type=document_type,
                ocr_text=ocr_text,
            )
            response = self.call_llm(
                prompt=prompt,
                schema=llm_schema,
            )
            data = self.parse_json(response)
            data = self._complete_with_deterministic_rules(
                data,
                ocr_text,
                document_type,
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

    @lru_cache(maxsize=32)
    def _extract_json_cached(
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

    def extract_json(
        self,
        ocr_text: str,
        document_type: str,
    ) -> Dict[str, Any]:
        """Résultat isolé, mis en cache pour un même contenu OCR.

        La copie profonde est indispensable : ``ExtractionAgent`` enrichit
        ensuite les relevés avec les métriques financières et la provenance.
        Sans copie, ces modifications contamineraient une future lecture du
        cache.
        """

        before = self._extract_json_cached.cache_info().hits
        result = self._extract_json_cached(ocr_text, document_type)
        if self._extract_json_cached.cache_info().hits > before:
            logger.info(
                "[DocumentExtractor] Résultat d'extraction réutilisé depuis le cache"
            )
        return deepcopy(result)

    def extract_statement_transactions_fallback(
        self,
        ocr_text: str,
    ) -> list[Dict[str, Any]]:
        """Relire seulement les opérations utiles d'un relevé difficile.

        Cette passe n'est pas utilisée lors du parcours normal. Elle est
        déclenchée par ``ExtractionAgent`` uniquement lorsque les extracteurs
        OCR déterministes n'ont trouvé aucune preuve exploitable.
        """

        prompt = RELEVE_TRANSACTIONS_FALLBACK_PROMPT.format(
            ocr_text=wrap_as_data(ocr_text)
        )
        response = self.call_llm(
            prompt=prompt,
            schema=ReleveTransactionsFallbackSchema,
        )
        data = self.parse_json(response)
        validated = ReleveTransactionsFallbackSchema.model_validate(data)
        return [item.model_dump() for item in validated.transactions]
