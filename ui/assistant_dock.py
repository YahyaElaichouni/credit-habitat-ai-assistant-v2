"""Assistant habitat flottant et synchronisation de son profil."""

import logging
from pathlib import Path

import streamlit as st

from utils.document_processing import get_orchestrator

def apply_assistant_result(result):
    """Mémoriser le profil et préremplir l'estimation rapide."""
    profile = result.get("profile")
    if not isinstance(profile, dict):
        return

    st.session_state.credit_profile = profile
    project = dict(st.session_state.get("quick_project", {}))
    project_mapping = {
        "prix_bien": "purchase_price",
        "apport_personnel": "contribution",
        "duree_souhaitee_annees": "duration_years",
    }
    widget_mapping = {
        "prix_bien": ("quick_price",),
        "apport_personnel": (
            "quick_contribution",
            "quick_capacity_contribution",
        ),
        "duree_souhaitee_annees": (
            "quick_years",
            "quick_capacity_years",
        ),
        "revenu_mensuel_net": ("quick_capacity_income",),
        "charges_mensuelles": ("quick_capacity_charges",),
    }

    for field in result.get("profile_updates", {}):
        if field in project_mapping and profile.get(field) is not None:
            project[project_mapping[field]] = profile[field]
        for widget_key in widget_mapping.get(field, ()):
            st.session_state.pop(widget_key, None)

    st.session_state.quick_project = project


def render_assistant_dock(advisor_id):
    """Afficher un assistant flottant lisible sur ordinateur et mobile."""
    robot_path = Path(__file__).resolve().parents[1] / "assets" / "assistant_habitat_robot.png"
    assistant_avatar = str(robot_path) if robot_path.exists() else ":material/smart_toy:"

    if not st.session_state.assistant_open:
        with st.container(key="assistant_launcher"):
            if st.button(
                "Nour · Assistant habitat",
                icon=":material/smart_toy:",
                key="open_assistant_dock",
                width="stretch",
                help="Ouvrir votre assistant virtuel",
            ):
                st.session_state.assistant_open = True
                st.rerun()
        return

    with st.container(key="assistant_dock", border=True):
        avatar_col, title_col, close_col = st.columns(
            [1.2, 5.6, 1],
            vertical_alignment="center",
        )
        with avatar_col:
            if robot_path.exists():
                st.image(str(robot_path), width=54)
            else:
                st.markdown(":material/smart_toy:")
        with title_col:
            st.markdown("**Nour, votre assistant habitat**")
            st.caption("En ligne · Je vous accompagne étape par étape")
        with close_col:
            if st.button(
                "×",
                key="assistant_close",
                help="Fermer l’assistant",
                width="content",
            ):
                st.session_state.assistant_open = False
                st.rerun()

        history = st.session_state.chat_history[-6:]
        if not history:
            st.write(
                "Bonjour ! Je vais vous accompagner étape par étape. "
                "Vous pouvez commencer par me parler de votre profession "
                "et de votre projet immobilier."
            )
            suggestions = {
                "Décrire ma situation": (
                    "Je souhaite préparer mon projet de crédit habitat."
                ),
                "Documents à préparer": "Quels documents dois-je préparer pour ma simulation ?",
                "Estimer ma mensualité": "Comment est calculée la mensualité de mon crédit habitat ?",
            }
            selected = st.pills(
                "Questions suggérées",
                list(suggestions),
                label_visibility="collapsed",
                key="assistant_dock_suggestions",
            )
            suggested_question = suggestions.get(selected)
        else:
            suggested_question = None
            with st.container(height=320, border=False):
                for exchange in history:
                    with st.chat_message("user", avatar=":material/person:"):
                        st.write(exchange["question"])
                    with st.chat_message("assistant", avatar=assistant_avatar):
                        st.write(exchange["answer"])

        question = st.chat_input(
            "Posez votre question…",
            key="assistant_dock_input",
            disabled=st.session_state.processing,
            submit_mode="disable",
        )
        question = question or suggested_question
        if not question:
            return

        with st.spinner("Nour prépare votre réponse…"):
            try:
                answer = get_orchestrator().handle_question(
                    question=question,
                    advisor_id=advisor_id,
                    session_id=st.session_state.session_id,
                    profile=st.session_state.credit_profile,
                    conversation_history=st.session_state.chat_history,
                )
            except FileNotFoundError:
                st.error("La base documentaire n’est pas encore disponible.")
                return
            except Exception as exc:
                logging.exception("Assistant indisponible")
                st.error(f"L’assistant est momentanément indisponible : {exc}")
                return

        apply_assistant_result(answer)
        st.session_state.chat_history.append({
            "question": question,
            "answer": answer["answer"],
            "in_scope": answer.get("in_scope", False),
            "sources": answer.get("sources", []),
            "mode": answer.get("mode", "rag"),
            "profile_updates": answer.get("profile_updates", {}),
        })
        st.rerun()

