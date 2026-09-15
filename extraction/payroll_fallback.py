"""Secours déterministe pour les bulletins de paie français et marocains.

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


def _value(data: Dict[str, Any], name: str) -> Any:
    current = data.get(name)
    return current.get("value") if isinstance(current, dict) else current


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


def _signed_amount(raw: str) -> Optional[float]:
    """Convertit un montant tout en conservant le signe des lignes de paie."""
    negative = str(raw).strip().startswith("-")
    value = _amount(str(raw).lstrip("- "))
    if value is None:
        return None
    return -value if negative else value


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


def _last_amount_on_labelled_line(
    text: str, label: str
) -> Optional[Tuple[float, re.Match]]:
    """Retourne le montant final d'une ligne de tableau de paie.

    Une ligne comme ``Salaire de base | heures | taux | à payer`` doit fournir
    la dernière cellule, et non le nombre d'heures placé juste après le libellé.
    """
    match = re.search(rf"(?im)^\s*{label}\b[^\r\n]*$", text)
    if not match:
        return None
    raw_amounts = re.findall(
        r"-?\s*\d+(?:[ \u00a0]\d{3})*(?:[,.]\d{1,4})", match.group(0)
    )
    if not raw_amounts:
        return None
    value = _signed_amount(raw_amounts[-1])
    return (abs(value), match) if value is not None else None


def _salary_base_row(text: str) -> Optional[Tuple[float, re.Match]]:
    """Lit la cellule finale de Salaire de base, même sur un OCR aplati."""
    salary_label = (
        r"(?:(?:SALA(?:IRE|INE)|BALAIRE)\s+"
        r"(?:PRINCIPAL|DE\s+BASE|BASE\s+HORAIRE|HORAIRE(?:\s+ANAPEC)?)|"
        r"TRAITEMENT\s+DE\s+BASE(?:\s+INDICIAIRE)?)"
    )
    result = _last_amount_on_labelled_line(
        text, salary_label
    )
    if result:
        return result

    flattened = " ".join(text.split())
    paired_codes = re.search(
        rf"(?:\b\d{{1,3}}\s+)?\d{{2,4}}\s+{salary_label}\b\s*"
        r"(-?\s*\d[\d ]*(?:[,.]\d{1,2}))"
        r"(?=\s+\d{1,3}\s+\d{2,4}\s+[A-Za-zÀ-ÖØ-öø-ÿ])",
        flattened,
        re.I,
    )
    if paired_codes:
        value = _signed_amount(paired_codes.group(1))
        if value is not None:
            return abs(value), paired_codes

    # Tableaux avec numéro/rubrique : le prochain code marque sans ambiguïté
    # la fin de la ligne, quelle que soit la banque ou l'entreprise.
    coded = re.search(
        rf"(?:\b\d{{1,5}}\s*\|\s*)?{salary_label}\b.*?"
        r"(?=\s+\d{1,5}\s*\|\s*[A-Za-zÀ-ÖØ-öø-ÿ])",
        flattened,
        re.I,
    )
    if coded:
        amounts = re.findall(
            r"-?\s*\d+(?:[ \u00a0]\d{3})*(?:[,.]\d{1,4})", coded.group(0)
        )
        if amounts:
            value = _signed_amount(amounts[-1])
            if value is not None:
                return abs(value), coded

    match = re.search(
        rf"{salary_label}\b"
        r".*?(?=\s+(?:Prime\b|Majoration\b|Heures?\s+suppl[ée]mentaires?\b|"
        r"Jour\s+f[ée]ri[ée]\b|Montant\s+anciennet[ée]\b|Indemnit[ée]\b|"
        r"Cplt\b|Compl[ée]ment\b|Contr\s+Patr\b|Ret\s+Cong[ée]\b|"
        r"Paiem?t\s+Cong[ée]\b|SALAIRE\s+BRUT\b|TOTAL\s+BRUT\b))",
        flattened,
        re.I,
    )
    if not match:
        return None
    amounts = re.findall(
        r"-?\s*\d+(?:[ \u00a0]\d{3})*(?:[,.]\d{1,4})", match.group(0)
    )
    if not amounts:
        return None
    value = _signed_amount(amounts[-1])
    return (abs(value), match) if value is not None else None


def _fill_pay_totals(data: Dict[str, Any], text: str) -> None:
    labels = {
        "salaire_brut": r"(?:TOTAL\s+BRUT|SALAIRE\s+BRUT(?!\s+IMPOSABLE))",
        "brut_imposable": r"(?:SALAIRE\s+BRUT\s+IMPOSABLE|BRUT\s+IMPOSABLE)",
        "total_retenues": (
            r"(?:TOTAL\s+(?:DES\s+)?RETENUES?|"
            r"TOTAL\s+(?:DES\s+)?COT(?:ISATIONS?|EETONS)"
            r"(?:\s+ET\s+CONTR[IÍ]BUTIONS)?)"
        ),
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


def _fill_split_withholdings(data: Dict[str, Any], text: str) -> None:
    """Additionne les totaux déductible et non déductible lorsqu'ils sont séparés."""
    block = _search(
        text,
        r"Total\s+des\s+retenues\s+d[ée]ductibles\s*(?:\||:)?\s*"
        r"(-?\s*\d[\d .]*(?:[,.]\d{1,2})).{0,120}?"
        r"Total\s+des\s+retenues\s+non\s+d[ée]ductibles\s*(?:\||:)?\s*"
        r"(-?\s*\d[\d .]*(?:[,.]\d{1,2}))",
    )
    if not block:
        return
    deductible = _amount(block.group(1))
    non_deductible = _amount(block.group(2))
    if deductible is None or non_deductible is None:
        return
    total = round(deductible + non_deductible, 2)
    current = _value(data, "total_retenues")
    if current in (None, deductible, non_deductible):
        data["total_retenues"] = _field(total, text, block, confidence=0.82)


def _fill_gross_from_earning_rows(data: Dict[str, Any], ocr_text: str) -> None:
    """Reconstitue le brut quand l'OCR perd la cellule du total.

    Certains bulletins français conservent parfaitement chaque ligne de gain
    mais omettent le montant visuellement aligné avec « SALAIRE BRUT MENS ».
    Dans ce seul cas, le brut est la somme vérifiable des lignes situées entre
    « Salaire de base » et ce total.
    """
    if not _missing(data, "salaire_brut"):
        return
    block = re.search(
        r"(?is)Salaire\s+de\s+Base\b.*?SALAIRE\s+BRUT(?:\s+MENS)?\b",
        ocr_text,
    )
    if not block:
        return

    earning_labels = re.compile(
        r"(?:Salaire\s+de\s+Base|Prime(?:\s+d['’]Anciennet[ée]|\s+Permanence)?\b|"
        r"Majoration\b|Heures?\s+suppl[ée]mentaires?\b|"
        r"Cplt\b|Compl[ée]ment\b|"
        r"Contr\s+Patr\s+Sant[ée]|Ret\s+Cong[ée]\s+Pay[ée]|"
        r"Paiem?t\s+Cong[ée]\s+Pay[ée])",
        re.I,
    )
    amount_pattern = r"-?\s*\d+(?:[ \u00a0]\d{3})*(?:[,.]\d{1,2})"
    components = []
    earning_block = block.group(0)
    labels = list(earning_labels.finditer(earning_block))
    for index, label_match in enumerate(labels):
        next_start = labels[index + 1].start() if index + 1 < len(labels) else len(earning_block)
        row = earning_block[label_match.start():next_start]
        amounts = re.findall(amount_pattern, row)
        if amounts:
            value = _signed_amount(amounts[-1])
            if value is not None:
                components.append(value)

    if len(components) >= 3 and any(value > 0 for value in components):
        gross = round(sum(components), 2)
        if gross > 0:
            data["salaire_brut"] = _field(gross, ocr_text, block, confidence=0.70)


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

    labelled_identity = _search(
        text,
        r"(?:Nom\s*(?:&|et)\s*Pr[ée]nom|Nom\s+complet)\s*:?[ ]*\|?[ ]*"
        r"([A-ZÀ-ÖØ-Þ][A-ZÀ-ÖØ-Þ'\-]{1,34})\s+"
        r"([A-ZÀ-ÖØ-Þ][A-ZÀ-ÖØ-Þ'\-]{1,34}(?:\s+[A-ZÀ-ÖØ-Þ][A-ZÀ-ÖØ-Þ'\-]{1,34})?)"
        r"(?=\s*(?:\||Adresse\b|Fonction\b|D[ée]partement\b))",
    )
    if labelled_identity:
        result["nom"] = _field(labelled_identity.group(1).upper(), text, labelled_identity, 0.90)
        result["prenom"] = _field(labelled_identity.group(2).title(), text, labelled_identity, 0.90)

    # Civilité + identité, fréquente sur les bulletins français :
    # « Mlle ASLAN DELPHINE ». Corrige aussi une sortie LLM qui place les
    # deux mots dans nom et laisse prenom vide.
    titled_identity = _search(
        text,
        r"\b(?:Madame|Monsieur|M(?:I|L|l)le|Mme|Mr|M)\s+"
        r"([A-ZÀ-ÖØ-Þ'\-]{2,35})\s+([A-ZÀ-ÖØ-Þ'\-]{2,35})"
        r"(?=\s+\d+\s*(?:rue|avenue|av\b|place|route|lot|hay)|"
        r"\s+[A-Z]{3}\s+\d{5}\b)",
    )
    if titled_identity:
        current_nom = result.get("nom")
        current_nom_value = current_nom.get("value") if isinstance(current_nom, dict) else current_nom
        combined = " ".join(
            (titled_identity.group(1), titled_identity.group(2))
        ).casefold()
        if _missing(result, "nom") or str(current_nom_value or "").strip().casefold() == combined:
            result["nom"] = _field(titled_identity.group(1).upper(), text, titled_identity, 0.88)
        if _missing(result, "prenom"):
            result["prenom"] = _field(titled_identity.group(2).title(), text, titled_identity, 0.88)

    if _missing(result, "nom") or _missing(result, "prenom"):
        long_titled_identity = _search(
            text,
            r"\b(?:Madame|Monsieur|Mme|Mr)\s+"
            r"([A-ZÀ-ÖØ-Þ'\-]{2,35}(?:\s+[A-ZÀ-ÖØ-Þ'\-]{2,35}){2,4})"
            r"(?=\s+(?:Statut\s+professionnel|Niveau\s*:|"
            r"\d+\s*(?:rue|avenue|av\b|bd\b|boulevard)))",
        )
        if long_titled_identity:
            identity_words = long_titled_identity.group(1).split()
            # Sur ce format multi-prénoms, le patronyme est imprimé en dernier.
            surname = identity_words[-1]
            given_names = " ".join(identity_words[:-1])
            if _missing(result, "nom"):
                result["nom"] = _field(surname.upper(), text, long_titled_identity, 0.66)
            if _missing(result, "prenom"):
                result["prenom"] = _field(given_names.title(), text, long_titled_identity, 0.66)
    exact_period = _search(
        text,
        r"P[ée]riode(?:\s+de\s+paie)?\s+du\s*:?\s*"
        r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\s*(?:\|\s*)?au\s*:?\s*"
        r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
    )
    period = _search(
        text,
        r"(?:Bulletin\s+de\s+paie\s+(?:P[ée]riode(?:\s+de\s+paie)?\s*:?\s*)?|"
        r"P[ée]riode(?:\s+de\s+paie)?\s*:?\s*)"
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
            r"P[ée]riode(?:\s+de\s+paie)?\s+du\s*:?\s*"
            r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\s*(?:\|\s*)?au\s*:?\s*"
            r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        )
    # Une correspondance structurelle sûre prime sur la sortie LLM : elle
    # fournit une citation réellement présente, vérifiable par provenance.py.
    _put_match(result, "periode", text, period, replace=True)
    if exact_period:
        result["periode"] = _field(
            f"{exact_period.group(1)} au {exact_period.group(2)}",
            text,
            exact_period,
            confidence=0.92,
        )
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
        _search(
            text,
            r"Date\s+(?:(?:d['’]?\s*)?embauche|d['’]?\s*entr[ée]e)"
            r"\s*(?:\||:)?\s*(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})",
        ),
        replace=True,
    )
    if _missing(result, "date_embauche"):
        _put_match(
            result,
            "date_embauche",
            text,
            _search(
                text,
                r"\bEntr[ée]e\s*:?[ ]*(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})",
            ),
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
    if _missing(result, "date_embauche"):
        entry_row = _search(
            text,
            r"Date\s+(?:d['’]?\s*)?Entr[ée]e\s*\|\s*Date\s+Anciennet[ée]"
            r".{0,260}?(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})\s*\|\s*"
            r"(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})",
        )
        _put_match(result, "date_embauche", text, entry_row, group=1, replace=True)
    # Les en-têtes de colonnes peuvent être suivis de Fonction/Situation,
    # puis seulement de la ligne naissance | embauche | ancienneté. Cette
    # preuve déterministe remplace aussi une valeur LLM dotée d'une fausse
    # citation, afin qu'elle ne soit pas annulée lors du contrôle de provenance.
    aligned_dates = _search(
        text,
        r"Date\s+(?:de\s+)?naissance\s*\|\s*Date\s+(?:d['’]?\s*)?embauche\s*\|\s*"
        r"Date\s+anciennet[ée]\s*\|?.{0,220}?"
        r"(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})\s*\|\s*"
        r"(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})\s*\|\s*"
        r"(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})",
    )
    if aligned_dates and _valid_employment_date(aligned_dates.group(2)):
        result["date_embauche"] = _field(
            aligned_dates.group(2), text, aligned_dates, confidence=0.72
        )
    if _missing(result, "date_embauche"):
        birth_hire_row = _search(
            text,
            r"Date\s+(?:de\s+)?Naissance\s*\|\s*Date\s+(?:d['’]?\s*)?embauche"
            r"\s*\|\s*Anciennet[ée]\s*\|\s*Fonction.{0,160}?"
            r"(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})\s*\|\s*"
            r"(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})",
        )
        if birth_hire_row and _valid_employment_date(birth_hire_row.group(2)):
            result["date_embauche"] = _field(
                birth_hire_row.group(2), text, birth_hire_row, confidence=0.78
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
        _put_match(
            result,
            "matricule",
            text,
            _search(text, r"\bMATRICULE\s*:?[ ]*(\d{2,10}[A-Z]?)\b"),
        )
    employee_grid = _search(
        text,
        r"Fonction\s*\|\s*D[ée]partement\s*\|\s*Type\s+Salaire\s*\|\s*Matricule"
        r"\s+([^|]{2,60}?)\s*\|\s*[^|]*\|\s*[^|]*\|\s*(\d{2,10}[A-Z]?)"
        r"(?=\s+Date\s+(?:d['’]?\s*)?Entr[ée]e|\s*$)",
    )
    if employee_grid:
        if _missing(result, "poste"):
            result["poste"] = _field(employee_grid.group(1).strip(), text, employee_grid, 0.82)
        if _missing(result, "matricule"):
            result["matricule"] = _field(employee_grid.group(2), text, employee_grid, 0.82)
    public_service_grid = _search(
        text,
        r"MATRICULE\s*\|\s*SERVICE\s*\|\s*EMPLOI\s+"
        r"([A-Z0-9._-]{3,20})\s*\|\s*([^|]{0,40})\|\s*([^|]{2,60})",
    )
    if public_service_grid:
        if _missing(result, "matricule"):
            result["matricule"] = _field(public_service_grid.group(1), text, public_service_grid, 0.76)
        if _missing(result, "poste"):
            result["poste"] = _field(public_service_grid.group(3).strip(), text, public_service_grid, 0.72)
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
                if len(words) >= 3 and words[0].upper() in {"EL", "AL"}:
                    surname = " ".join(words[:2]).upper()
                    given = " ".join(words[2:]).title()
                else:
                    surname = words[0].upper()
                    given = " ".join(words[1:]).title()
                if _missing(result, "nom"):
                    result["nom"] = _field(surname, text, labelled_employee)
                if _missing(result, "prenom"):
                    result["prenom"] = _field(given, text, labelled_employee)

    _put_match(
        result, "poste", text,
        _search(text, r"\b\d{3,5}\s+([A-ZÀ-ÖØ-Þ][A-ZÀ-ÖØ-Þ ]{5,70}?)\s+\d{3,8}[A-Z]?\s+[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÖØ-öø-ÿ' -]+\s+Classe\b"),
    )
    if _missing(result, "poste"):
        _put_match(
            result,
            "poste",
            text,
            _search(text, r"\bEMPLOI\s*:?[ ]*([^|]{2,70}?)(?=\s*\|)"),
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
        function_row = _search(
            text,
            r"Fonction\s*\|\s*D[ée]partement\s*\|\s*Type\s+Salaire\s*\|\s*Matricule"
            r"\s+([^|]{2,60}?)\s*\|",
        )
        _put_match(result, "poste", text, function_row)
    if _missing(result, "poste"):
        function_with_family = _search(
            text,
            r"Fonction\s*\|\s*Situation\s+familiale.*?"
            r"N[°º].{0,15}?C.{0,3}?I.{0,3}?N.{0,3}?\s+"
            r"([^|]{2,60}?)\s*\|",
        )
        _put_match(result, "poste", text, function_with_family)
    if _missing(result, "poste"):
        dated_function_row = _search(
            text,
            r"Date\s+(?:de\s+)?Naissance\s*\|\s*Date\s+(?:d['’]?\s*)?embauche"
            r".*?\|\s*Fonction\s+\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\s*\|\s*"
            r"\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\s*\|(?:\s*\|)?\s*"
            r"([^|]{3,60}?)(?=\s+\d{1,5}\s*\|)",
        )
        _put_match(result, "poste", text, dated_function_row)
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
    if _missing(result, "employeur"):
        legal_employer = _search(
            text,
            r"\b((?:SAS|SA|SARL|S\.A\.|S\.A\.R\.L\.)\s+[A-ZÀ-ÖØ-öø-ÿ0-9&.' -]{2,70}?)"
            r"(?=\s*\||\s+\d{1,4}\s*(?:rue|avenue|av\b))",
        )
        _put_match(result, "employeur", text, legal_employer)
    if _missing(result, "employeur"):
        company_employee_grid = _search(
            text,
            r"SOCI[ÉE]T[ÉE]\s*\|\s*EMPLOY[ÉE]\s+"
            r"([^|]{2,80}?)\s*\|\s*\d{2,10}[A-Z]?\s+[A-ZÀ-ÖØ-öø-ÿ]",
        )
        _put_match(result, "employeur", text, company_employee_grid)
    if _missing(result, "employeur"):
        named_center = _search(
            text,
            r"\b([A-ZÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ&.' -]{2,70}"
            r"(?:Contact\s+Center|Budget\s+g[ée]n[ée]ral))\b",
        )
        _put_match(result, "employeur", text, named_center)

    base_row = _salary_base_row(ocr_text)
    if base_row:
        # La ligne structurée est plus fiable que la première cellule choisie
        # par le LLM (souvent le nombre d'heures, par ex. 151,67).
        result["salaire_base"] = _field(base_row[0], ocr_text, base_row[1], confidence=0.88)
    else:
        base = _labelled_amount(
            text, r"(?:SALA(?:IRE|INE)|BALAIRE)\s+(?:PRINCIPAL|DE\s+BASE|HORAIRE)"
        )
        if base and _missing(result, "salaire_base"):
            result["salaire_base"] = _field(base[0], text, base[1])

    _fill_pay_totals(result, text)
    _fill_split_withholdings(result, text)
    _fill_gross_from_earning_rows(result, ocr_text)

    if _missing(result, "salaire_net"):
        net_block = _search(text, r"NET\s*[ÀA]?\s*P(?:AYER|ATER|KYER).{0,500}$")
        if net_block:
            amounts = re.findall(r"(?<!\d)(\d{1,3}(?:[ .]\d{3})+|\d+)[,.](\d{2})(?!\d)", net_block.group(0))
            if amounts:
                whole, decimals = amounts[-1]
                net_value = _amount(f"{whole},{decimals}")
                if net_value is not None:
                    result["salaire_net"] = _field(net_value, text, net_block, confidence=0.62)

    euro = _search(
        text,
        r"(?:\bNet\s+pay[ée]\s*:?[ ]*\d[\d .]*[,.]\d{2}\s+euros?\b|"
        r"\d[\d .]*[,.]\d{2}\s*€)",
    )
    if euro:
        result["devise"] = _field("EUR", text, euro, confidence=0.98)

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
        explicit_mad = _search(text, r"\b(?:MAD|DHS?|DIRHAMS?\s+MAROCAINS?)\b")
        france = _search(text, r"\b(?:FRA|FRANCE|SIRET|URSSAF|service-public\.fr|euros?)\b")
        morocco = _search(
            text,
            r"\b(?:MAROC|RABAT|CASABLANCA|TANGER|AGADIR|TAZA|CNSS|AMO|RCAR|CNRA)\b",
        )
        if explicit_mad:
            result["devise"] = _field("MAD", text, explicit_mad, confidence=0.96)
        elif france:
            result["devise"] = _field("EUR", text, france, confidence=0.76)
        elif morocco:
            result["devise"] = _field("MAD", text, morocco, confidence=0.72)

    return result
