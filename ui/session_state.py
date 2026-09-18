"""Initialisation centralisée de l'état de session Streamlit."""

import uuid

import streamlit as st


SESSION_DEFAULTS = {
    "documents": {},
    "current_doc_id": None,
    "confirmed_fields": {},
    "last_result": None,
    "chat_history": [],
    "credit_profile": {},
    "page": "Accueil",
    "theme": "light",
    "processing": False,
    "last_error": None,
    "assistant_open": False,
    "account_created": False,
    "customer_profile": {},
    "compromis_skipped": False,
    "additional_statement_mode": False,
    "editing_home_project": False,
    "continue_after_project": False,
    "advisor_authenticated": False,
    "advisor_username": None,
}


def initialize_session_state():
    """Créer une fois toutes les clés partagées entre les écrans."""
    st.session_state.setdefault("session_id", str(uuid.uuid4()))
    for key, default in SESSION_DEFAULTS.items():
        # Copier les conteneurs afin qu'aucune session ne partage un objet mutable.
        value = default.copy() if isinstance(default, (dict, list)) else default
        st.session_state.setdefault(key, value)

    if not st.session_state.get("current_client_id"):
        st.session_state.current_client_id = (
            f"client-{st.session_state.session_id[:8]}"
        )

    # L'ancienne page dédiée est remplacée par l'assistant permanent.
    if st.session_state.page == "Assistant":
        st.session_state.page = "Accueil"
