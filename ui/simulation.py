"""Simulation indicative commune au parcours rapide et au dossier vérifié."""
import math

import streamlit as st


def calculate_payment(price, contribution, years, annual_rate):
    values = (price, contribution, years, annual_rate)
    if not all(math.isfinite(float(value)) for value in values):
        raise ValueError("Renseignez des montants valides.")
    if price <= 0 or contribution < 0 or contribution > price:
        raise ValueError("Le prix doit être positif et l'apport compris entre 0 et le prix du bien.")
    if years <= 0 or annual_rate < 0:
        raise ValueError("La durée doit être positive et le taux positif ou nul.")
    capital = price - contribution
    months = years * 12
    rate = annual_rate / 1200
    payment = capital / months if rate == 0 else capital * rate / (1 - (1 + rate) ** -months)
    return capital, payment, payment * months - capital


def render_simulation(project=None, *, key_prefix="quick"):
    project = project or {}
    result = st.container()
    st.subheader("Mon projet")
    price = st.number_input("Prix du bien (MAD)", min_value=0.0,
                            value=float(project.get("purchase_price", 600000)),
                            step=10000.0, key=f"{key_prefix}_price")
    contribution = st.number_input("Mon apport personnel (MAD)", min_value=0.0,
                                   value=float(project.get("contribution", 100000)),
                                   step=5000.0, key=f"{key_prefix}_contribution")
    years = st.slider("Durée souhaitée", 5, 30, int(project.get("duration_years", 20)),
                      format="%d ans", key=f"{key_prefix}_years")
    with st.expander("Taux et détails du calcul"):
        rate = st.number_input("Taux annuel indicatif (%)", min_value=0.0, max_value=20.0,
                               value=float(project.get("annual_rate", 4.5)), step=0.05, key=f"{key_prefix}_rate")
        st.caption("Hypothèse de simulation modifiable ; le taux proposé par la banque peut différer.")
        details = st.container()
    try:
        capital, payment, interest = calculate_payment(price, contribution, years, rate)
    except ValueError as exc:
        result.error(str(exc))
        return None
    result.metric("Mensualité estimée", f"{payment:,.2f} MAD / mois")
    result.caption(f"Sur {years} ans · taux indicatif {rate:.2f} % · hors assurance et frais")
    details.write(f"Montant à financer : {capital:,.2f} MAD")
    details.write(f"Coût estimé des intérêts : {interest:,.2f} MAD")
    st.caption("Estimation non contractuelle, hors assurance et frais. Elle ne constitue pas un accord de crédit.")
    return {"purchase_price": price, "contribution": contribution, "duration_years": years,
            "monthly_payment": payment, "annual_rate": rate}
