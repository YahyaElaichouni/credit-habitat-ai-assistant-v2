from agents.guidance_agent import GuidanceAgent


SIMULATION_QUESTION = """
Pouvez-vous me donner les informations suivantes :
- La durée du prêt choisie
- Le montant du financement souhaité
- Le taux d'intérêt choisi (fixe ou variable)
"""


def test_simulation_follow_up_keeps_financial_meaning():
    agent = GuidanceAgent(model="test")
    result = agent.run(
        "15 ans, 386000, 4.5",
        profile={},
        conversation_history=[{
            "question": "Estime ma mensualité",
            "answer": SIMULATION_QUESTION,
            "mode": "rag",
        }],
    )

    assert result["mode"] == "simulation"
    assert result["profile_updates"] == {
        "duree_souhaitee_annees": 15,
        "montant_financement_souhaite": 386000.0,
        "taux_annuel_indicatif": 4.5,
    }
    assert result["profile"]["anciennete_annees"] is None
    assert result["profile"]["revenu_mensuel_net"] is None
    assert "386 000 MAD" in result["answer"]
    assert "mensualité estimée" in result["answer"]


def test_three_numbers_without_simulation_context_are_not_forced():
    updates = GuidanceAgent._extract_simulation_follow_up(
        "15 ans, 386000, 4.5",
        [{"answer": "Quelle est votre profession ?"}],
    )

    assert updates == {}


def test_simulation_follow_up_rejects_invalid_values():
    updates = GuidanceAgent._extract_simulation_follow_up(
        "2 ans, 386000, 45",
        [{"answer": SIMULATION_QUESTION}],
    )

    assert updates == {}
