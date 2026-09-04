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
    "salaire_net": {"value": 6000.0, "confidence": 0.9, "reasons": [],
        "source": {"document": "fictif.pdf", "page": 2, "quote": "Net 6000", "verified": True}}
}}}
render_document_review(result, "bulletin", "A", "test", "session", st.session_state.confirmations)
st.session_state.csv_result = export_confirmed_csv(result, "bulletin", st.session_state.confirmations, "A")
'''


def test_edit_confirm_reopen_and_export(tmp_path, monkeypatch):
    from database import audit
    monkeypatch.setattr(audit, "settings", SimpleNamespace(database_path=tmp_path / "audit.db"))
    audit.init_audit_table()
    app = AppTest.from_string(REVIEW_APP).run()
    assert not app.exception
    assert app.session_state.csv_result is None
    app.number_input[0].set_value(6500.0).run()
    app.checkbox[0].check().run()
    app.button(key="confirm_salaire_net_A").click().run()
    assert not app.exception
    record = app.session_state.confirmations["salaire_net"]
    assert record["value"] == 6500.0 and record["status"] == "corrige"
    rows = list(csv.DictReader(io.StringIO(app.session_state.csv_result.decode("utf-8-sig"))))
    assert rows[0]["Valeur finale"] == "6500.0"
    app.button(key="reopen_A_salaire_net").click().run()
    assert not app.exception
    assert app.session_state.csv_result is None
    assert app.number_input[0].value == 6500.0
    assert not app.checkbox[0].value


def test_audit_failure_does_not_confirm(monkeypatch):
    from database import audit
    def fail(*args, **kwargs):
        raise RuntimeError("audit indisponible")
    monkeypatch.setattr(audit, "log_human_confirmation", fail)
    app = AppTest.from_string(REVIEW_APP).run()
    app.checkbox[0].check().run()
    app.button(key="confirm_salaire_net_A").click().run()
    assert not app.exception and app.error
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


def test_missing_extracted_amount_stays_empty():
    app = AppTest.from_string(REVIEW_APP.replace('"value": 6000.0', '"value": None')).run()
    assert not app.exception
    assert app.number_input[0].value is None
    app.checkbox[0].check().run()
    app.button(key="confirm_salaire_net_A").click().run()
    assert not app.exception and app.error
    assert not app.session_state.confirmations


def test_full_app_document_switch(tmp_path, monkeypatch):
    import sys
    from pathlib import Path
    from database import audit
    # No model calls, but the real app entry point and review interface run.
    monkeypatch.setitem(sys.modules, "agents.orchestrator", SimpleNamespace(Orchestrator=lambda: object()))
    monkeypatch.setattr(audit, "settings", SimpleNamespace(database_path=tmp_path / "audit.db"))
    audit.init_audit_table()
    app = AppTest.from_file(str(Path(__file__).parents[1] / "app.py"))
    result = {"control_result": {"valid": True}, "validation_result": {
        "fields": {"salaire_net": {"value": 6000.0, "confidence": 0.95,
                   "status": "pre_rempli", "reasons": [], "source": None}},
        "needs_priority_review": True, "rule_engine": {}, "discrepancies": []}}
    docs = {key: {"client_id": "fictif", "type": "bulletin", "filename": key + ".pdf",
                  "result": result, "confirmed_fields": {}, "status": "completed"}
            for key in ("A", "B")}
    for key, value in {"page": "Extraction", "current_client_id": "fictif",
                       "documents": docs, "current_doc_id": "A", "last_result": result}.items():
        app.session_state[key] = value
    app.run()
    assert not app.exception
    app.number_input(key="review_value_A_salaire_net").set_value(6500.0).run()
    app.checkbox(key="review_check_A_salaire_net").check().run()
    app.button(key="confirm_salaire_net_A").click().run()
    assert not app.exception
    app.button(key="view_B").click().run()
    assert not app.exception
    assert app.session_state.documents["B"]["confirmed_fields"] == {}
    app.button(key="view_A").click().run()
    assert not app.exception
    assert app.session_state.documents["A"]["confirmed_fields"]["salaire_net"]["value"] == 6500.0
