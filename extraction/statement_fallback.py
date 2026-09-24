"""Secours déterministe pour les en-têtes et soldes des relevés marocains."""

from __future__ import annotations

import re
import unicodedata
import calendar
from collections import Counter
from datetime import date, datetime, timedelta
from typing import Any, Dict, Optional, Tuple


STATEMENT_TARGET_FIELDS = (
    "banque",
    "periode_debut",
    "periode_fin",
    "transactions",
    "charge_mensuelle_credits",
    "revenus_complementaires",
)


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


def _fold(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text).strip().casefold()


def _ocr_lines(text: str) -> list[Dict[str, Any]]:
    """Conserve les lignes, pages et citations originales de l'OCR."""
    lines = []
    page = 1
    for match in re.finditer(r"[^\r\n]+", text):
        raw = match.group(0).strip()
        if not raw:
            continue
        marker = re.fullmatch(r"\[PAGE\s+(\d+)\]", raw, re.I)
        if marker:
            page = int(marker.group(1))
            continue
        lines.append({
            "raw": raw,
            "folded": _fold(raw),
            "page": page,
            "start": match.start(),
        })
    return lines


def _line_field(value: Any, line: Dict[str, Any], confidence: float) -> Dict[str, Any]:
    return {
        "value": value,
        "confidence": confidence,
        "source": {
            "page": line["page"],
            "quote": " ".join(line["raw"].split()),
        },
    }


_FULL_DATE_RE = re.compile(
    r"(?<!\d)(\d{1,2})\s*[./-]\s*(\d{1,2})\s*[./-]\s*((?:19|20)?\d{2})(?!\d)"
)
_SHORT_DATE_RE = re.compile(
    r"(?<!\d)(\d{1,2})\s*[./-]\s*(\d{1,2})(?!\s*[./-]\s*\d)"
)
_AMOUNT_RE = re.compile(
    r"(?<!\d)(?:\d{1,3}(?:[ .\u00a0]\d{3})+|\d+)[,.]\d{2}(?!\d)"
)


def _date_value(day: int, month: int, year: int) -> Optional[date]:
    if year < 100:
        year += 2000 if year < 70 else 1900
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _statement_anchor(text: str) -> Tuple[Optional[int], Optional[int]]:
    """Trouve une année fiable et, si possible, le mois du solde précédent."""
    preferred = re.search(
        r"(?i)(?:solde\s+(?:de\s+)?d[ée]part|ancien\s+solde|relev[ée].{0,30}?au)"
        r".{0,50}?(\d{1,2})\s*[./-]\s*(\d{1,2})\s*[./-]\s*((?:19|20)\d{2})",
        text,
        re.S,
    )
    if preferred:
        return int(preferred.group(3)), int(preferred.group(2))
    years = [int(match.group(3)) for match in _FULL_DATE_RE.finditer(text)]
    return (Counter(years).most_common(1)[0][0], None) if years else (None, None)


def _parse_statement_date(
    raw: Any,
    default_year: Optional[int],
    anchor_month: Optional[int] = None,
) -> Optional[date]:
    value = str(raw or "")
    full = _FULL_DATE_RE.search(value)
    if full:
        return _date_value(*(int(part) for part in full.groups()))
    short = _SHORT_DATE_RE.search(value)
    if not short or default_year is None:
        return None
    day, month = int(short.group(1)), int(short.group(2))
    year = default_year
    # Passage décembre -> janvier après un solde précédent daté du 31/12.
    if anchor_month == 12 and month == 1:
        year += 1
    elif anchor_month == 1 and month == 12:
        year -= 1
    return _date_value(day, month, year)


def _transaction_date_lines(
    result: Dict[str, Any],
    text: str,
) -> list[Tuple[date, Dict[str, Any]]]:
    """Dates prouvées des opérations, sans dépendre d'une banque précise."""
    lines = _ocr_lines(text)
    year, anchor_month = _statement_anchor(text)
    candidates: list[Tuple[date, Dict[str, Any]]] = []

    # Les transactions structurées du LLM sont utilisées seulement pour leur
    # date ; la citation doit être retrouvée dans une ligne OCR.
    for item in result.get("transactions") or []:
        if not isinstance(item, dict):
            continue
        parsed = _parse_statement_date(item.get("date"), year, anchor_month)
        quote = _fold(item.get("quote"))
        if parsed is None or not quote:
            continue
        evidence = next((line for line in lines if quote in line["folded"]), None)
        if evidence:
            candidates.append((parsed, evidence))

    # Secours OCR : une vraie ligne d'opération commence par une date, possède
    # un libellé alphabétique et au moins un montant décimal. Les soldes et
    # totaux sont exclus explicitement.
    for line in lines:
        folded = line["folded"]
        if any(word in folded for word in (
            "solde depart", "solde initial", "ancien solde", "nouveau solde",
            "solde final", "total mouvement", "total des mouvements",
        )):
            continue
        if not _AMOUNT_RE.search(line["raw"]) or not re.search(r"[A-Za-zÀ-ÖØ-öø-ÿ]{3}", line["raw"]):
            continue
        # Les OCR de tableaux accolent parfois date opération et date valeur :
        # « 01/0901/09 ». La première date de la ligne reste la date opération.
        start = re.match(r"\s*(\d{1,2}\s*[./-]\s*\d{1,2}(?:\s*[./-]\s*\d{2,4})?)", line["raw"])
        if not start:
            continue
        parsed = _parse_statement_date(start.group(1), year, anchor_month)
        if parsed:
            candidates.append((parsed, line))

    unique = {}
    for parsed, line in candidates:
        unique.setdefault((parsed, line["page"], line["raw"]), (parsed, line))
    return list(unique.values())


def _fill_generic_period(result: Dict[str, Any], text: str) -> None:
    """Période explicite, puis couverture réelle des opérations en secours."""
    lines = _ocr_lines(text)
    for line in lines:
        if not re.search(
            r"(?:\bperiode\b|\breleve\s+du\b|^du\b|\bstatement\s+period\b|"
            r"\bperiod\s+from\b|^from\b)",
            line["folded"],
        ):
            continue
        dates = [
            _date_value(*(int(part) for part in match.groups()))
            for match in _FULL_DATE_RE.finditer(line["raw"])
        ]
        dates = [value for value in dates if value is not None]
        if len(dates) >= 2:
            result["periode_debut"] = _line_field(dates[0].strftime("%d/%m/%Y"), line, 0.95)
            result["periode_fin"] = _line_field(dates[1].strftime("%d/%m/%Y"), line, 0.95)
            return

    dated_lines = _transaction_date_lines(result, text)

    # Secours pour les OCR qui séparent la date, le libellé et le montant en
    # plusieurs lignes. Après l'en-tête des opérations, toute date JJ/MM est
    # une candidate ; les lignes de solde restent exclues.
    if len(dated_lines) < 2:
        year, anchor_month = _statement_anchor(text)
        lines = _ocr_lines(text)
        table_started = False
        relaxed = []
        for line in lines:
            folded = line["folded"]
            if any(marker in folded for marker in ("operation", "reference", "debit", "credit")):
                table_started = True
            if not table_started or "solde" in folded or "total" in folded:
                continue
            match = _FULL_DATE_RE.search(line["raw"]) or _SHORT_DATE_RE.search(line["raw"])
            if not match:
                continue
            parsed = _parse_statement_date(match.group(0), year, anchor_month)
            if parsed:
                relaxed.append((parsed, line))
        if len(relaxed) >= 2:
            dated_lines = relaxed

    # Relevé mensuel partiel (par exemple image 0001/0004) : « Solde départ
    # au 31/08 » suivi d'opérations de septembre prouve le début du mois mais
    # pas la dernière page. On propose alors les bornes du mois à faible
    # confiance, au lieu de laisser les champs vides ou de prendre le 12/09
    # comme fausse date de clôture.
    opening = re.search(
        r"(?i)solde\s+(?:de\s+)?d[ée]part\s+au.{0,100}?"
        r"(\d{1,2}\s*[./-]\s*\d{1,2}\s*[./-]\s*\d{2,4})",
        text,
        re.S,
    )
    if opening:
        opening_date = _parse_statement_date(opening.group(1), None)
        if opening_date:
            period_start = opening_date + timedelta(days=1)
            following = [item for item in dated_lines if item[0] >= period_start]
            if following and all(
                item[0].year == period_start.year and item[0].month == period_start.month
                for item in following
            ):
                evidence = next(
                    (line for line in _ocr_lines(text) if _fold(opening.group(0)) in line["folded"]),
                    None,
                )
                if evidence is None:
                    evidence = {
                        "raw": " ".join(opening.group(0).split()),
                        "page": _page_at(text, opening.start()),
                    }
                month_end = calendar.monthrange(period_start.year, period_start.month)[1]
                # Cette preuve déterministe est plus fiable qu'une période
                # proposée par le LLM à partir du solde précédent. Elle
                # corrige notamment 31/12/2019 -> janvier 2020 chez Attijari.
                result["periode_debut"] = _line_field(
                    period_start.strftime("%d/%m/%Y"), evidence, 0.66
                )
                result["periode_fin"] = _line_field(
                    period_start.replace(day=month_end).strftime("%d/%m/%Y"),
                    evidence,
                    0.58,
                )
                return

    if len(dated_lines) < 2:
        return
    first_date, first_line = min(dated_lines, key=lambda item: item[0])
    last_date, last_line = max(dated_lines, key=lambda item: item[0])
    # Il s'agit de la couverture observée, proposée sous le seuil de validation
    # automatique. Le client conserve donc la décision finale.
    if _missing(result, "periode_debut"):
        result["periode_debut"] = _line_field(first_date.strftime("%d/%m/%Y"), first_line, 0.68)
    if _missing(result, "periode_fin"):
        result["periode_fin"] = _line_field(last_date.strftime("%d/%m/%Y"), last_line, 0.68)


def _fill_generic_bank_name(result: Dict[str, Any], text: str) -> None:
    """Lit un nom bancaire dans l'en-tête sans catalogue d'établissements."""
    if not _missing(result, "banque"):
        return
    for line in _ocr_lines(text)[:20]:
        raw = line["raw"]
        match = re.search(
            r"\b([A-ZÀ-ÖØ-Þ][A-ZÀ-ÖØ-Þ0-9&.' -]{1,55}?\s+(?:BANK|BANQUE))\b",
            raw,
            re.I,
        )
        if match:
            candidate = " ".join(match.group(1).split()).strip(" |-:")
            result["banque"] = _line_field(candidate, line, 0.88)
            return


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
        _put(result, "banque", "Banque Populaire", text, account_table, 0.80)


def _fill_bank_name(result: Dict[str, Any], text: str) -> None:
    """Reconnaît les banques usuelles sans dépendre de la mise en page OCR."""
    if not _missing(result, "banque"):
        return
    bank_patterns = (
        (r"\bSOCI[ÉE]T[ÉE]\s+G[ÉE]N[ÉE]RALE\b", "Société Générale"),
        (r"\bCR[ÉE]DIT\s+AGRICOLE(?:\s+DU\s+MAROC)?\b", "Crédit Agricole du Maroc"),
        (r"\bBANQUE\s+POPULAIRE\b", "Banque Populaire"),
        (r"\bATTIJARIWAFA\s*BANK\b", "Attijariwafa bank"),
        (r"\b(?:BANK\s+OF\s+AFRICA|BMCE)\b", "Bank of Africa"),
        (r"\bBMCI\b", "BMCI"),
        (r"\bCIH(?:\s+BANK)?\b", "CIH Bank"),
    )
    # Le nom de la banque apparaît normalement dans l'en-tête. Une recherche
    # bornée évite de confondre une banque citée dans le libellé d'une opération.
    header = text[:1800]
    for pattern, name in bank_patterns:
        match = re.search(pattern, header, re.I)
        if match:
            _put(result, "banque", name, text, match, 0.94)
            return


def fill_missing_statement_fields(data: Dict[str, Any], ocr_text: str) -> Dict[str, Any]:
    """Complète uniquement les champs du relevé utiles à la simulation."""
    result = {
        key: value
        for key, value in data.items()
        if key == "document_type" or key in STATEMENT_TARGET_FIELDS
    }
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
                # veille. « Solde départ au » joue le même rôle sur plusieurs
                # relevés : la période commence alors le lendemain.
                is_previous_balance = bool(
                    re.search(r"ANCIEN|PR[ÉE]C[ÉE]DENT", initial_label, re.I)
                    or re.search(r"D[ÉE]PART\s+AU", match.group(0), re.I)
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
    _fill_bank_name(result, ocr_text)
    _fill_generic_bank_name(result, ocr_text)

    # Les libellés explicites restent prioritaires. Si le relevé n'affiche
    # aucune plage, on propose la couverture réellement observée dans les
    # opérations, avec une confiance imposant la validation humaine.
    _fill_generic_period(result, ocr_text)

    return {
        key: value
        for key, value in result.items()
        if key == "document_type" or key in STATEMENT_TARGET_FIELDS
    }

