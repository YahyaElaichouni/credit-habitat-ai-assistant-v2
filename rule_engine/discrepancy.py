"""
===========================================================
Écart déclaratif / extrait
Projet PFE Crédit Agricole du Maroc
===========================================================

Compare une valeur déclarée par l'utilisateur (formulaire) à la
valeur trouvée par l'extraction IA dans un justificatif (EB-108).
Le seuil vient de config/settings.yaml, jamais en dur ici.
"""

from typing import Any, Dict, List, Optional

from config.settings import settings


def compute_discrepancy(
    declared_value: Any,
    extracted_value: Any,
) -> Optional[float]:
    """Écart relatif entre deux valeurs numériques.

    Retourne None quand la comparaison n'a pas de sens (valeur
    manquante, non numérique, ou déclaratif à zéro) — à distinguer
    d'un écart de 0.0, qui signifie "valeurs identiques".
    """

    if declared_value is None or extracted_value is None:
        return None

    try:
        declared = float(declared_value)
        extracted = float(extracted_value)
    except (TypeError, ValueError):
        return None

    if declared == 0:
        return None

    return abs(extracted - declared) / abs(declared)


def check_discrepancy(
    field_name: str,
    declared_value: Any,
    extracted_value: Any,
    threshold: Optional[float] = None,
) -> Dict[str, Any]:
    """Même format de résultat que rule_engine.checks, pour rester
    agrégeable par rule_engine.engine.RuleEngine si besoin
    (passed=True/False/None)."""

    if threshold is None:
        threshold = settings.discrepancy_threshold

    ecart = compute_discrepancy(declared_value, extracted_value)

    # Le zéro est une déclaration réelle, pas une donnée manquante.
    try:
        if float(declared_value) == 0 and extracted_value is not None:
            equal = float(extracted_value) == 0
            return {"rule": f"ecart_{field_name}", "passed": equal,
                    "message": "Valeurs nulles identiques" if equal else
                    f"{field_name} : déclaré à zéro mais montant extrait non nul, à vérifier"}
    except (TypeError, ValueError):
        pass

    if ecart is None:
        return {
            "rule": f"ecart_{field_name}",
            "passed": None,
            "message": (
                f"Écart non évaluable pour {field_name} "
                "(valeur manquante ou non numérique)"
            ),
        }

    passed = ecart <= threshold

    return {
        "rule": f"ecart_{field_name}",
        "passed": passed,
        "message": (
            f"Écart {field_name} : {ecart:.1%} "
            f"({'conforme' if passed else 'à vérifier'}, "
            f"seuil {threshold:.0%})"
        ),
    }


def check_discrepancies(
    declared_data: Dict[str, Any],
    extracted_data: Dict[str, Any],
    fields: List[str],
    threshold: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Applique check_discrepancy sur une liste de champs communs
    au déclaratif et à l'extrait."""

    return [
        check_discrepancy(
            field,
            declared_data.get(field),
            extracted_data.get(field),
            threshold,
        )
        for field in fields
    ]
