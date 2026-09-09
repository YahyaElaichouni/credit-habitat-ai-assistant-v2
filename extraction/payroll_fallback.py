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


def _put_match(
    data: Dict[str, Any], name: str, text: str, match: Optional[re.Match],
    group: int = 1, *, replace: bool = False,
) -> None:
    if match and (replace or _missing(data, name)):
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
        "total_retenues": r"(?:TOTAL\s+(?:DES\s+)?RETENUES?|TOTAL\s+COT(?:ISATIONS?|EETONS))",
        "salaire_net": r"(?:SALAIRE\s+NET|NET\s*[ÀA]?\s*P(?:AYER|ATER|KYER)|NET\s+PAY[EÉ])",
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
            r"BULLETIN\s+DE\s+PAIE\s*\|?\s*"
            r"((?:janvier|f[ée]vrier|mars|avril|mai|juin|juillet|ao[ûu]t|"
            r"septembre|octobre|novembre|d[ée]cembre)\s+\d{4})"
            r"\s*\|?\s*P[ée]riode\b",
        )
    if not period:
        # En-tête aplati : « BULLETIN DE PAIE | Période Janvier 2026 ».
        period = _search(
            text,
            r"BULLETIN\s+DE\s+PAIE\s*\|?\s*P[ée]riode\s*\|?\s*"
            r"((?:janvier|f[ée]vrier|mars|avril|mai|juin|juillet|ao[ûu]t|"
            r"septembre|octobre|novembre|d[ée]cembre)\s+(?:19|20)\d{2})",
        )
    if not period:
        period = _search(
            text,
            r"P[ée]riode\s+du\s*:?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\s*(?:\|\s*)?au\s*:?\s*"
            r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        )
    # Une correspondance structurelle sûre prime sur la sortie LLM : elle
    # fournit une citation réellement présente, vérifiable par provenance.py.
    _put_match(result, "periode", text, period, replace=True)
    # OCR très bruité : « P : 010524 ». On conserve seulement le mois/année
    # porté par la date de début, sans tenter de corriger une date de fin douteuse.
    if _missing(result, "periode"):
        compact_period = _search(text, r"(?:BULLETIN\s*DE\s*PAIE.{0,30}?)\bP\s*:\s*(\d{2})(\d{2})(\d{2})\b")
        if compact_period:
            day, month, year = map(int, compact_period.groups())
            if 1 <= day <= 31 and 1 <= month <= 12:
                result["periode"] = _field(
                    f"{month:02d}/20{year:02d}", text, compact_period, confidence=0.58
                )
    _put_match(result, "compte_bancaire", text, _search(text, r"Compte\s+bancaire.{0,80}?\b(\d{20,30})\b"))
    if _missing(result, "compte_bancaire"):
        _put_match(result, "compte_bancaire", text, _search(text, r"\bRIB\s*:?[ ]*([A-Z0-9 ]{8,32})"))

    _put_match(
        result, "date_embauche", text,
        _search(text, r"Date\s+(?:d['’]?\s*)?embauche\s*(?:\||:)?\s*(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})"),
        replace=True,
    )
    if _missing(result, "date_embauche"):
        dates_row = _search(
            text,
            r"Date\s+naissance\s*\|\s*Date\s+(?:d['’]?\s*)?embauche\s*\|\s*"
            r"Date\s+anciennet[ée].{0,180}?\|\s*"
            r"(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})\s*\|\s*"
            r"(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})\s*\|\s*"
            r"(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})",
        )
        _put_match(result, "date_embauche", text, dates_row, group=2, replace=True)
    # Les en-têtes de colonnes peuvent être suivis de Fonction/Situation,
    # puis seulement de la ligne naissance | embauche | ancienneté. Cette
    # preuve déterministe remplace aussi une valeur LLM dotée d'une fausse
    # citation, afin qu'elle ne soit pas annulée lors du contrôle de provenance.
    aligned_dates = _search(
        text,
        r"Date\s+naissance\s*\|\s*Date\s+(?:d['’]?\s*)?embauche\s*\|\s*"
        r"Date\s+anciennet[ée]\s*\|?.{0,220}?"
        r"(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})\s*\|\s*"
        r"(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})\s*\|\s*"
        r"(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})",
    )
    if aligned_dates and _valid_employment_date(aligned_dates.group(2)):
        result["date_embauche"] = _field(
            aligned_dates.group(2), text, aligned_dates, confidence=0.72
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
        interleaved_employee = _search(
            text,
            r"EMPLOY[ÉE]E?\s+[^|]{2,100}\|\s*"
            r"(\d{2,8}[A-Z]?)\s+([A-ZÀ-ÖØ-Þ][A-ZÀ-ÖØ-Þ'' -]{1,40})\s+"
            r"([A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÖØ-öø-ÿ' -]{1,40}?)"
            r"(?=\s+N[°º](?:\s|$)|\s*\|)",
        )
        if interleaved_employee:
            if _missing(result, "matricule"):
                result["matricule"] = _field(interleaved_employee.group(1), text, interleaved_employee)
            if _missing(result, "nom"):
                result["nom"] = _field(interleaved_employee.group(2).strip().upper(), text, interleaved_employee)
            if _missing(result, "prenom"):
                result["prenom"] = _field(interleaved_employee.group(3).strip().title(), text, interleaved_employee)

    if _missing(result, "matricule"):
        table_matricule = _search(
            text,
            r"Matricule\s*\|\s*Niveau\s*\|\s*Coef{1,2}icient\s*\|\s*Indice"
            r".{0,120}?\b(\d{2,8}[A-Z]?)\b",
        )
        _put_match(result, "matricule", text, table_matricule)
    if _missing(result, "matricule"):
        noisy_matricule = _search(text, r"Matr(?:i)?c(?:u)?le\s*:?[ ]*(\d{2,7}[nIl])\b")
        if noisy_matricule:
            normalized = re.sub(r"[nIl]$", "1", noisy_matricule.group(1))
            result["matricule"] = _field(normalized, text, noisy_matricule, confidence=0.52)

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
    if _missing(result, "poste"):
        occupied_job = _search(
            text,
            r"Emploi\s+occup[ée]\s*(?:\||:)?\s*([A-ZÀ-ÖØ-Þ][A-ZÀ-ÖØ-Þ /&'\-]{2,60})"
            r"(?=\s*\|\s*(?:D[ée]partement|Qualification|N\s*[°º]?\s*SIRET)|"
            r"\s+(?:D[ée]partement|Qualification|N\s*[°º]?\s*SIRET)\b)",
        )
        _put_match(result, "poste", text, occupied_job)
    if _missing(result, "poste"):
        split_job = _search(
            text,
            r"Emploi\s+occup[ée]\s*\|\s*D[ée]partement\s*\|\s*"
            r"([A-ZÀ-ÖØ-Þ][A-ZÀ-ÖØ-Þ /&'\-]{2,60})"
            r"(?=\s*\|\s*Qualification\b)",
        )
        _put_match(result, "poste", text, split_job)
    if _missing(result, "poste"):
        noisy_job = _search(
            text,
            r"Fonction\s+(.{3,55}?)(?=\s+N[°º]\s*CIN|\s+Balaire\s+Horaire)",
        )
        if noisy_job:
            candidate = " ".join(noisy_job.group(1).split())
            candidate = re.sub(r"^.*\|\s*", "", candidate)
            if 3 <= len(candidate) <= 55:
                result["poste"] = _field(candidate, text, noisy_job, confidence=0.48)

    # Le nom de l'organisme est accepté seulement dans l'en-tête immédiat.
    header = _search(text, r"\[PAGE\s+1\]\s+([A-Z][A-Z0-9&.-]{2,20})\s+(?:Di\s*rection|Direction)")
    if header and _missing(result, "employeur"):
        result["employeur"] = _field(header.group(1), text, header)

    base = _labelled_amount(text, r"(?:SALA(?:IRE|INE)|BALAIRE)\s+(?:PRINCIPAL|DE\s+BASE|HORAIRE)")
    if base and _missing(result, "salaire_base"):
        result["salaire_base"] = _field(base[0], text, base[1])

    _fill_pay_totals(result, text)

    if _missing(result, "salaire_net"):
        net_block = _search(text, r"NET\s*[ÀA]?\s*P(?:AYER|ATER|KYER).{0,500}$")
        if net_block:
            amounts = re.findall(r"(?<!\d)(\d{1,3}(?:[ .]\d{3})+|\d+)[,.](\d{2})(?!\d)", net_block.group(0))
            if amounts:
                whole, decimals = amounts[-1]
                net_value = _amount(f"{whole},{decimals}")
                if net_value is not None:
                    result["salaire_net"] = _field(net_value, text, net_block, confidence=0.62)

    if _missing(result, "nom") or _missing(result, "prenom"):
        identity_block = _search(
            text,
            r"\b[MF]\s*\|\s*((?:EL\s+|AL\s+)?[A-ZÀ-ÖØ-Þ]{2,25}(?:\s+[A-ZÀ-ÖØ-Þ]{2,25}){1,3}?)"
            r"\s+[A-ZÀ-ÖØ-Þ]{3,20}\s+(?=(?:Acq\w*|Reste|Repos|Cong[ée]s)\b)",
        )
        if identity_block:
            words = identity_block.group(1).split()
            if len(words) >= 3 and words[0] in {"EL", "AL"}:
                surname, given = " ".join(words[:2]), " ".join(words[2:])
            else:
                surname, given = " ".join(words[:-1]), words[-1]
            if _missing(result, "nom"):
                result["nom"] = _field(surname, text, identity_block, confidence=0.66)
            if _missing(result, "prenom"):
                result["prenom"] = _field(given.title(), text, identity_block, confidence=0.66)

    # Certains moteurs suppriment l'espace entre le patronyme et le prénom.
    # La séparation n'est faite que lorsqu'un prénom marocain courant forme un
    # suffixe exact ; sinon le champ reste vide pour éviter toute invention.
    if _missing(result, "nom") or _missing(result, "prenom"):
        joined_identity = _search(text, r"\b[MF]\s*\|\s*(EL\s+|AL\s+)?([A-ZÀ-ÖØ-Þ]{7,35})(?=\s+\d{1,4}\s+LOT\b)")
        if joined_identity:
            joined = joined_identity.group(2)
            given_names = ("MOHAMED", "MOHAMMED", "HAMZA", "YOUNESS", "YAHYA", "AHMED", "AMINE", "OMAR", "ALI")
            given = next((name for name in given_names if joined.endswith(name) and len(joined) > len(name) + 1), None)
            if given:
                prefix = (joined_identity.group(1) or "") + joined[:-len(given)]
                if _missing(result, "nom"):
                    result["nom"] = _field(prefix.strip(), text, joined_identity, confidence=0.50)
                if _missing(result, "prenom"):
                    result["prenom"] = _field(given.title(), text, joined_identity, confidence=0.50)

    if _missing(result, "devise") and any(
        not _missing(result, name) for name in ("salaire_base", "salaire_brut", "salaire_net")
    ):
        salary_label = _search(text, r"SALAIRE\s+(?:PRINCIPAL|BRUT|NET)")
        if salary_label:
            result["devise"] = _field("MAD", text, salary_label, confidence=0.70)

    return result
