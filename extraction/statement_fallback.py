"""Secours déterministe pour les en-têtes et soldes des relevés marocains."""

from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple


def _missing(data: Dict[str, Any], name: str) -> bool:
    current = data.get(name)
    return current is None or (
        isinstance(current, dict) and current.get("value") in (None, "")
    )


def _page_at(text: str, position: int) -> int:
    markers = list(re.finditer(r"\[PAGE\s+(\d+)\]", text[:position], re.I))
    return int(markers[-1].group(1)) if markers else 1


def _amount(raw: str) -> Optional[float]:
    cleaned = raw.replace("\u00a0", " ").replace(" ", "")
    if "," in cleaned and "." in cleaned:
        decimal = "," if cleaned.rfind(",") > cleaned.rfind(".") else "."
        cleaned = cleaned.replace("." if decimal == "," else ",", "").replace(decimal, ".")
    else:
        cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _balance_line(text: str, label: str) -> Optional[Tuple[re.Match, str, float]]:
    match = re.search(
        rf"(?im)^.*{label}.*$",
        text,
    )
    if not match:
        # Compatibilité avec un OCR aplati sur une seule ligne.
        match = re.search(rf"{label}.{{0,100}}", text, re.I)
    if not match:
        return None
    quote = " ".join(match.group(0).split())
    date_match = re.search(r"\b(\d{2}[./-]\d{2}[./-]\d{4})\b", quote)
    amounts = re.findall(r"(?<!\d)(\d{1,3}(?:[ .]\d{3})+|\d+)[,.](\d{2})(?!\d)", quote)
    if not amounts:
        return None
    whole, decimals = amounts[-1]
    value = _amount(f"{whole},{decimals}")
    if value is None:
        return None
    return match, date_match.group(1) if date_match else "", value


def _put(data, name, value, text, match, confidence=0.82):
    if _missing(data, name):
        data[name] = {
            "value": value,
            "confidence": confidence,
            "source": {
                "page": _page_at(text, match.start()),
                "quote": " ".join(match.group(0).split()),
            },
        }


def fill_missing_statement_fields(data: Dict[str, Any], ocr_text: str) -> Dict[str, Any]:
    """Complète les champs usuels sans dépendre d'une mise en page bancaire."""
    result = dict(data)
    initial = None
    for label in (
        r"SOLDE\s+(?:DE\s+)?D[ÉE]PART",
        r"SOLDE\s+INITIAL",
        r"ANCIEN\s+SOLDE",
        r"SOLDE\s+PR[ÉE]C[ÉE]DENT",
    ):
        initial = _balance_line(ocr_text, label)
        if initial:
            break

    final = None
    for label in (r"NOUVEAU\s+SOLDE", r"SOLDE\s+FINAL", r"(?<!ANCIEN\s)SOLDE\s+AU"):
        final = _balance_line(ocr_text, label)
        if final:
            break

    if initial:
        match, date_value, amount = initial
        _put(result, "solde_initial", amount, ocr_text, match)
        if date_value:
            _put(result, "periode_debut", date_value, ocr_text, match)
    if final:
        match, date_value, amount = final
        _put(result, "solde_final", amount, ocr_text, match)
        if date_value:
            _put(result, "periode_fin", date_value, ocr_text, match)

    period = re.search(
        r"\bDu\s+(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})\s+Au\s+"
        r"(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})\b",
        ocr_text,
        re.I,
    )
    if period:
        _put(result, "periode_debut", period.group(1), ocr_text, period)
        _put(result, "periode_fin", period.group(2), ocr_text, period)

    account = re.search(r"\bCompte\s*:\s*([0-9 ]{8,32})", ocr_text, re.I)
    if account:
        _put(result, "numero_compte", re.sub(r"\s+", "", account.group(1)), ocr_text, account)

    rib = re.search(r"\bRIB\s*:\s*([0-9 ]{12,32})", ocr_text, re.I)
    if rib:
        _put(result, "iban", re.sub(r"\s+", "", rib.group(1)), ocr_text, rib)

    return result
