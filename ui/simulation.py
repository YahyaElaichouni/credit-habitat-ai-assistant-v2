"""Simulation et comparaison de scénarios de crédit habitat."""

import csv
import io
import math

import streamlit as st


def calculate_payment(
    price,
    contribution,
    years,
    annual_rate,
):
    """Calculer le capital, la mensualité et les intérêts."""

    values = (
        price,
        contribution,
        years,
        annual_rate,
    )

    if not all(
        math.isfinite(float(value))
        for value in values
    ):
        raise ValueError(
            "Renseignez des montants valides."
        )

    if price <= 0:
        raise ValueError(
            "Le prix du bien doit être supérieur à zéro."
        )

    if contribution < 0 or contribution > price:
        raise ValueError(
            "L'apport doit être compris entre zéro "
            "et le prix du bien."
        )

    if years <= 0:
        raise ValueError(
            "La durée doit être positive."
        )

    if annual_rate < 0:
        raise ValueError(
            "Le taux doit être positif ou nul."
        )

    capital = price - contribution
    months = years * 12
    monthly_rate = annual_rate / 1200

    if capital == 0:
        payment = 0.0

    elif monthly_rate == 0:
        payment = capital / months

    else:
        payment = (
            capital
            * monthly_rate
            / (
                1
                - (1 + monthly_rate) ** -months
            )
        )

    interest = payment * months - capital

    return capital, payment, interest


def build_comparison_scenarios(
    price,
    contribution,
    durations,
    annual_rate,
    income=None,
    existing_monthly_charges=0,
):
    """Construire les scénarios de comparaison."""

    scenarios = []

    for duration in sorted(set(durations)):
        capital, payment, interest = calculate_payment(
            price=price,
            contribution=contribution,
            years=duration,
            annual_rate=annual_rate,
        )

        debt_ratio = None

        if income is not None and income > 0:
            debt_ratio = (
                existing_monthly_charges + payment
            ) / income * 100

        scenarios.append({
            "Durée": duration,
            "Capital financé": round(capital, 2),
            "Mensualité": round(payment, 2),
            "Coût des intérêts": round(interest, 2),
            "Total remboursé": round(
                capital + interest,
                2,
            ),
            "Taux d'endettement": (
                round(debt_ratio, 2)
                if debt_ratio is not None
                else None
            ),
        })

    return scenarios


def get_default_durations(selected_years):
    """Proposer trois durées différentes autour du choix principal."""

    if selected_years <= 7:
        durations = [
            selected_years,
            min(30, selected_years + 5),
            min(30, selected_years + 10),
        ]

    elif selected_years >= 28:
        durations = [
            max(5, selected_years - 10),
            max(5, selected_years - 5),
            selected_years,
        ]

    else:
        durations = [
            max(5, selected_years - 5),
            selected_years,
            min(30, selected_years + 5),
        ]

    # Éviter les doublons aux limites de 5 et 30 ans.
    durations = sorted(set(durations))

    for candidate in range(5, 31):
        if len(durations) >= 3:
            break

        if candidate not in durations:
            durations.append(candidate)

    return sorted(durations[:3])


def scenarios_to_csv(scenarios):
    """Créer le fichier CSV du comparateur."""

    output = io.StringIO()

    fieldnames = [
        "Durée",
        "Capital financé",
        "Mensualité",
        "Coût des intérêts",
        "Total remboursé",
        "Taux d'endettement",
    ]

    writer = csv.DictWriter(
        output,
        fieldnames=fieldnames,
        delimiter=";",
    )

    writer.writeheader()
    writer.writerows(scenarios)

    return output.getvalue().encode("utf-8-sig")


def render_comparison(
    price,
    contribution,
    selected_years,
    annual_rate,
    key_prefix,
    income=None,
    existing_monthly_charges=0,
):
    """Afficher le comparateur de scénarios."""

    st.divider()
    st.subheader("Comparer plusieurs scénarios")

    st.caption(
        "Comparez différentes durées pour trouver le meilleur "
        "équilibre entre mensualité et coût total du crédit."
    )

    default_durations = get_default_durations(
        selected_years
    )

    durations = st.multiselect(
        "Durées à comparer",
        options=list(range(5, 31)),
        default=default_durations,
        max_selections=3,
        format_func=lambda value: f"{value} ans",
        key=f"{key_prefix}_comparison_durations",
        help="Sélectionnez deux ou trois durées.",
    )

    if len(durations) < 2:
        st.info(
            "Sélectionnez au moins deux durées "
            "pour afficher la comparaison."
        )
        return []

    scenarios = build_comparison_scenarios(
        price=price,
        contribution=contribution,
        durations=durations,
        annual_rate=annual_rate,
        income=income,
        existing_monthly_charges=existing_monthly_charges,
    )

    # -----------------------------------------------------
    # CARTES DES SCÉNARIOS
    # -----------------------------------------------------

    columns = st.columns(len(scenarios))

    for column, scenario in zip(
        columns,
        scenarios,
    ):
        with column:
            duration = scenario["Durée"]

            if duration == selected_years:
                st.badge(
                    "Votre choix",
                    color="green",
                    icon=":material/check_circle:",
                )

            elif duration == min(durations):
                st.badge(
                    "Coût réduit",
                    color="blue",
                    icon=":material/savings:",
                )

            elif duration == max(durations):
                st.badge(
                    "Mensualité réduite",
                    color="gray",
                    icon=":material/calendar_month:",
                )

            st.markdown(f"### {duration} ans")

            st.metric(
                "Mensualité",
                f"{scenario['Mensualité']:,.2f} MAD",
            )

            st.caption(
                "Intérêts estimés : "
                f"{scenario['Coût des intérêts']:,.2f} MAD"
            )

            if scenario["Taux d'endettement"] is not None:
                ratio_value = scenario["Taux d'endettement"]

                st.metric(
                    "Endettement estimé",
                    f"{ratio_value:.2f} %",
                )

    # -----------------------------------------------------
    # TABLEAU COMPARATIF
    # -----------------------------------------------------

    st.markdown("#### Comparaison détaillée")

    table_rows = []

    for scenario in scenarios:
        row = {
            "Durée": f"{scenario['Durée']} ans",
            "Mensualité (MAD)": scenario["Mensualité"],
            "Intérêts (MAD)": scenario["Coût des intérêts"],
            "Total remboursé (MAD)": scenario["Total remboursé"],
        }

        if scenario["Taux d'endettement"] is not None:
            row["Endettement estimé (%)"] = (
                scenario["Taux d'endettement"]
            )

        table_rows.append(row)

    st.dataframe(
        table_rows,
        hide_index=True,
        width="stretch",
        column_config={
            "Mensualité (MAD)": st.column_config.NumberColumn(
                format="%.2f MAD",
            ),
            "Intérêts (MAD)": st.column_config.NumberColumn(
                format="%.2f MAD",
            ),
            "Total remboursé (MAD)": (
                st.column_config.NumberColumn(
                    format="%.2f MAD",
                )
            ),
            "Endettement estimé (%)": (
                st.column_config.NumberColumn(
                    format="%.2f %%",
                )
            ),
        },
    )

    shortest = min(
        scenarios,
        key=lambda scenario: scenario["Durée"],
    )

    longest = max(
        scenarios,
        key=lambda scenario: scenario["Durée"],
    )

    st.info(
        f"Sur {shortest['Durée']} ans, le coût des intérêts "
        f"est plus faible. Sur {longest['Durée']} ans, "
        "la mensualité est plus faible, mais le crédit "
        "coûte davantage au total."
    )

    st.download_button(
        "Télécharger la comparaison",
        data=scenarios_to_csv(scenarios),
        file_name="comparaison_simulations.csv",
        mime="text/csv",
        icon=":material/download:",
        width="stretch",
        key=f"{key_prefix}_download_comparison",
    )

    return scenarios


def render_simulation(
    project=None,
    *,
    key_prefix="quick",
    income=None,
    existing_monthly_charges=0,
):
    """Afficher une simulation et son comparateur."""

    project = project or {}

    st.subheader("Mon projet")

    price = st.number_input(
        "Prix du bien (MAD)",
        min_value=0.0,
        value=float(
            project.get(
                "purchase_price",
                600000,
            )
        ),
        step=10000.0,
        key=f"{key_prefix}_price",
    )

    contribution = st.number_input(
        "Mon apport personnel (MAD)",
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

    years = st.slider(
        "Durée souhaitée",
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
        "Taux et détails du calcul"
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

        st.caption(
            "Le taux est une hypothèse modifiable. "
            "Le taux proposé par la banque peut être différent."
        )

        details_container = st.container()

    try:
        capital, payment, interest = calculate_payment(
            price=price,
            contribution=contribution,
            years=years,
            annual_rate=annual_rate,
        )

    except ValueError as error:
        st.error(str(error))
        return None

    # -----------------------------------------------------
    # RÉSULTAT PRINCIPAL
    # -----------------------------------------------------

    result_column, cost_column = st.columns(2)

    with result_column:
        st.metric(
            "Mensualité estimée",
            f"{payment:,.2f} MAD / mois",
        )

    with cost_column:
        st.metric(
            "Coût estimé des intérêts",
            f"{interest:,.2f} MAD",
        )

    st.caption(
        f"Sur {years} ans · taux indicatif "
        f"{annual_rate:.2f} % · hors assurance et frais"
    )

    details_container.write(
        f"Montant à financer : {capital:,.2f} MAD"
    )

    details_container.write(
        f"Total estimé à rembourser : "
        f"{capital + interest:,.2f} MAD"
    )

    debt_ratio = None

    if income is not None and income > 0:
        debt_ratio = (
            existing_monthly_charges + payment
        ) / income

        st.metric(
            "Taux d'endettement estimé",
            f"{debt_ratio:.2%}",
        )

    # -----------------------------------------------------
    # COMPARATEUR
    # -----------------------------------------------------

    scenarios = render_comparison(
        price=price,
        contribution=contribution,
        selected_years=years,
        annual_rate=annual_rate,
        key_prefix=key_prefix,
        income=income,
        existing_monthly_charges=existing_monthly_charges,
    )

    st.caption(
        "Simulation indicative et non contractuelle, "
        "hors assurance et frais. Elle ne constitue "
        "pas un accord de crédit."
    )

    return {
        "purchase_price": price,
        "contribution": contribution,
        "duration_years": years,
        "monthly_payment": payment,
        "annual_rate": annual_rate,
        "interest_cost": interest,
        "debt_ratio": debt_ratio,
        "comparison": scenarios,
    }