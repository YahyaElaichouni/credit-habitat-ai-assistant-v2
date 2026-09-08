"""Secours déterministe pour les bulletins de paie marocains.

Le LLM reste l'extracteur principal. Ce module complète uniquement ses champs
absents à partir de libellés explicitement présents dans l'OCR. Les confiances
restent volontairement inférieures au seuil de confirmation humaine.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from typing import Any, Dict, Iterable, Optional, Tuple


FALLBACK_CONFIDENCE = 0.78


def _plain(text: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(char)
    )


def _page_number(text: str, position: int) -> int:
    pages = list(re.finditer(r"\[PAGE\s+(\d+)\]", text[:position], re.I))
    return int(pages[-1].group(1)) if pages else 1


def _field(value: Any, text: str, match: re.Match, confidence: float = FALLBACK_CONFIDENCE) -> Dict[str, Any]:
    quote = " ".join(match.group(0).split())
    return {
        "value": value,
        "confidence": confidence,
        "source": {"page": _page_number(text, match.start()), "quote": quote},
    }


def _missing(data: Dict[str, Any], name: str) -> bool:
    current = data.get(name)
    return current is None or (isinstance(current, dict) and current.get("value") in (None, ""))


def _clear_invalid_field(data: Dict[str, Any], name: str) -> None:
    """Supprime une hallucination afin que le secours OCR puisse la remplacer."""
    current = data.get(name)
    if isinstance(current, dict):
        data[name] = {"value": None, "confidence": 0.0, "source": None}
    elif current is not None:
        data[name] = None


def _valid_employment_date(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    raw = value.strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y", "%d-%m-%y", "%d.%m.%y", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(raw, fmt).date()
            return date(1940, 1, 1) <= parsed <= date.today()
        except ValueError:
            continue
    return False


def _valid_pay_period(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    raw = " ".join(value.strip().split())
    month = r"(?:janvier|f[ée]vrier|mars|avril|mai|juin|juillet|ao[ûu]t|septembre|octobre|novembre|d[ée]cembre)"
    return bool(
        re.fullmatch(r"(?:0?[1-9]|1[0-2])\s*/\s*(?:19|20)\d{2}", raw, re.I)
        or re.fullmatch(rf"{month}\s+(?:19|20)\d{{2}}", raw, re.I)
        or re.fullmatch(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\s+au\s+\d{1,2}[/-]\d{1,2}[/-]\d{2,4}", raw, re.I)
    )


def _amount(raw: str) -> Optional[float]:
    value = raw.replace("\u00a0", " ").replace(" ", "")
    if "," in value and "." in value:
        decimal = "," if value.rfind(",") > value.rfind(".") else "."
        value = value.replace("." if decimal == "," else ",", "").replace(decimal, ".")
    elif "," in value:
        value = value.replace(",", ".")
    try:
        return abs(float(value))
    except ValueError:
        return None


def _search(text: str, pattern: str, flags: int = re.I) -> Optional[re.Match]:
    return re.search(pattern, text, flags)


def _put_match(data: Dict[str, Any], name: str, text: str, match: Optional[re.Match], group: int = 1) -> None:
    if match and _missing(data, name):
        data[name] = _field(" ".join(match.group(group).split()), text, match)


def _labelled_amount(text: str, label: str) -> Optional[Tuple[float, re.Match]]:
    # Compatible avec la reconstruction spatiale « LIBELLE | montant ».
    pattern = rf"{label}\s*(?:\||:|-)?\s*(-?\s*\d[\d .]*(?:[,.]\d{{1,2}}))"
    match = _search(text, pattern)
    if not match:
        return None
    value = _amount(match.group(1))
    return (value, match) if value is not None else None


def _fill_pay_totals(data: Dict[str, Any], text: str) -> None:
    labels = {
        "salaire_brut": r"(?:TOTAL\s+BRUT|SALAIRE\s+BRUT(?!\s+IMPOSABLE))",
        "brut_imposable": r"(?:SALAIRE\s+BRUT\s+IMPOSABLE|BRUT\s+IMPOSABLE)",
        "total_retenues": r"(?:TOTAL\s+(?:DES\s+)?RETENUES?|TOTAL\s+COTISATIONS?)",
        "salaire_net": r"(?:SALAIRE\s+NET|NET\s+[ÀA]\s+PAYER|NET\s+PAY[EÉ])",
    }
    # Certains OCR aplatissent les quatre libellés puis les quatre nombres.
    # On sécurise l'attribution par l'identité comptable brut - retenues = net.
    block = _search(
        text,
        r"SALAIRE\s+BRUT(?:\s*\|\s*|\s+)BRUT\s+IMPOSABLE"
        r"(?:\s*\|\s*|\s+)TOTAL\s+RETENUES?"
        r"(?:\s*\|\s*|\s+)SALAIRE\s+NET\s+"
        r"((?:-?\s*\d[\d ]*(?:[,.]\d{1,2})(?:\s*\|\s*|\s+)){3}"
        r"-?\s*\d[\d ]*(?:[,.]\d{1,2}))",
    )
    if block:
        values = [_amount(item) for item in re.findall(r"-?\s*\d[\d ]*(?:[,.]\d{1,2})", block.group(1))]
        if len(values) == 4 and not any(value is None for value in values):
            amounts = [float(value) for value in values]
            retenues, net = amounts[-2], amounts[-1]
            gross_candidates = amounts[:2]
            brut = min(gross_candidates, key=lambda value: abs((value - retenues) - net))
            imposable = gross_candidates[1] if brut == gross_candidates[0] else gross_candidates[0]
            inferred = {
                "salaire_brut": brut,
                "brut_imposable": imposable,
                "total_retenues": retenues,
                "salaire_net": net,
            }
            for name, value in inferred.items():
                if _missing(data, name):
                    data[name] = _field(value, text, block, confidence=0.74)

    # Format normal : chaque montant suit directement son libellé.
    found = {name: _labelled_amount(text, label) for name, label in labels.items()}
    for name, result in found.items():
        if result and _missing(data, name):
            value, match = result
            data[name] = _field(value, text, match)


def fill_missing_payroll_fields(data: Dict[str, Any], ocr_text: str) -> Dict[str, Any]:
    """Complète uniquement les champs bulletin absents, sans écraser le LLM."""

    result = dict(data)
    current_date = result.get("date_embauche")
    current_date_value = current_date.get("value") if isinstance(current_date, dict) else current_date
    if current_date_value is not None and not _valid_employment_date(current_date_value):
        _clear_invalid_field(result, "date_embauche")

    current_period = result.get("periode")
    current_period_value = current_period.get("value") if isinstance(current_period, dict) else current_period
    if current_period_value is not None and not _valid_pay_period(current_period_value):
        _clear_invalid_field(result, "periode")

    text = " ".join(ocr_text.replace("\n", " ").split())
    period = _search(
        text,
        r"(?:Bulletin\s+de\s+paie\s+(?:P[ée]riode\s*:?\s*)?|P[ée]riode\s*:?\s*)"
        r"((?:\d{1,2}\s*/\s*\d{4})|(?:janvier|f[ée]vrier|mars|avril|mai|juin|"
        r"juillet|ao[ûu]t|septembre|octobre|novembre|d[ée]cembre)\s+\d{4})",
    )
    if not period:
        period = _search(
            text,
            r"P[ée]riode\s+du\s+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\s+au\s+"
            r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        )
    _put_match(result, "periode", text, period)
    _put_match(result, "compte_bancaire", text, _search(text, r"Compte\s+bancaire.{0,80}?\b(\d{20,30})\b"))
    if _missing(result, "compte_bancaire"):
        _put_match(result, "compte_bancaire", text, _search(text, r"\bRIB\s*:?[ ]*([A-Z0-9 ]{8,32})"))

    _put_match(
        result, "date_embauche", text,
        _search(text, r"Date\s+(?:d['’]?\s*)?embauche\s*(?:\||:)?\s*(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})"),
    )

    # Format fréquent : matricule, nom du salarié, puis « Classe ».
    employee = _search(text, r"\b([0-9]{3,8}[A-Z]?)\s+([A-ZÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ' -]{2,60}?)\s+Classe\b")
    if employee:
        if _missing(result, "matricule"):
            result["matricule"] = _field(employee.group(1), text, employee)
        words = employee.group(2).strip().split()
        if len(words) >= 2:
            if _missing(result, "prenom"):
                result["prenom"] = _field(words[0].title(), text, employee)
            if _missing(result, "nom"):
                result["nom"] = _field(" ".join(words[1:]).upper(), text, employee)

    if _missing(result, "matricule") or _missing(result, "nom"):
        labelled_employee = _search(
            text,
            r"(?:EMPLOY[ÉE]|Matricule)\s*:?[ ]*(\d{2,8}[A-Z]?)"
            r"(?:\s+[MF])?\s+([A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÖØ-öø-ÿ' -]{3,55}?)"
            r"(?=\s+(?:Casablanca|Rabat|Tanger|Adresse|Portable|Email|\d{1,4}\s+LOT)\b|\s*\|)",
        )
        if labelled_employee:
            if _missing(result, "matricule"):
                result["matricule"] = _field(labelled_employee.group(1), text, labelled_employee)
            words = labelled_employee.group(2).strip().split()
            if len(words) >= 2:
                if _missing(result, "nom"):
                    result["nom"] = _field(words[0].upper(), text, labelled_employee)
                if _missing(result, "prenom"):
                    result["prenom"] = _field(" ".join(words[1:]).title(), text, labelled_employee)

    _put_match(
        result, "poste", text,
        _search(text, r"\b\d{3,5}\s+([A-ZÀ-ÖØ-Þ][A-ZÀ-ÖØ-Þ ]{5,70}?)\s+\d{3,8}[A-Z]?\s+[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÖØ-öø-ÿ' -]+\s+Classe\b"),
    )

    # Le nom de l'organisme est accepté seulement dans l'en-tête immédiat.
    header = _search(text, r"\[PAGE\s+1\]\s+([A-Z][A-Z0-9&.-]{2,20})\s+(?:Di\s*rection|Direction)")
    if header and _missing(result, "employeur"):
        result["employeur"] = _field(header.group(1), text, header)

    base = _labelled_amount(text, r"SALAIRE\s+(?:PRINCIPAL|DE\s+BASE|HORAIRE)")
    if base and _missing(result, "salaire_base"):
        result["salaire_base"] = _field(base[0], text, base[1])

    _fill_pay_totals(result, text)

    if _missing(result, "devise") and any(
        not _missing(result, name) for name in ("salaire_base", "salaire_brut", "salaire_net")
    ):
        salary_label = _search(text, r"SALAIRE\s+(?:PRINCIPAL|BRUT|NET)")
        if salary_label:
            result["devise"] = _field("MAD", text, salary_label, confidence=0.70)

    return result
