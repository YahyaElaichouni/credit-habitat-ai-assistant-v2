"""Non-régressions des chemins rapides OCR et extraction."""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


def _field(value, quote="preuve OCR", confidence=0.90):
    return {
        "value": value,
        "confidence": confidence,
        "source": {"page": 1, "quote": quote},
    }


def test_complete_deterministic_payroll_skips_ollama(monkeypatch):
    from extraction.extractor import DocumentExtractor

    deterministic = {
        "document_type": "bulletin",
        "nom": _field("Alaoui"),
        "prenom": _field("Nadia"),
        "employeur": _field("Entreprise Exemple"),
        "poste": _field("Analyste"),
        "date_embauche": _field("01/02/2020"),
        "periode": _field("08/2026"),
        "salaire_net": _field(9500.0),
    }
    monkeypatch.setattr(
        DocumentExtractor,
        "_deterministic_extract",
        staticmethod(lambda text, kind: deterministic),
    )
    monkeypatch.setattr(
        DocumentExtractor,
        "call_llm",
        lambda *args, **kwargs: pytest.fail("Ollama ne doit pas être appelé"),
    )

    result = DocumentExtractor().extract("[PAGE 1]\npreuve OCR", "bulletin")

    assert result.salaire_net.value == 9500.0
    assert result.employeur.value == "Entreprise Exemple"


def test_extraction_cache_returns_independent_copies(monkeypatch):
    from extraction.extractor import DocumentExtractor

    deterministic = {
        "document_type": "releve",
        "banque": _field("CIH Bank"),
        "periode_debut": _field("01/08/2026"),
        "periode_fin": _field("31/08/2026"),
    }
    monkeypatch.setattr(
        DocumentExtractor,
        "_deterministic_extract",
        staticmethod(lambda text, kind: deterministic),
    )
    extractor = DocumentExtractor()

    first = extractor.extract_json("[PAGE 1]\npreuve OCR", "releve")
    first["data"]["banque"] = "valeur modifiée"
    second = extractor.extract_json("[PAGE 1]\npreuve OCR", "releve")

    assert second["data"]["banque"] == "CIH Bank"
    assert extractor._extract_json_cached.cache_info().hits == 1


def _load_ocr_engine_without_models(monkeypatch, module_name):
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


def test_onnx_cuda_dlls_are_preloaded_before_gpu_configuration(monkeypatch):
    calls = []
    fake_ort = SimpleNamespace(
        get_available_providers=lambda: [
            "CUDAExecutionProvider",
            "CPUExecutionProvider",
        ],
        preload_dlls=lambda **kwargs: calls.append(kwargs),
    )
    monkeypatch.setitem(sys.modules, "onnxruntime", fake_ort)
    module = _load_ocr_engine_without_models(monkeypatch, "ocr_cuda_preload")

    config = module._onnx_engine_config()

    assert calls == [{"directory": ""}]
    assert config["device_type"] == "gpu"
    assert config["providers"][0] == "CUDAExecutionProvider"


def test_onnx_cuda_preload_failure_falls_back_to_cpu(monkeypatch):
    def fail_preload(**kwargs):
        raise OSError("DLL introuvable")

    fake_ort = SimpleNamespace(
        get_available_providers=lambda: [
            "CUDAExecutionProvider",
            "CPUExecutionProvider",
        ],
        preload_dlls=fail_preload,
    )
    monkeypatch.setitem(sys.modules, "onnxruntime", fake_ort)
    module = _load_ocr_engine_without_models(monkeypatch, "ocr_cuda_fallback")

    config = module._onnx_engine_config()

    assert config == {
        "device_type": "cpu",
        "providers": ["CPUExecutionProvider"],
    }


def test_cnie_uses_one_color_pass_when_evidence_is_sufficient(monkeypatch):
    module = _load_ocr_engine_without_models(monkeypatch, "ocr_color_fast_path")
    calls = []
    engine = module.OCREngine.__new__(module.OCREngine)
    engine.reader = SimpleNamespace(predict=lambda image: calls.append(image) or [{
        "rec_texts": [
            "CARTE NATIONALE D IDENTITE ROYAUME DU MAROC",
            "ADRESSE 10 RUE EXEMPLE CASABLANCA AA123456 VALABLE 01/01/2030",
        ],
        "rec_scores": [0.99, 0.99],
        "rec_polys": [None, None],
    }])
    engine.preprocessor = SimpleNamespace(
        preprocess=lambda image: pytest.fail("La binarisation doit être évitée")
    )
    image = __import__("numpy").zeros((400, 700, 3), dtype="uint8")

    lines = engine.image_to_text(image, document_type="carte_identite")

    assert len(calls) == 1
    assert any("CARTE NATIONALE" in line["text"] for line in lines)


def test_cnie_keeps_binarized_fallback_when_color_is_poor(monkeypatch):
    module = _load_ocr_engine_without_models(monkeypatch, "ocr_color_fallback")
    calls = []

    def predict(image):
        calls.append(image)
        texts = ["illisible"] if len(calls) == 1 else ["CARTE NATIONALE", "AA123456"]
        return [{
            "rec_texts": texts,
            "rec_scores": [0.90] * len(texts),
            "rec_polys": [None] * len(texts),
        }]

    engine = module.OCREngine.__new__(module.OCREngine)
    engine.reader = SimpleNamespace(predict=predict)
    engine.preprocessor = SimpleNamespace(preprocess=lambda image: image)
    image = __import__("numpy").zeros((400, 700, 3), dtype="uint8")

    lines = engine.image_to_text(image, document_type="carte_identite")

    assert len(calls) == 2
    assert any("AA123456" in line["text"] for line in lines)


def test_cnie_rejects_incomplete_color_evidence(monkeypatch):
    module = _load_ocr_engine_without_models(monkeypatch, "ocr_color_incomplete")
    lines = [
        {"text": "CARTE NATIONALE D IDENTITE ROYAUME DU MAROC", "confidence": 0.99},
        {"text": "ADRESSE 10 RUE EXEMPLE CASABLANCA", "confidence": 0.99},
    ]

    assert module.OCREngine._identity_color_is_sufficient(lines) is False


def test_bulletin_combines_upper_and_lower_in_one_bounded_reread(monkeypatch):
    module = _load_ocr_engine_without_models(monkeypatch, "ocr_bulletin_combined")
    calls = []
    engine = module.OCREngine.__new__(module.OCREngine)
    engine.reader = SimpleNamespace(predict=lambda image: calls.append(image.shape) or [])
    image = __import__("numpy").zeros((1005, 735, 3), dtype="uint8")

    engine._read_bulletin_regions(
        image,
        missing_markers=("PERIODE", "NET A PAYER"),
    )

    assert len(calls) == 1
    assert max(calls[0][:2]) <= 1600


def test_hybrid_reader_downsizes_large_raster_by_document_type():
    from ocr.hybrid_reader import HybridReader

    captured = {}
    page = SimpleNamespace(
        rect=SimpleNamespace(width=4000, height=3000),
        get_pixmap=lambda **kwargs: captured.update(kwargs) or SimpleNamespace(),
    )
    reader = HybridReader(max_ocr_side=2000)

    reader._render_for_ocr(
        SimpleNamespace(is_pdf=False), page, document_type="carte_identite"
    )

    assert captured["matrix"].a == pytest.approx(0.4)
    assert captured["matrix"].d == pytest.approx(0.4)


def test_hybrid_reader_removes_only_blank_outer_margins():
    from ocr.hybrid_reader import HybridReader

    numpy = __import__("numpy")
    image = numpy.full((200, 300, 3), 255, dtype="uint8")
    image[50:150, 80:220] = 0

    cropped = HybridReader._trim_blank_margins(image, padding=10)

    assert cropped.shape == (120, 160, 3)
    assert int(cropped[10, 10, 0]) == 0


def test_statement_credit_reread_only_when_an_incoming_amount_is_missing(monkeypatch):
    module = _load_ocr_engine_without_models(monkeypatch, "ocr_credit_gate")

    def box(x0, y0, x1, y1):
        return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]

    base_lines = [
        {"text": "DEBIT", "bbox": box(550, 90, 630, 110)},
        {"text": "CREDIT", "bbox": box(760, 90, 850, 110)},
        {"text": "VIREMENT RECU DE CLIENT", "bbox": box(180, 190, 500, 210)},
    ]

    assert module.OCREngine._statement_credit_pass_needed(base_lines, 1000) is True

    complete_lines = base_lines + [
        {"text": "500,00", "bbox": box(770, 190, 840, 210)},
    ]
    assert module.OCREngine._statement_credit_pass_needed(complete_lines, 1000) is False


def test_ocr_cache_uses_file_content_not_temporary_name(tmp_path, monkeypatch):
    from database import audit

    monkeypatch.setattr(
        audit,
        "settings",
        SimpleNamespace(database_path=tmp_path / "audit.db"),
    )
    from workflows import document_workflow as workflow

    with workflow._ocr_pages_cache_lock:
        workflow._ocr_pages_cache.clear()
    calls = []

    class FakeOCRAgent:
        def execute_pages(self, path, document_type=None):
            calls.append((path, document_type))
            return [{"page": 1, "text": "Texte identique"}]

    monkeypatch.setattr(workflow, "_ocr_agent", FakeOCRAgent())
    first = tmp_path / "premier.pdf"
    second = tmp_path / "second.pdf"
    first.write_bytes(b"contenu documentaire identique")
    second.write_bytes(b"contenu documentaire identique")

    first_result = workflow.ocr_node({
        "pdf_path": str(first), "document_type": "bulletin"
    })
    second_result = workflow.ocr_node({
        "pdf_path": str(second), "document_type": "bulletin"
    })

    assert len(calls) == 1
    assert first_result == second_result
