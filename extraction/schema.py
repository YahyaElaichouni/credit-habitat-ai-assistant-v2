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

from pydantic import BaseModel, Field, field_validator
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

    nom: ExtractedField[str] = Field(default_factory=ExtractedField)
    prenom: ExtractedField[str] = Field(default_factory=ExtractedField)

    employeur: ExtractedField[str] = Field(default_factory=ExtractedField)
    poste: ExtractedField[str] = Field(default_factory=ExtractedField)

    date_embauche: ExtractedField[str] = Field(default_factory=ExtractedField)
    periode: ExtractedField[str] = Field(default_factory=ExtractedField)

    salaire_base: ExtractedField[float] = Field(default_factory=ExtractedField)
    salaire_brut: ExtractedField[float] = Field(default_factory=ExtractedField)
    salaire_net: ExtractedField[float] = Field(default_factory=ExtractedField)

    devise: ExtractedField[str] = Field(default_factory=ExtractedField)


# =========================================================
# RELEVE BANCAIRE
# =========================================================




class ReleveBancaireSchema(BaseModel):

    document_type: str = "releve"

    nom: ExtractedField[str] = Field(default_factory=ExtractedField)
    prenom: ExtractedField[str] = Field(default_factory=ExtractedField)

    banque: ExtractedField[str] = Field(default_factory=ExtractedField)
    numero_compte: ExtractedField[str] = Field(default_factory=ExtractedField)
    iban: ExtractedField[str] = Field(default_factory=ExtractedField)

    periode_debut: ExtractedField[str] = Field(default_factory=ExtractedField)
    periode_fin: ExtractedField[str] = Field(default_factory=ExtractedField)

    solde_initial: ExtractedField[float] = Field(default_factory=ExtractedField)
    solde_final: ExtractedField[float] = Field(default_factory=ExtractedField)

    devise: ExtractedField[str] = Field(default_factory=ExtractedField)

    transactions: List[Transaction] = Field(default_factory=list)

    charge_mensuelle_credits: ExtractedField[float] = Field(default_factory=ExtractedField)
    revenus_complementaires: ExtractedField[float] = Field(default_factory=ExtractedField)


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

    prix_vente: ExtractedField[float] = Field(default_factory=ExtractedField)
    devise: ExtractedField[str] = Field(default_factory=ExtractedField)

    date_signature: ExtractedField[str] = Field(default_factory=ExtractedField)

    superficie: ExtractedField[float] = Field(default_factory=ExtractedField)
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
