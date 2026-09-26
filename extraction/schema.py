"""
===========================================================
Schemas d'extraction
Projet PFE Crédit Agricole du Maroc
===========================================================

Chaque champ extrait par le LLM porte un indice de confiance
(EB-125) : on ne stocke jamais juste une valeur, mais une paire
{valeur, confiance}. En dessous du seuil (config/settings.yaml,
0,85 par défaut), agents/validation_agent.py doit signaler le
champ pour vérification humaine plutôt que le proposer comme
fiable.

Les sous-objets (ex : lignes de transaction d'un relevé) restent
volontairement en champs simples : leur confiance n'est pas
demandée individuellement pour l'instant, pour ne pas complexifier
inutilement le format attendu du LLM. Peut être étendu plus tard
si besoin.
"""

from typing import Any, Dict, Generic, List, Optional, TypeVar
import re

from pydantic import BaseModel, Field, field_validator, model_validator
import math

T = TypeVar("T")


# =========================================================
# CHAMP AVEC INDICE DE CONFIANCE (EB-125)
# =========================================================

class FieldEvidence(BaseModel):
    """Citation proposée par le modèle, à vérifier contre les pages OCR."""

    page: Optional[int] = Field(default=None, ge=1, strict=True)
    quote: Optional[str] = None


class ExtractedField(BaseModel, Generic[T]):
    """Enveloppe générique : une valeur extraite + la confiance
    du modèle sur cette valeur (entre 0 et 1)."""

    value: Optional[T] = None
    confidence: Optional[float] = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    source: Optional[FieldEvidence] = None

    @field_validator("value")
    @classmethod
    def finite_value(cls, value):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("Valeur numérique non finie")
        return value


class MonetaryField(ExtractedField[float]):
    """Montant numérique tolérant aux notations OCR marocaines."""

    @field_validator("value", mode="before")
    @classmethod
    def parse_moroccan_amount(cls, value):
        if value is None or isinstance(value, (int, float)):
            return value
        if not isinstance(value, str):
            return value
        text = value.strip().replace("\u00a0", " ").replace("\u202f", " ")
        text = re.sub(r"(?i)\b(?:MAD|DHS?|DIRHAMS?)\b", "", text)
        text = text.replace("د.م.", "").replace("د.م", "")
        text = re.sub(r"[^0-9,\.\-+ ]", "", text).replace(" ", "")
        if not text or text in {"-", "+", ".", ","}:
            return value
        comma, dot = text.rfind(","), text.rfind(".")
        if comma >= 0 and dot >= 0:
            decimal = "," if comma > dot else "."
            thousands = "." if decimal == "," else ","
            text = text.replace(thousands, "").replace(decimal, ".")
        elif comma >= 0:
            decimals = len(text) - comma - 1
            text = text.replace(",", "." if decimals in {1, 2} else "")
        elif dot >= 0:
            decimals = len(text) - dot - 1
            if decimals not in {1, 2}:
                text = text.replace(".", "")
        try:
            return float(text)
        except ValueError:
            return value


# =========================================================
# TRANSACTION BANCAIRE
# =========================================================

class Transaction(BaseModel):
    date: Optional[str] = None
    description: Optional[str] = None
    montant: Optional[float] = None
    type: Optional[str] = None
    page: Optional[int] = Field(default=None, ge=1, strict=True)
    quote: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def accept_simple_or_wrapped_fields(cls, data):
        """Tolérer les sous-champs enveloppés malgré la consigne du prompt."""
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        evidence_page = normalized.get("page")
        evidence_quote = normalized.get("quote")
        for name in ("date", "description", "montant", "type"):
            wrapped = normalized.get(name)
            if not isinstance(wrapped, dict) or "value" not in wrapped:
                continue
            source = wrapped.get("source")
            if isinstance(source, dict):
                if evidence_page is None and type(source.get("page")) is int:
                    evidence_page = source["page"]
                if evidence_quote is None and isinstance(source.get("quote"), str):
                    evidence_quote = source["quote"]
            normalized[name] = wrapped.get("value")
        if isinstance(evidence_page, dict):
            evidence_page = evidence_page.get("value")
        if isinstance(evidence_quote, dict):
            evidence_quote = evidence_quote.get("value")
        normalized["page"] = evidence_page
        normalized["quote"] = evidence_quote
        return normalized


# =========================================================
# CARTE D'IDENTITE
# =========================================================

class CarteIdentiteSchema(BaseModel):

    document_type: str = "carte_identite"

    cin: ExtractedField[str] = Field(default_factory=ExtractedField)
    nom: ExtractedField[str] = Field(default_factory=ExtractedField)
    prenom: ExtractedField[str] = Field(default_factory=ExtractedField)
    date_naissance: ExtractedField[str] = Field(default_factory=ExtractedField)
    lieu_naissance: ExtractedField[str] = Field(default_factory=ExtractedField)
    sexe: ExtractedField[str] = Field(default_factory=ExtractedField)
    adresse: ExtractedField[str] = Field(default_factory=ExtractedField)
    date_expiration: ExtractedField[str] = Field(default_factory=ExtractedField)
    identite_ambigue: ExtractedField[bool] = Field(default_factory=ExtractedField)
    noms_non_attribues: ExtractedField[List[str]] = Field(default_factory=ExtractedField)


# =========================================================
# BULLETIN DE SALAIRE
# =========================================================

class BulletinSchema(BaseModel):

    document_type: str = "bulletin"

    # Champs strictement nécessaires au parcours de crédit habitat.
    # Garder un schéma court réduit le temps d'inférence et les confusions
    # entre les nombreuses colonnes chiffrées d'un bulletin de paie.
    nom: ExtractedField[str] = Field(default_factory=ExtractedField)
    prenom: ExtractedField[str] = Field(default_factory=ExtractedField)
    employeur: ExtractedField[str] = Field(default_factory=ExtractedField)
    poste: ExtractedField[str] = Field(default_factory=ExtractedField)
    date_embauche: ExtractedField[str] = Field(default_factory=ExtractedField)
    periode: ExtractedField[str] = Field(default_factory=ExtractedField)
    salaire_net: MonetaryField = Field(default_factory=MonetaryField)


# =========================================================
# RELEVE BANCAIRE
# =========================================================




class ReleveBancaireSchema(BaseModel):

    document_type: str = "releve"

    # Métadonnées minimales permettant d'identifier et dater le relevé.
    banque: ExtractedField[str] = Field(default_factory=ExtractedField)
    periode_debut: ExtractedField[str] = Field(default_factory=ExtractedField)
    periode_fin: ExtractedField[str] = Field(default_factory=ExtractedField)

    # Les transactions sont conservées uniquement comme données techniques
    # nécessaires aux deux calculs métier ci-dessous.
    transactions: List[Transaction] = Field(default_factory=list)
    charge_mensuelle_credits: MonetaryField = Field(default_factory=MonetaryField)
    revenus_complementaires: MonetaryField = Field(default_factory=MonetaryField)


class ReleveLLMSchema(BaseModel):
    """Sortie minimale demandée au LLM pour un relevé bancaire.

    Les transactions et les métriques financières sont extraites ensuite par
    les traitements déterministes à partir des pages OCR. Les retirer du
    schéma Ollama évite de générer plusieurs milliers de tokens sans modifier
    le schéma final exposé au reste de l'application.
    """

    document_type: str = "releve"
    banque: ExtractedField[str] = Field(default_factory=ExtractedField)
    periode_debut: ExtractedField[str] = Field(default_factory=ExtractedField)
    periode_fin: ExtractedField[str] = Field(default_factory=ExtractedField)


class ReleveTransactionsFallbackSchema(BaseModel):
    """Opérations utiles demandées uniquement lorsque l'OCR direct échoue."""

    transactions: List[Transaction] = Field(default_factory=list)


# =========================================================
# COMPROMIS DE VENTE
# =========================================================

class CompromisSchema(BaseModel):

    document_type: str = "compromis"

    vendeur_nom: ExtractedField[str] = Field(default_factory=ExtractedField)
    vendeur_prenom: ExtractedField[str] = Field(default_factory=ExtractedField)

    acheteur_nom: ExtractedField[str] = Field(default_factory=ExtractedField)
    acheteur_prenom: ExtractedField[str] = Field(default_factory=ExtractedField)

    adresse_bien: ExtractedField[str] = Field(default_factory=ExtractedField)
    type_bien: ExtractedField[str] = Field(default_factory=ExtractedField)

    prix_vente: MonetaryField = Field(default_factory=MonetaryField)
    devise: ExtractedField[str] = Field(default_factory=ExtractedField)

    date_signature: ExtractedField[str] = Field(default_factory=ExtractedField)

    superficie: MonetaryField = Field(default_factory=MonetaryField)
    reference_cadastrale: ExtractedField[str] = Field(default_factory=ExtractedField)


# =========================================================
# MAPPING DES SCHEMAS
# =========================================================

DOCUMENT_SCHEMAS = {

    "carte_identite": CarteIdentiteSchema,

    "bulletin": BulletinSchema,

    "releve": ReleveBancaireSchema,

    "compromis": CompromisSchema
}


# Schémas réellement transmis au LLM. Par défaut, le schéma d'extraction et
# le schéma final sont identiques. Seul le relevé utilise une sortie allégée :
# les opérations bancaires restent traitées côté serveur depuis l'OCR.
LLM_DOCUMENT_SCHEMAS = {
    **DOCUMENT_SCHEMAS,
    "releve": ReleveLLMSchema,
}


# =========================================================
# UTILITAIRES : dé-imbrication pour rule_engine
# =========================================================
# rule_engine/checks.py attend des valeurs brutes (data.get("nom")
# -> "Alaoui"), pas des objets {value, confidence}. Plutôt que de
# faire connaître ce format à checks.py, on l'aplatit une fois ici.

def flatten(model: BaseModel) -> Dict[str, Any]:
    """{champ: valeur} à partir d'un modèle avec ExtractedField."""

    result: Dict[str, Any] = {}

    for name, value in model:

        if isinstance(value, ExtractedField):
            result[name] = value.value

        elif isinstance(value, list):
            result[name] = [
                item.model_dump() if isinstance(item, BaseModel) else item
                for item in value
            ]

        else:
            result[name] = value

    return result


def extract_confidences(model: BaseModel) -> Dict[str, Optional[float]]:
    """{champ: confiance} pour tous les champs qui en portent une."""

    result: Dict[str, Optional[float]] = {}

    for name, value in model:
        if isinstance(value, ExtractedField):
            result[name] = value.confidence

    return result
