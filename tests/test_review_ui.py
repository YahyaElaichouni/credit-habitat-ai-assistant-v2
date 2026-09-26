import csv
import io
from types import SimpleNamespace

from streamlit.testing.v1 import AppTest


REVIEW_APP = '''
import streamlit as st
from ui.document_review import render_document_review
from extraction.confirmation import export_confirmed_csv
st.session_state.setdefault("confirmations", {})
result = {"validation_result": {"fields": {
    "employeur": {"value": "Entreprise Test", "confidence": 0.9, "reasons": [],
        "source": {"document": "fictif.pdf", "page": 1,
                   "quote": "Entreprise Test", "verified": True}},
    "date_embauche": {"value": "01/02/2020", "confidence": 0.9, "reasons": [],
        "source": {"document": "fictif.pdf", "page": 1,
                   "quote": "Date embauche 01/02/2020", "verified": True}},
    "salaire_net": {"value": 6000.0, "confidence": 0.9, "reasons": [],
        "source": {"document": "fictif.pdf", "page": 2,
                   "quote": "Net 6000", "verified": True}}
}}}
render_document_review(
    result, "bulletin", "A", "test", "session",
    st.session_state.confirmations,
)
st.session_state.csv_result = export_confirmed_csv(
    result, "bulletin", st.session_state.confirmations, "A"
)
'''


def _submit_review(app, label="Valider et continuer"):
    submit = next(button for button in app.button if button.label == label)
    return submit.click().run()


def test_edit_confirm_reopen_and_export(tmp_path, monkeypatch):
    from database import audit

    monkeypatch.setattr(
        audit,
        "settings",
        SimpleNamespace(database_path=tmp_path / "audit.db"),
    )
    audit.init_audit_table()

    app = AppTest.from_string(REVIEW_APP).run()
    assert not app.exception
    assert app.session_state.csv_result is None

    app.text_input(key="review_value_A_salaire_net").set_value("6500.0").run()
    app = _submit_review(app)

    assert not app.exception
    record = app.session_state.confirmations["salaire_net"]
    assert record["value"] == 6500.0
    assert record["status"] == "corrige"

    rows = list(csv.DictReader(
        io.StringIO(app.session_state.csv_result.decode("utf-8-sig"))
    ))
    salary_row = next(row for row in rows if row["Champ"] == "salaire_net")
    assert salary_row["Valeur finale"] == "6500.0"

    app = app.run()
    assert not app.exception
    assert app.text_input(key="review_value_A_salaire_net").value == "6500.0"


def test_audit_failure_does_not_confirm(monkeypatch):
    from database import audit

    def fail(*args, **kwargs):
        raise RuntimeError("audit indisponible")

    monkeypatch.setattr(audit, "log_human_confirmation", fail)
    app = AppTest.from_string(REVIEW_APP).run()
    app = _submit_review(app)

    assert not app.exception
    assert app.error
    assert app.session_state.confirmations == {}
    assert app.session_state.csv_result is None


def test_declared_blank_is_not_zero():
    app = AppTest.from_string('''
import streamlit as st
from ui.document_review import render_declared_form
st.session_state.values = render_declared_form("releve", "fictif")
''').run()
    assert not app.exception and app.session_state["values"] == {}
    app.number_input[0].set_value(0.0).run()
    assert app.session_state["values"]["charge_mensuelle_credits"] == 0.0


def test_discrepancy_warning_is_visible():
    app = AppTest.from_string(REVIEW_APP.replace(
        '"validation_result": {"fields": {',
        '"validation_result": {"discrepancies": '
        '[{"rule": "ecart_salaire_net", "passed": False, '
        '"message": "Écart salaire_net : 20.8 %, seuil 10 %"}], "fields": {',
    )).run()
    assert not app.exception
    assert any("Incohérence détectée" in warning.value for warning in app.warning)


def test_missing_extracted_amount_stays_empty():
    app = AppTest.from_string(
        REVIEW_APP.replace('"value": 6000.0', '"value": None')
    ).run()
    assert not app.exception
    assert app.text_input(key="review_value_A_salaire_net").value == ""

    app = _submit_review(app)
    assert not app.exception
    assert app.error
    assert not app.session_state.confirmations


def test_full_app_document_review_persists_confirmation(tmp_path, monkeypatch):
    import sys
    from pathlib import Path

    from database import audit
    from database import customer_accounts

    monkeypatch.setitem(
        sys.modules,
        "agents.orchestrator",
        SimpleNamespace(Orchestrator=lambda: object()),
    )
    monkeypatch.setattr(
        audit,
        "settings",
        SimpleNamespace(database_path=tmp_path / "audit.db"),
    )
    audit.init_audit_table()
    monkeypatch.setattr(
        customer_accounts,
        "load_project",
        lambda _customer_id: {
            "city": "Rabat",
            "property_type": "Appartement",
            "purchase_price": 800000.0,
            "contribution": 100000.0,
            "duration_years": 20,
        },
    )
    monkeypatch.setattr(
        customer_accounts,
        "save_document",
        lambda *args, **kwargs: None,
    )

    app = AppTest.from_file(str(Path(__file__).parents[1] / "app.py"))
    result = {
        "control_result": {"valid": True},
        "validation_result": {
            "fields": {
                "employeur": {
                    "value": "Entreprise Test", "confidence": 0.95,
                    "status": "pre_rempli", "reasons": [], "source": None,
                },
                "date_embauche": {
                    "value": "01/02/2020", "confidence": 0.95,
                    "status": "pre_rempli", "reasons": [], "source": None,
                },
                "salaire_net": {
                    "value": 6000.0, "confidence": 0.95,
                    "status": "pre_rempli", "reasons": [], "source": None,
                },
            },
            "needs_priority_review": True,
            "rule_engine": {},
            "discrepancies": [],
        },
    }
    document = {
        "client_id": "fictif",
        "type": "bulletin",
        "filename": "A.pdf",
        "result": result,
        "confirmed_fields": {},
        "status": "completed",
        "journey_reviewed": False,
    }
    for key, value in {
        "page": "Extraction",
        "account_created": True,
        "current_client_id": "fictif",
        "documents": {"A": document},
        "current_doc_id": "A",
        "last_result": result,
    }.items():
        app.session_state[key] = value

    app.run()
    assert not app.exception
    app.text_input(key="review_value_A_salaire_net").set_value("6500.0").run()
    app = _submit_review(app)

    assert not app.exception
    saved = app.session_state.documents["A"]
    assert saved["journey_reviewed"] is True
    assert saved["confirmed_fields"]["salaire_net"]["value"] == 6500.0
