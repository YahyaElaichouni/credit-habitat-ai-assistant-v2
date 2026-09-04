"""
===========================================================
Rule Engine
Projet PFE Crédit Agricole du Maroc
===========================================================

Agrège les résultats de checks.py (plausibilité/format) et,
quand disponible, de discrepancy.py (écart déclaratif/extrait)
pour produire un résultat de synthèse par document.

Distingue explicitement trois états par règle :
  - passed = True   -> règle vérifiée, conforme
  - passed = False  -> règle vérifiée, non conforme (vrai problème)
  - passed = None   -> non évaluable (donnée manquante), à ne pas
                        compter comme un échec
"""

import logging

from rule_engine.checks import RULES

logger = logging.getLogger(__name__)


class RuleEngine:

    def __init__(self):
        logger.debug("Initialisation du Rule Engine")

    # =====================================================
    # VALIDATION
    # =====================================================

    def validate(self, data, document_type):

        if document_type not in RULES:
            raise ValueError(
                f"Aucune règle pour : {document_type}"
            )

        validator = RULES[document_type]
        results = validator(data)

        return self._summarize(document_type, results)

    def validate_with_extra_rules(self, data, document_type, extra_results):
        """Comme validate(), mais permet d'ajouter des résultats calculés
        ailleurs (ex : discrepancy.py) dans le même résumé final, sans
        dupliquer la logique d'agrégation."""

        if document_type not in RULES:
            raise ValueError(
                f"Aucune règle pour : {document_type}"
            )

        validator = RULES[document_type]
        results = validator(data) + list(extra_results)

        return self._summarize(document_type, results)

    # =====================================================
    # AGRÉGATION
    # =====================================================

    def _summarize(self, document_type, results):

        total = len(results)

        passed = sum(
            1 for result in results
            if result["passed"] is True
        )

        failed = sum(
            1 for result in results
            if result["passed"] is False
        )

        not_evaluated = sum(
            1 for result in results
            if result["passed"] is None
        )

        evaluated = total - not_evaluated

        score = (passed / evaluated) if evaluated > 0 else 0.0

        return {

            "document_type":
                document_type,

            # un document non conforme uniquement à cause de données
            # manquantes (not_evaluated) n'est pas invalide pour autant :
            # seul un échec avéré (failed) le rend invalide.
            "valid":
                failed == 0,

            "score":
                round(score, 2),

            "total_rules":
                total,

            "passed_rules":
                passed,

            "failed_rules":
                failed,

            "not_evaluated_rules":
                not_evaluated,

            "rules":
                results
        }
