"""Composants visuels réutilisables de la page d'accueil."""

import base64
import html
from pathlib import Path

import streamlit as st

def image_to_data_url(image_path):
    """Convertir une image locale en URL intégrable dans le carrousel HTML."""
    path = Path(image_path)
    if not path.is_file():
        return ""

    mime_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }
    mime_type = mime_types.get(path.suffix.lower(), "image/png")
    encoded_image = base64.b64encode(path.read_bytes()).decode("utf-8")
    return f"data:{mime_type};base64,{encoded_image}"


def render_home_assurance_strip(on_start=None):
    """Présenter les bénéfices réels, puis détailler l'offre aux visiteurs."""
    with st.container(key="cam_assurance_strip"):
        for column, (icon, title, description) in zip(st.columns(3), (
            ("description", "Moins de ressaisie", "Les informations de vos justificatifs sont extraites pour vous aider à préparer votre dossier."),
            ("task_alt", "Vous gardez la main", "Vérifiez et corrigez les informations détectées avant votre simulation."),
            ("bookmark", "Un parcours à votre rythme", "Retrouvez votre projet et vos documents dans votre espace personnel."),
        )):
            with column:
                st.markdown(f":material/{icon}: **{title}**")
                st.caption(description)

    if st.session_state.get("account_created", False):
        return

    st.markdown("## Un projet important. Des démarches plus simples.")
    st.write("De vos premiers justificatifs à votre simulation, réunissez les étapes essentielles dans un même espace.")
    benefits = (
        ("document_scanner", "Moins de saisie, plus de simplicité",
         "L’analyse assistée par IA extrait les informations de vos pièces d’identité, bulletins de paie et relevés bancaires. Vous relisez les données proposées au lieu de tout recopier."),
        ("fact_check", "Un dossier plus clair",
         "Repérez les informations à compléter ou à corriger. Validez vos données et avancez avec un dossier mieux préparé."),
        ("tune", "Des scénarios à comparer",
         "Comparez les durées et les mensualités proposées dans votre simulation. Visualisez les mensualités estimées pour mieux préparer vos choix."),
        ("forum", "Des réponses pour avancer",
         "Posez vos questions à l’assistant habitat sur les étapes et les justificatifs. Ses réponses s’appuient sur la documentation disponible, avec des sources à consulter."),
        ("folder_open", "Votre projet au même endroit",
         "Retrouvez vos informations et vos justificatifs dans votre espace personnel. Reprenez votre préparation sans repartir de zéro."),
        ("route", "Un parcours qui vous guide",
         "Décrivez votre projet, ajoutez vos documents, vérifiez les informations puis simulez votre financement. Chaque étape vous aide à savoir quoi faire ensuite."),
    )
    for offset in range(0, len(benefits), 3):
        for column, (icon, title, description) in zip(st.columns(3, gap="medium"), benefits[offset:offset + 3]):
            with column.container(border=True, height="stretch"):
                st.markdown(f":material/{icon}:")
                st.markdown(f"### {title}")
                st.write(description)

    with st.container(border=True):
        st.markdown("### L’IA vous accompagne. Vous validez.")
        st.write("L’extraction automatique vous aide à préparer vos informations. Vous pouvez les vérifier et les corriger avant de poursuivre : votre validation reste une étape essentielle du parcours.")

    st.markdown("## Vos questions, avant de commencer")
    for question, answer in (
        ("Comment commencer ?", "Cliquez sur « Démarrer le parcours » en haut de cette page, puis créez votre compte ou connectez-vous. Vous pourrez ensuite renseigner votre projet et ajouter vos justificatifs."),
        ("Quels documents préparer ?", "Prévoyez une pièce d’identité, un bulletin de paie et un relevé bancaire lisibles. Le parcours vous indique les documents attendus et les informations à vérifier."),
        ("Puis-je corriger une information détectée ?", "Oui. L’analyse automatique peut comporter des erreurs. L’étape de vérification vous permet de relire et de corriger les informations avant la simulation."),
        ("La simulation vaut-elle accord de crédit ?", "Non. Elle fournit une estimation indicative pour préparer votre projet. L’octroi du financement reste soumis à l’étude et à la décision de la banque."),
    ):
        with st.expander(question):
            st.write(answer)
    with st.container(border=True):
        st.markdown("### Donnez une première direction à votre projet.")
        st.write("Créez votre espace pour préparer votre dossier, ou retrouvez votre parcours en vous connectant.")
        if on_start is not None:
            if st.button("Démarrer mon projet", type="primary", icon=":material/arrow_forward:", key="home_benefits_start"):
                on_start()
        st.caption("Simulation indicative. Le financement reste soumis à l’étude du dossier par la banque.")


