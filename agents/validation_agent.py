"""
===========================================================
Validation Agent
Projet PFE Crédit Agricole du Maroc
===========================================================

Point de convergence du pipeline d'extraction : combine le
moteur de règles (plausibilité), l'écart déclaratif/extrait
(EB-108), le seuil de confiance (EB-125) et le flag anti-injection
pour décider, champ par champ, si une valeur peut être proposée
en pré-remplissage ou doit être signalée pour revue humaine
prioritaire.

Important : ceci ne valide jamais rien automatiquement (EB-106).
"pre_rempli" signifie seulement "rien d'anormal détecté, peut être
proposé à la confirmation" — la confirmation humaine reste
obligatoire dans tous les cas, ce statut ne sert qu'à prioriser
la file de revue.
"""

import logging
from typing import Any, Dict, List, Optional

from config.settings import settings
from rule_engine.discrepancy import check_discrepancies
from rule_engine.engine import RuleEngine

logger = logging.getLogger(__name__)


class ValidationAgent:

    def __init__(self):
        self.engine = RuleEngine()

    # =====================================================
    # POINT D'ENTREE
    # =====================================================

    def run(
        self,
        document_type: str,
        data: Dict[str, Any],
        confidences: Dict[str, Optional[float]],
        security: Dict[str, Any],
        declared_data: Optional[Dict[str, Any]] = None,
        sources: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Parameters
        ----------
        document_type : "bulletin", "carte_identite", "releve", "compromis"
        data : valeurs extraites aplaties (ExtractionAgent.run()["data"])
        confidences : confiance par champ (ExtractionAgent.run()["confidences"])
        security : flag anti-injection (ExtractionAgent.run()["security"])
        declared_data : valeurs déclarées par l'utilisateur dans le
            formulaire, si disponibles. Un champ absent du déclaratif
            n'est simplement pas comparé (pas d'erreur).
        """

        declared_data = declared_data or {}

        # 1. Plausibilité / format (indépendant du déclaratif)
        rule_result = self.engine.validate(data, document_type)

        # 2. Écart déclaratif / extrait, uniquement sur les champs
        #    présents des deux côtés
        common_fields = [
            field for field in data
            if field != "document_type" and field in declared_data
        ]
        discrepancy_results = check_discrepancies(
            declared_data, data, common_fields
        )

        # 3. Décision par champ (confiance + écart)
        field_decisions = self._decide_fields(
            data, confidences, discrepancy_results
        )
        for name, decision in field_decisions.items():
            decision["source"] = (sources or {}).get(name)
            if decision["value"] is not None and not (decision["source"] or {}).get("verified"):
                decision["status"] = "signale"
                decision["reasons"].append("Provenance non vérifiée : contrôler le document original")
            if decision["value"] is not None and (not rule_result["valid"] or security.get("suspicious")):
                decision["status"] = "signale"
                decision["reasons"].append("Anomalie de plausibilité ou de sécurité du document")

        needs_priority_review = (
            security.get("suspicious", False)
            or not rule_result["valid"]
            or any(
                decision["status"] == "signale"
                for decision in field_decisions.values()
            )
        )

        if needs_priority_review:
            logger.warning(
                "[ValidationAgent] Document %s signalé pour revue "
                "prioritaire (sécurité=%s, règles_ok=%s, champs_signalés=%s)",
                document_type,
                security.get("suspicious", False),
                rule_result["valid"],
                [
                    f for f, d in field_decisions.items()
                    if d["status"] == "signale"
                ],
            )

        return {
            "document_type": document_type,
            "fields": field_decisions,
            "rule_engine": rule_result,
            "discrepancies": discrepancy_results,
            "security": security,
            "needs_priority_review": needs_priority_review,
        }

    # =====================================================
    # DECISION PAR CHAMP
    # =====================================================

    def _decide_fields(
        self,
        data: Dict[str, Any],
        confidences: Dict[str, Optional[float]],
        discrepancy_results: List[Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:

        discrepancies_by_field = {
            result["rule"][len("ecart_"):]: result
            for result in discrepancy_results
        }

        decisions: Dict[str, Dict[str, Any]] = {}

        for field_name, value in data.items():

            if field_name == "document_type":
                continue

            confidence = confidences.get(field_name)
            discrepancy = discrepancies_by_field.get(field_name)
            reasons: List[str] = []

            if value is None:
                status = "absent"
                reasons.append("Valeur non extraite ou illisible")

            else:
                status = "pre_rempli"

                if confidence is None:
                    status = "signale"
                    reasons.append("Confiance non fournie par l'extraction")

                elif confidence < settings.confidence_threshold:
                    status = "signale"
                    reasons.append(
                        f"Confiance {confidence:.2f} "
                        f"< seuil {settings.confidence_threshold:.2f}"
                    )

                if discrepancy is not None and discrepancy["passed"] is False:
                    status = "signale"
                    reasons.append(discrepancy["message"])

            decisions[field_name] = {
                "value": value,
                "confidence": confidence,
                "status": status,  # "pre_rempli" | "signale" | "absent"
                "reasons": reasons,
            }

        return decisions
