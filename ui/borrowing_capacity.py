"""Calcul indicatif de la capacité d'emprunt."""

import math

import streamlit as st


def calculate_borrowing_capacity(
    monthly_income,
    existing_monthly_charges,
    contribution,
    years,
    annual_rate,
    target_debt_ratio,
):
    """
    Calculer la mensualité disponible et le capital empruntable.

    target_debt_ratio est exprimé en pourcentage :
    40 signifie 40 %.
    """

    values = (
        monthly_income,
        existing_monthly_charges,
        contribution,
        years,
        annual_rate,
        target_debt_ratio,
    )

    if not all(
        math.isfinite(float(value))
        for value in values
    ):
        raise ValueError(
            "Toutes les valeurs doivent être valides."
        )

    if monthly_income <= 0:
        raise ValueError(
            "Le revenu mensuel doit être supérieur à zéro."
        )

    if existing_monthly_charges < 0:
        raise ValueError(
            "Les charges existantes ne peuvent pas être négatives."
        )

    if contribution < 0:
        raise ValueError(
            "L'apport personnel ne peut pas être négatif."
        )

    if years <= 0:
        raise ValueError(
            "La durée doit être positive."
        )

    if annual_rate < 0:
        raise ValueError(
            "Le taux doit être positif ou nul."
        )

    if not 0 < target_debt_ratio <= 100:
        raise ValueError(
            "Le taux d'endettement doit être compris "
            "entre 0 et 100 %."
        )

    ratio = target_debt_ratio / 100
    maximum_total_charges = monthly_income * ratio

    available_payment = max(
        0.0,
        maximum_total_charges - existing_monthly_charges,
    )

    months = int(years * 12)
    monthly_rate = annual_rate / 1200

    if available_payment == 0:
        borrowing_capacity = 0.0

    elif monthly_rate == 0:
        borrowing_capacity = (
            available_payment * months
        )

    else:
        borrowing_capacity = (
            available_payment
            * (
                1
                - (1 + monthly_rate) ** -months
            )
            / monthly_rate
        )

    total_payments = available_payment * months

    interest_cost = max(
        0.0,
        total_payments - borrowing_capacity,
    )

    maximum_property_price = (
        borrowing_capacity + contribution
    )

    current_debt_ratio = (
        existing_monthly_charges
        / monthly_income
        * 100
    )

    return {
        "monthly_income": monthly_income,
        "existing_monthly_charges": (
            existing_monthly_charges
        ),
        "target_debt_ratio": target_debt_ratio,
        "current_debt_ratio": current_debt_ratio,
        "maximum_total_charges": (
            maximum_total_charges
        ),
        "available_monthly_payment": (
            available_payment
        ),
        "borrowing_capacity": borrowing_capacity,
        "contribution": contribution,
        "maximum_property_price": (
            maximum_property_price
        ),
        "duration_years": years,
        "annual_rate": annual_rate,
        "interest_cost": interest_cost,
        "total_payments": total_payments,
    }


def render_borrowing_capacity(
    project=None,
    *,
    key_prefix="capacity",
    income=None,
    existing_monthly_charges=None,
):
    """Afficher le calcul de capacité d'emprunt."""

    project = project or {}

    st.subheader("Ma capacité d'emprunt")

    st.caption(
        "Découvrez le montant approximatif que vous pourriez "
        "emprunter selon vos revenus, vos charges et la durée."
    )

    verified_situation = (
        income is not None
        and float(income) > 0
    )

    # -----------------------------------------------------
    # REVENUS ET CHARGES
    # -----------------------------------------------------

    if verified_situation:
        monthly_income = float(income)

        monthly_charges = float(
            existing_monthly_charges or 0
        )

        st.success(
            "Calcul effectué à partir de vos informations vérifiées."
        )

        income_column, charges_column = st.columns(2)

        with income_column:
            st.metric(
                "Revenu mensuel vérifié",
                f"{monthly_income:,.2f} MAD",
            )

        with charges_column:
            st.metric(
                "Charges mensuelles existantes",
                f"{monthly_charges:,.2f} MAD",
            )

    else:
        income_column, charges_column = st.columns(2)

        with income_column:
            monthly_income = st.number_input(
                "Revenu mensuel net (MAD)",
                min_value=0.0,
                value=8000.0,
                step=500.0,
                key=f"{key_prefix}_income",
            )

        with charges_column:
            monthly_charges = st.number_input(
                "Crédits et charges mensuelles (MAD)",
                min_value=0.0,
                value=0.0,
                step=250.0,
                key=f"{key_prefix}_charges",
            )

    # -----------------------------------------------------
    # HYPOTHÈSES DU PROJET
    # -----------------------------------------------------

    contribution_column, duration_column = st.columns(2)

    with contribution_column:
        contribution = st.number_input(
            "Apport personnel (MAD)",
            min_value=0.0,
            value=float(
                project.get(
                    "contribution",
                    100000,
                )
            ),
            step=5000.0,
            key=f"{key_prefix}_contribution",
        )

    with duration_column:
        years = st.slider(
            "Durée du crédit",
            min_value=5,
            max_value=30,
            value=int(
                project.get(
                    "duration_years",
                    20,
                )
            ),
            format="%d ans",
            key=f"{key_prefix}_years",
        )

    with st.expander(
        "Taux et hypothèse d'endettement"
    ):
        annual_rate = st.number_input(
            "Taux annuel indicatif (%)",
            min_value=0.0,
            max_value=20.0,
            value=float(
                project.get(
                    "annual_rate",
                    4.5,
                )
            ),
            step=0.05,
            key=f"{key_prefix}_rate",
        )

        target_debt_ratio = st.slider(
            "Taux d'endettement maximal utilisé",
            min_value=20,
            max_value=60,
            value=40,
            step=1,
            format="%d %%",
            key=f"{key_prefix}_debt_limit",
        )

        st.caption(
            "Le seuil de 40 % est une hypothèse de simulation "
            "modifiable. La décision finale dépend des règles "
            "et de l'étude réalisées par la banque."
        )

    # -----------------------------------------------------
    # CALCUL
    # -----------------------------------------------------

    try:
        result = calculate_borrowing_capacity(
            monthly_income=monthly_income,
            existing_monthly_charges=monthly_charges,
            contribution=contribution,
            years=years,
            annual_rate=annual_rate,
            target_debt_ratio=target_debt_ratio,
        )

    except ValueError as error:
        st.error(str(error))
        return None

    # -----------------------------------------------------
    # RÉSULTAT
    # -----------------------------------------------------

    if result["available_monthly_payment"] <= 0:
        st.warning(
            "Vos charges actuelles atteignent déjà le niveau "
            "d'endettement utilisé pour cette estimation."
        )

        st.metric(
            "Capacité d'emprunt estimée",
            "0.00 MAD",
        )

        return result

    st.markdown("#### Votre estimation")

    first_column, second_column, third_column = (
        st.columns(3)
    )

    with first_column:
        st.metric(
            "Mensualité disponible",
            (
                f"{result['available_monthly_payment']:,.2f} "
                "MAD / mois"
            ),
        )

    with second_column:
        st.metric(
            "Capital empruntable",
            f"{result['borrowing_capacity']:,.2f} MAD",
        )

    with third_column:
        st.metric(
            "Budget immobilier estimé",
            (
                f"{result['maximum_property_price']:,.2f} "
                "MAD"
            ),
        )

    st.info(
        "Votre budget immobilier estimé correspond au capital "
        "empruntable augmenté de votre apport personnel."
    )

    with st.expander(
        "Voir le détail du calcul"
    ):
        st.write(
            "Revenu mensuel pris en compte : "
            f"{result['monthly_income']:,.2f} MAD"
        )

        st.write(
            "Charges mensuelles existantes : "
            f"{result['existing_monthly_charges']:,.2f} MAD"
        )

        st.write(
            "Mensualité totale maximale : "
            f"{result['maximum_total_charges']:,.2f} MAD"
        )

        st.write(
            "Mensualité disponible pour le nouveau crédit : "
            f"{result['available_monthly_payment']:,.2f} MAD"
        )

        st.write(
            "Coût estimé des intérêts : "
            f"{result['interest_cost']:,.2f} MAD"
        )

        st.write(
            f"Durée utilisée : {result['duration_years']} ans"
        )

        st.write(
            "Taux annuel utilisé : "
            f"{result['annual_rate']:.2f} %"
        )

    st.caption(
        "Cette capacité d'emprunt est une estimation indicative "
        "et non contractuelle. Elle ne constitue pas une décision "
        "d'octroi de crédit."
    )

    return result