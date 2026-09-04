import csv
import io
import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from extraction.schema import DOCUMENT_SCHEMAS, ExtractedField, ReleveBancaireSchema
from extraction.provenance import verify_sources, page_text
from extraction.confirmation import make_confirmation, parse_confirmed_value, export_confirmed_csv


def decision(value=6000.0):
    return {"value": value, "confidence": 0.95, "status": "pre_rempli", "reasons": [],
            "source": {"document": "fictif.pdf", "page": 2, "quote": "Net 6000",
                       "sha256": "abc", "verified": True}}


def confirm(value="6500", name="salaire_net", doc="A", original=None):
    return make_confirmation("bulletin", name, value, original or decision(),
                             document_id=doc, advisor_id="test", source_checked=True)


@pytest.mark.parametrize("score", [-0.1, 1.1, float("nan"), float("inf")])
def test_confidence_bounded(score):
    with pytest.raises(ValidationError):
        ExtractedField[float](value=1, confidence=score)


def test_required_schemas_and_prompts():
    from extraction.prompts import DOCUMENT_PROMPTS, SYSTEM_PROMPT
    from rule_engine.checks import RULES
    for document_type in DOCUMENT_SCHEMAS:
        assert document_type in DOCUMENT_PROMPTS and document_type in RULES
        assert "OCR" in DOCUMENT_PROMPTS[document_type].format(ocr_text="[PAGE 1] fictif")
    assert "source" in SYSTEM_PROMPT
    fields = ReleveBancaireSchema.model_fields
    assert "charge_mensuelle_credits" in fields and "revenus_complementaires" in fields


@pytest.mark.parametrize("value,expected", [("6 500,50", 6500.5), ("0", 0.0), ("6\u202f000", 6000.0)])
def test_numeric_correction(value, expected):
    record = confirm(value)
    assert type(record["value"]) is float
    assert record["value"] == expected


@pytest.mark.parametrize("value", ["NaN", "inf", "-1", "bonjour", "", True])
def test_invalid_required_amount_rejected(value):
    with pytest.raises((ValueError, TypeError)):
        confirm(value)


@pytest.mark.parametrize("value,expected", [("01/02/2020", "2020-02-01"), ("2020-02-01", "2020-02-01")])
def test_date_normalized(value, expected):
    assert parse_confirmed_value("bulletin", "date_embauche", value) == expected


@pytest.mark.parametrize("value", ["31/02/2020", "2999-01-01", ""])
def test_invalid_date_rejected(value):
    with pytest.raises(ValueError):
        parse_confirmed_value("bulletin", "date_embauche", value)


def test_explicit_confirmation_required():
    with pytest.raises(ValueError):
        make_confirmation("bulletin", "salaire_net", "6000", decision(),
                          document_id="A", advisor_id="test")
    with pytest.raises(ValueError):
        make_confirmation("bulletin", "salaire_net", "6000", decision(),
                          document_id="A", advisor_id="", source_checked=True)


def test_unchanged_numeric_not_correction():
    assert confirm("6000")["status"] == "confirme"
    assert confirm("6500")["status"] == "corrige"
    assert confirm("6500", original=decision(None))["status"] == "corrige"


@pytest.mark.parametrize("page,quote,valid", [(2, "Net 6000", True), (1, "Net 6000", False),
                                             (9, "Net 6000", False), (2, "Net 9999", False),
                                             (2, "", False), (None, None, False)])
def test_provenance_checked_against_actual_page(page, quote, valid):
    raw = {"salaire_net": {"value": 6000, "source": {"page": page, "quote": quote,
            "document": "invented.pdf", "verified": True}}}
    result = verify_sources(raw, [{"page": 1, "text": "Entête"}, {"page": 2, "text": "Net 6000 MAD"}],
                            "trusted.pdf", "hash")["salaire_net"]
    assert result["verified"] is valid
    assert result["document"] == "trusted.pdf" and result["sha256"] == "hash"
    if not valid:
        assert result["page"] is None and result["quote"] is None


def test_blank_pages_keep_numbering():
    assert "[PAGE 2]" in page_text([{"page": 1, "text": ""}, {"page": 2, "text": "Net 6000"}])


def test_csv_uses_only_typed_confirmed_values():
    result = {"validation_result": {"fields": {"salaire_net": decision(), "employeur": decision("Fictif")}}}
    assert export_confirmed_csv(result, "bulletin", {}, "A") is None
    assert export_confirmed_csv(result, "bulletin", {"salaire_net": "6500"}, "A") is None
    assert export_confirmed_csv(result, "bulletin", {"salaire_net": confirm(doc="B")}, "A") is None
    data = export_confirmed_csv(result, "bulletin", {"salaire_net": confirm()}, "A")
    rows = list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))
    assert len(rows) == 1 and rows[0]["Valeur finale"] == "6500.0"
    assert rows[0]["Page"] == "2" and rows[0]["Statut humain"] == "corrige"


def test_csv_formula_escaped():
    result = {"validation_result": {"fields": {"employeur": decision("=1+1")}}}
    data = export_confirmed_csv(result, "bulletin", {"employeur": confirm("=1+1", "employeur")}, "A")
    assert "'=1+1" in data.decode("utf-8-sig")


def test_missing_source_flagged():
    from agents.validation_agent import ValidationAgent
    result = ValidationAgent().run("bulletin", {"salaire_net": 6000}, {"salaire_net": 0.99}, {})
    assert result["fields"]["salaire_net"]["status"] == "signale"


def test_pipeline_provenance_and_audit(tmp_path, monkeypatch):
    from database import audit
    monkeypatch.setattr(audit, "settings", SimpleNamespace(database_path=tmp_path / "audit.db"))
    audit.init_audit_table()
    from workflows import document_workflow as wf
    from extraction.extractor import DocumentExtractor
    # Only OCR and inference are substituted: validation, graph and SQLite are real.
    monkeypatch.setattr(wf, "_ocr_agent", SimpleNamespace(execute_pages=lambda p: [
        {"page": 1, "text": "Entête fictive"}, {"page": 2, "text": "Net 6000 MAD"}]))
    monkeypatch.setattr(DocumentExtractor, "call_llm", lambda self, prompt: json.dumps({
        "salaire_net": {"value": 6000, "confidence": 0.95,
                        "source": {"page": 2, "quote": "Net 6000 MAD"}}}))
    path = tmp_path / "fictif.pdf"
    path.write_bytes(b"%PDF-1.4\n% fictitious test header")
    result = wf.workflow.invoke({"pdf_path": str(path), "document_type": "bulletin",
                                 "advisor_id": "test", "session_id": "session", "declared_data": {}})
    source = result["validation_result"]["fields"]["salaire_net"]["source"]
    assert source["verified"] and source["page"] == 2
    assert len(source["sha256"]) == 64
    events = audit.get_audit_trail(document_path=str(path))
    event = next(e for e in events if e["field_name"] == "salaire_net")
    assert json.loads(event["details"])["source"] == source
    audit.log_human_confirmation(str(path), "bulletin", "salaire_net", 6500.0, "test",
                                 original_value=6000.0, source=source, confirmation_status="corrige")
    assert audit.get_audit_trail(document_path=str(path))[0]["decision"] == "corrigé_par_humain"


def test_human_audit_error_propagates(monkeypatch):
    from database import audit
    class BrokenConnection:
        def execute(self, *args):
            raise RuntimeError("disk full")
        def close(self):
            pass
    monkeypatch.setattr(audit, "get_connection", lambda: BrokenConnection())
    with pytest.raises(RuntimeError, match="disk full"):
        audit.log_human_confirmation("fictif.pdf", "bulletin", "salaire_net", 6000, "test")


@pytest.mark.parametrize("extracted,expected", [(0, True), (500, False)])
def test_zero_declared_charge(extracted, expected):
    from rule_engine.discrepancy import check_discrepancy
    assert check_discrepancy("charge_mensuelle_credits", 0, extracted)["passed"] is expected


def test_non_finite_extraction_rejected():
    with pytest.raises(ValidationError):
        ExtractedField[float](value=float("nan"))


def test_ocr_retains_blank_page_boundaries(monkeypatch):
    import importlib.util
    import sys
    from pathlib import Path
    # Exercise the real page assembly method without installing OCR models.
    monkeypatch.setitem(sys.modules, "cv2", SimpleNamespace())
    monkeypatch.setitem(sys.modules, "paddleocr", SimpleNamespace(PaddleOCR=object))
    monkeypatch.setitem(sys.modules, "ocr.pdf_loader", SimpleNamespace(PDFLoader=object))
    monkeypatch.setitem(sys.modules, "ocr.preprocessing", SimpleNamespace(ImagePreprocessor=object))
    spec = importlib.util.spec_from_file_location("ocr_engine_under_test", Path(__file__).parents[1] / "ocr/ocr_engine.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = module.OCREngine.__new__(module.OCREngine)
    engine.loader = SimpleNamespace(load=lambda path: [[], [{"text": "Net 6000"}]])
    engine.image_to_text = lambda image: image
    assert engine.document_to_pages("fictif.pdf") == [
        {"page": 1, "text": ""}, {"page": 2, "text": "Net 6000"}]
