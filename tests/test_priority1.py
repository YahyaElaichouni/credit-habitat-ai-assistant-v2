import csv
import io
import json
import sys
from pathlib import Path
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


def test_cih_glued_dates_and_received_transfers_are_summed():
    """Les deux dates CIH peuvent être accolées par l'OCR (01/0901/09)."""
    from extraction.financial_metrics import derive_complementary_income

    pages = [{"page": 1, "text": "\n".join([
        "SOLDE DEPART AU : 31/08/2023 | CREDIT: 45 674,66",
        "01/0901/09 | VIREMENT RECU DE ABDELALI OUALAYAD | CREDIT: 500,00",
        "03/0903/09 | VIREMENT RECU DE MERIEM MOUDAKIR | CREDIT: 250,00",
        "04/0904/09 | RECHARGE MAROC TELECOM | DEBIT: 10,00",
        "04/0904/09 | VIRT RECU DE LA PART HUTOELLE | CREDIT: 13 175,79",
        "10/0910/09 | RETRAIT CARTE GAB | DEBIT: 1 000,00",
    ])}]

    result = derive_complementary_income([], pages, "cih.png", "sha")

    assert result is not None
    assert result["value"] == pytest.approx(750.0)
    assert len(result["source"]["evidence"]) == 2
    assert result["source"]["excluded_evidence"][0]["montant"] == pytest.approx(13175.79)
    assert "remboursement" in result["source"]["excluded_evidence"][0]["reason"]


def test_cih_fragmented_received_transfers_are_all_summed():
    """Les séparateurs et fautes OCR ne doivent pas supprimer des crédits CIH."""
    from extraction.financial_metrics import derive_complementary_income

    pages = [{"page": 1, "text": "\n".join([
        "SOLDE DEPART AU : 31/08/2023 | 45 674,66",
        "02/0102/80 | VIRENENT | RECU DE ABDELALI CUALAATAD | 500,00",
        # Virement sortant déformé : il ne doit pas devenir un revenu.
        "02/0102/80 | VIRENENT | cNI3 | EN FATEUR DE BENEFICIAIRE | :0 026,60",
        "03/0103/0% | VIREMENT RECU DE MERIEE MOUDAKIR | 250,00",
        "03/0103/80 | VIRENENT RECU DX LARBI EL JID | 300,00",
        "03/0103/0% | VIREMENT RECU DE EOUSSAM ZAOUGULA | 520,00",
        "04/0304/05 | VIRT RECU DE LA PART MUTUELLE | 13 175,79",
        "05/0905/05 | VIREMENT | RECU DE MOEAMED TARAKI | 4 150,00",
        "05/0305/09 | RECU | DE | KHADIJA EL FATIEI | 1000.00",
        "05/01/5/80 | DE KIND CEOUF | 180,00",
        "08/018/80 | VIRENENT | Do | KIND CEOUF | 88:0,00",
        "08/03018/0% | VIREMENT | RECU | DE KIND CHOUF | 1 100,00",
        "09/0109/80 | VIRENENT | RECU | DX KIND CEOUF | 690,00",
        "10/01:0/80 | VIRENENT | RECU | DX KIND CEOUF | 440,00",
        "12/0302/0% | VIREMENT RECU | VIREMNT RECU DE EIND CEOEF | 400.00",
    ])}]

    result = derive_complementary_income([], pages, "cih.png", "sha")

    assert result is not None
    assert result["value"] == pytest.approx(10410.0)
    assert len(result["source"]["evidence"]) == 12
    assert [item["montant"] for item in result["source"]["excluded_evidence"]] == [
        pytest.approx(13175.79)
    ]
    assert all(item["montant"] != pytest.approx(26.6)
               for item in result["source"]["evidence"])


def test_attijari_wrong_column_marker_does_not_hide_received_transfers():
    """Un faux marqueur CREDIT ne doit ni compter un émis ni masquer les reçus."""
    from extraction.financial_metrics import derive_complementary_income

    pages = [{"page": 1, "text": "\n".join([
        "SOLDE DEPART AU 31 12 2019 | 142 811,90 CREDITEUR",
        # Marqueur volontairement erroné, comme sur la reconstruction OCR.
        "03 01 | VIR. EMIS WEB VERS LEMKHENTER | 03 01 2020 | CREDIT: 500,00",
        # Les deux vrais crédits n'ont plus de marqueur de colonne.
        "08 01 | VIREMENT RECU DE TRESORERIE PREFECTURE | 09 01 2020 | 5 621,62",
        "08 01 | VIREMENT RECU DE TRESORERIE PREFECTURE | 09 01 2020 | 6 158,88",
        "09 01 | PAIEMENT CB BOUTIQUE | 08 01 2020 | 638,52",
    ])}]

    result = derive_complementary_income([], pages, "attijari.png", "sha")

    assert result is not None
    assert result["value"] == pytest.approx(11780.50)
    assert sorted(item["montant"] for item in result["source"]["evidence"]) == [
        pytest.approx(5621.62), pytest.approx(6158.88)
    ]


def test_bank_fee_misclassified_by_model_is_not_income():
    """Un type LLM erroné ne transforme jamais des frais débités en revenu."""
    from extraction.financial_metrics import derive_complementary_income

    line = "26/01/2024 | PACKAGES FRAIS PACK GLOBAL BUSINESS | DEBIT: 80,00"
    income_line = "12/01/2024 | VERST DEPLACE 1351190 | CREDIT: 900,00"
    pages = [{"page": 1, "text": (
        "ANCIEN SOLDE AU 29/12/2023\n" + line + "\n" + income_line
    )}]
    transactions = [{
        "date": "26/01/2024",
        "description": "PACKAGES FRAIS PACK GLOBAL BUSINESS",
        "montant": 80.0,
        "type": "credit",  # erreur volontaire du modèle
        "page": 1,
        "quote": line,
    }]

    result = derive_complementary_income(transactions, pages, "cdm.png", "sha")

    assert result is not None
    assert result["value"] == 900.0
    assert result["source"].get("absence_based") is not True


def test_statement_layout_keeps_adjacent_operations_on_separate_rows(monkeypatch):
    """Deux opérations CIH proches verticalement ne doivent pas être fusionnées."""
    import importlib.util
    from types import SimpleNamespace

    monkeypatch.setitem(sys.modules, "paddleocr", SimpleNamespace(PaddleOCR=object))
    monkeypatch.setitem(sys.modules, "ocr.pdf_loader", SimpleNamespace(PDFLoader=object))
    monkeypatch.setitem(sys.modules, "ocr.preprocessing", SimpleNamespace(ImagePreprocessor=object))
    spec = importlib.util.spec_from_file_location(
        "ocr_engine_layout_test", Path(__file__).parents[1] / "ocr/ocr_engine.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def box(x0, y0, x1, y1):
        return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]

    lines = [
        {"text": "DEBIT", "bbox": box(600, 0, 680, 12)},
        {"text": "CREDIT", "bbox": box(720, 0, 810, 12)},
        {"text": "02/09", "bbox": box(10, 20, 60, 30)},
        {"text": "VIREMENT RECU A", "bbox": box(100, 20, 400, 30)},
        {"text": "500,00", "bbox": box(730, 20, 800, 30)},
        {"text": "03/09", "bbox": box(10, 25, 60, 35)},
        {"text": "VIREMENT RECU B", "bbox": box(100, 25, 400, 35)},
        {"text": "250,00", "bbox": box(730, 25, 800, 35)},
    ]
    rendered = module.OCREngine.lines_to_layout_text(lines)

    assert "02/09 | VIREMENT RECU A | CREDIT: 500,00" in rendered
    assert "03/09 | VIREMENT RECU B | CREDIT: 250,00" in rendered


def _load_ocr_engine_without_models(monkeypatch, module_name):
    """Charge le moteur sans importer ni initialiser les modèles PaddleOCR."""
    import importlib.util

    monkeypatch.setitem(sys.modules, "paddleocr", SimpleNamespace(PaddleOCR=object))
    monkeypatch.setitem(sys.modules, "ocr.pdf_loader", SimpleNamespace(PDFLoader=object))
    monkeypatch.setitem(
        sys.modules,
        "ocr.preprocessing",
        SimpleNamespace(ImagePreprocessor=object),
    )
    spec = importlib.util.spec_from_file_location(
        module_name, Path(__file__).parents[1] / "ocr/ocr_engine.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bulletin_never_runs_statement_credit_pass(monkeypatch):
    """La relecture CREDIT est strictement réservée aux relevés bancaires."""
    module = _load_ocr_engine_without_models(monkeypatch, "ocr_bulletin_scope_test")
    engine = module.OCREngine.__new__(module.OCREngine)
    engine.preprocessor = SimpleNamespace(preprocess=lambda image: image)
    engine.reader = SimpleNamespace(predict=lambda image: [{
        "rec_texts": ["PERIODE", "MATRICULE", "DATE D'EMBAUCHE"],
        "rec_scores": [0.99, 0.99, 0.99],
        "rec_polys": [None, None, None],
    }])
    engine._read_statement_credit_column = lambda *args: pytest.fail(
        "la passe CREDIT ne doit pas être appelée pour un bulletin"
    )

    image = __import__("numpy").zeros((100, 100, 3), dtype="uint8")
    engine.image_to_text(image, document_type="bulletin")


def test_bulletin_region_selection_targets_only_missing_area(monkeypatch):
    """Le net absent ne déclenche que la moitié basse du bulletin."""
    module = _load_ocr_engine_without_models(monkeypatch, "ocr_bulletin_regions_test")
    engine = module.OCREngine.__new__(module.OCREngine)
    calls = []
    engine.reader = SimpleNamespace(predict=lambda image: calls.append(image.shape) or [])

    image = __import__("numpy").zeros((100, 80, 3), dtype="uint8")
    engine._read_bulletin_regions(image, missing_markers=("NET A PAYER",))

    assert len(calls) == 1
    # Zone 48 %-100 %, agrandie 2,2 fois.
    assert calls[0][0] in {114, 115}
