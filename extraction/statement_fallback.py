"""Secours déterministe pour les en-têtes et soldes des relevés marocains."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
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
    date_pattern = r"\d{1,2}(?:\s*[./-]\s*|\s+)\d{1,2}(?:\s*[./-]\s*|\s+)\d{2,4}"
    amount_pattern = r"\d{1,3}(?:[ .]\d{3})*[,.]\d{2}"
    # Capture bornée et non gourmande : sur un OCR aplati en une seule
    # ligne, ``^.*$`` engloberait toute la page et prendrait le dernier
    # montant du relevé au lieu du solde recherché.
    match = re.search(
        rf"{label}(?:\s+AU)?\s*(?:[:|]\s*)?"
        rf"(?:(?:{date_pattern})\s*(?:[:|]\s*)?)?"
        rf"(?:{amount_pattern})",
        text,
        re.I,
    )
    if not match:
        match = re.search(rf"{label}.{{0,80}}?(?:{amount_pattern})", text, re.I)
    if not match:
        return None
    quote = " ".join(match.group(0).split())
    date_match = re.search(date_pattern, quote)
    amounts = re.findall(r"(?<!\d)(\d{1,3}(?:[ .]\d{3})+|\d+)[,.](\d{2})(?!\d)", quote)
    if not amounts:
        return None
    whole, decimals = amounts[-1]
    value = _amount(f"{whole},{decimals}")
    if value is None:
        return None
    return match, date_match.group(0) if date_match else "", value


def _put(data, name, value, text, match, confidence=0.82, force=False):
    if force or _missing(data, name):
        data[name] = {
            "value": value,
            "confidence": confidence,
            "source": {
                "page": _page_at(text, match.start()),
                "quote": " ".join(match.group(0).split()),
            },
        }


def _normalized_date(raw: str) -> Optional[str]:
    parts = re.fullmatch(
        r"\s*(\d{1,2})(?:\s*[./-]\s*|\s+)(\d{1,2})"
        r"(?:\s*[./-]\s*|\s+)(\d{2,4})\s*",
        str(raw or ""),
    )
    if not parts:
        return None
    day, month, year = (int(value) for value in parts.groups())
    if year < 100:
        year += 2000
    try:
        return datetime(year, month, day).strftime("%d/%m/%Y")
    except ValueError:
        return None


def _header_match(text: str, pattern: str) -> Optional[re.Match]:
    # Certains moteurs OCR conservent des retours à la ligne dans un même
    # bloc d'en-tête. DOTALL permet aux expressions bornées de suivre ces
    # blocs sans dépendre de la mise en page exacte.
    return re.search(pattern, text, re.I | re.S)


def _fill_populaire_header(result: Dict[str, Any], text: str) -> None:
    """Secours pour les relevés Banque Populaire dont l'OCR aplatit l'en-tête."""
    agency = _header_match(
        text,
        r"\bAgence\s*\|?\s*:?\s*\|?\s*([A-ZÀ-Ü][A-ZÀ-Ü '\-]{2,40}?)(?=\s*\||\s+MME?\b|\s+M(?:LLE)?\b|\s+Adresse\b)",
    )
    if agency:
        _put(result, "agence", " ".join(agency.group(1).split()), text, agency, 0.86)

    holder = _header_match(
        text,
        r"\b(?:MME|MLLE|MR|M)\s+([A-ZÀ-Ü][A-ZÀ-Ü'\-]{1,30})"
        r"\s+([A-ZÀ-Ü][A-ZÀ-Ü'\-]{1,30})(?=\s+Adresse\b|\s+T[ée]l\b|\s+EXTRAIT\b)",
    )
    if holder:
        _put(result, "nom", holder.group(1).strip(), text, holder, 0.78)
        _put(result, "prenom", holder.group(2).strip(), text, holder, 0.78)

    address = _header_match(
        text,
        r"\bAdresse\s*\|?\s*:?\s*\|?\s*(.{8,160}?)(?=\s+T[ée]l\s*\||\s+EXTRAIT\s+DE\s+COMPTE)",
    )
    if address:
        _put(
            result,
            "titulaire_adresse",
            " ".join(address.group(1).replace("|", " ").split()),
            text,
            address,
            0.82,
        )

    account_table = _header_match(
        text,
        r"NUMERO\s+DE\s+COMPTE\s+PRINCIPAL.{0,80}?"
        r"190\s*\|\s*780\s*\|\s*([0-9 |]{10,35}?)\s*\|\s*76\b",
    )
    if account_table:
        account_number = re.sub(r"\D", "", account_table.group(1))
        if 12 <= len(account_number) <= 24:
            _put(result, "numero_compte", account_number, text, account_table, 0.84)
        _put(result, "banque", "Banque Populaire", text, account_table, 0.80)


def fill_missing_statement_fields(data: Dict[str, Any], ocr_text: str) -> Dict[str, Any]:
    """Complète les champs usuels sans dépendre d'une mise en page bancaire."""
    result = dict(data)
    initial = None
    initial_label = ""
    for label in (
        r"SOLDE\s+(?:DE\s+)?D[ÉE]PART",
        r"SOLDE\s+INITIAL",
        r"ANCIEN(?:\s+SOLDE)?",
        r"SOLDE\s+PR[ÉE]C[ÉE]DENT",
    ):
        initial = _balance_line(ocr_text, label)
        if initial:
            initial_label = label
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
            normalized_initial_date = _normalized_date(date_value)
            if normalized_initial_date:
                initial_date = datetime.strptime(normalized_initial_date, "%d/%m/%Y")
                # « ancien/précédent » désigne le solde de clôture de la
                # veille ; un libellé « solde initial » peut déjà porter la
                # première date de la période.
                is_previous_balance = bool(
                    re.search(r"ANCIEN|PR[ÉE]C[ÉE]DENT", initial_label, re.I)
                )
                first_day = (
                    initial_date + timedelta(days=1) if is_previous_balance else initial_date
                ).strftime("%d/%m/%Y")
                _put(result, "periode_debut", first_day, ocr_text, match, confidence=0.76)
    if final:
        match, date_value, amount = final
        _put(result, "solde_final", amount, ocr_text, match)
        if date_value:
            normalized_final_date = _normalized_date(date_value)
            if normalized_final_date:
                _put(result, "periode_fin", normalized_final_date, ocr_text, match)

    statement_at = re.search(
        r"(?:EXTRAIT|RELEV[ÉE])\s+DE\s+COMPTE\s+AU\s*\|?\s*"
        r"(\d{1,2}(?:\s*[./-]\s*|\s+)\d{1,2}(?:\s*[./-]\s*|\s+)\d{2,4})",
        ocr_text,
        re.I,
    )
    if statement_at:
        normalized = _normalized_date(statement_at.group(1))
        if normalized:
            # Cette date d'en-tête est une preuve plus forte que la date de
            # l'ancien solde ou qu'une date d'opération choisie par le LLM.
            _put(result, "periode_fin", normalized, ocr_text, statement_at, 0.92, force=True)
            if _missing(result, "periode_debut"):
                statement_date = datetime.strptime(normalized, "%d/%m/%Y")
                first_day = statement_date.replace(day=1).strftime("%d/%m/%Y")
                _put(result, "periode_debut", first_day, ocr_text, statement_at, 0.70)

    period = re.search(
        r"\bDu\s+(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})\s+Au\s+"
        r"(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})\b",
        ocr_text,
        re.I,
    )
    if period:
        _put(result, "periode_debut", period.group(1), ocr_text, period, 0.94, force=True)
        _put(result, "periode_fin", period.group(2), ocr_text, period, 0.94, force=True)

    account = re.search(r"\bCompte\s*:\s*([0-9 ]{8,32})", ocr_text, re.I)
    if account:
        _put(result, "numero_compte", re.sub(r"\s+", "", account.group(1)), ocr_text, account)

    # Un RIB marocain n'est pas un IBAN : le champ iban reste vide sans
    # libellé IBAN explicite.
    iban = re.search(r"\bIBAN\s*:\s*([A-Z]{2}[0-9A-Z ]{13,34})", ocr_text, re.I)
    if iban:
        _put(result, "iban", re.sub(r"\s+", "", iban.group(1)), ocr_text, iban)

    _fill_populaire_header(result, ocr_text)

    return result
