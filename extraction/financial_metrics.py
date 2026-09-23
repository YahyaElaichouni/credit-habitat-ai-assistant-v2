"""Calculs déterministes proposés à la revue humaine, jamais décisions LLM."""
import re
import statistics
import unicodedata
import logging
from difflib import SequenceMatcher
from datetime import datetime, timedelta
import calendar
from pathlib import Path

CREDIT_CHARGE_PATTERN = (
    # « REGLEMENT CREDIT CARTE » est un libellé CIH de mouvement carte :
    # il peut se trouver dans la colonne CREDIT et ne prouve jamais, à lui
    # seul, une mensualité de prêt. Une charge exige donc un terme explicite
    # d'échéance, de prélèvement ou de remboursement.
    r"\b(?:mensualite|echeance|prelevement|remboursement)\w*"
    r".{0,35}\b(?:credit|pret|financement|habitat|logement|immobilier|auto|conso)\w*"
    r"|\b(?:credit|pret|financement)\w*.{0,35}"
    r"\b(?:mensualite|echeance|prelevement|habitat|logement|immobilier|auto|conso)\w*"
)
EXCLUDED_WORDS = ("assurance", "remboursement anticipe", "solde du pret")
# Le type ``credit`` vient de la colonne du relevé et constitue la règle
# principale. Ce motif compact sert uniquement de secours lorsque l'OCR/LLM
# omet le type : il couvre les familles lexicales, pas les libellés des banques.
# Ce motif n'est utilisé que lorsque la colonne CREDIT n'a pas été conservée
# par le modèle. Il doit donc prouver le sens entrant de l'opération. Le mot
# ``virement`` seul serait dangereux : il engloberait aussi les virements émis
# et les commissions de virement.
INCOMING_OPERATION_PATTERN = (
    r"\b(?:vir(?:ement)?|virt)\s*(?:-\s*)?(?:inst(?:antane)?)?\s+"
    r"(?:recu|de|en\s+votre\s+faveur)\b"
    r"|\brecept(?:ion)?\b.{0,24}\bvir(?:ement)?\b"
    r"|\breglement\s+credit\s+carte\b"
    r"|\b(?:vers(?:ement|t)?|depot|remise|encaissement|recette|allocation|"
    r"pension|loyer|prime|distribution|dividende|benefice)\w*\b"
    r"|\binteret\s+crediteur\b"
)
EXTRA_INCOME_EXCLUSION_REASONS = (
    (("solde initial", "solde depart", "solde precedent", "ancien solde", "nouveau solde", "solde au"),
     "solde du compte, pas un revenu"),
    (("salaire", "paie"), "salaire déjà pris en compte par le bulletin de paie"),
    (("mutuelle", "remboursement", "rembourse", "indemnite", "indemnisation", "restitution"),
     "remboursement ou indemnisation ponctuelle"),
    (("annulation", "contrepassation", "regularisation"), "correction bancaire ponctuelle"),
    (("commission", "frais", "retrait", "paiement"), "dépense ou opération technique"),
    (("total mouvement",), "total du relevé, pas une opération"),
)

# Libellés qui prouvent qu'un débit est une dépense courante/technique et non
# un revenu. Cette garde est surtout utile lorsque le LLM inverse les colonnes
# d'un tableau : le type extrait ne doit jamais suffire à transformer des frais
# ou un prélèvement en revenu complémentaire.
OUTGOING_OPERATION_PATTERN = (
    r"\b(?:frais|commission|retrait|paiement|achat|prelevement|cotisation|"
    r"assurance|taxe|timbre|droit|facture|recharge|virement\s+emis)\w*\b"
    r"|\bvers\b"
)

logger = logging.getLogger(__name__)


def _income_exclusion_reason(description):
    text = _norm(description)
    for keywords, reason in EXTRA_INCOME_EXCLUSION_REASONS:
        if any(keyword in text for keyword in keywords):
            return reason
    # Les scans CIH observés transforment parfois MUTUELLE en HUTOELLE.
    # On limite la tolérance à ces familles d'exclusion pour ne pas écarter
    # arbitrairement un virement légitime.
    words = re.findall(r"[a-z]{4,}", text)
    if any(_similar_word(word, ("mutuelle",), 0.70) for word in words):
        return "remboursement ou indemnisation ponctuelle"
    if any(
        _similar_word(word, ("remboursement", "indemnisation"), 0.76)
        for word in words
    ):
        return "remboursement ou indemnisation ponctuelle"
    return None


def _evidence_item(item, decision="retenu", reason=None):
    result = {
        key: item.get(key)
        for key in ("date", "description", "montant", "page", "quote")
    }
    result["decision"] = decision
    if reason:
        result["reason"] = reason
    return result


def _norm(value):
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", text).strip()


def _similar_word(word, targets, threshold=0.72):
    """Tolérance bornée aux substitutions OCR sur un seul mot."""
    cleaned = re.sub(r"[^a-z]", "", _norm(word))
    if not cleaned:
        return False
    return any(
        SequenceMatcher(None, cleaned, target).ratio() >= threshold
        for target in targets
    )


def _incoming_description(description):
    """Reconnaît un encaissement malgré les erreurs OCR courantes.

    Exemples réels CIH : VIRSNENT/VIRZHENT pour VIREMENT et
    RECD/RECO pour RECU. Deux indices sont exigés pour ne pas transformer
    un virement émis ou une commission en revenu.
    """
    text = _norm(description)
    # Les cellules PaddleOCR sont parfois séparées par ``|`` :
    # ``VIREMENT | RECU | DE ...`` doit être lu comme une seule phrase.
    semantic_text = re.sub(r"\s*\|\s*", " ", text)
    words = re.findall(r"[a-z]{2,}", semantic_text)
    has_sent = any(_similar_word(word, ("emis",), 0.72) for word in words)
    has_favour = any(
        _similar_word(word, ("faveur",), 0.67)
        for word in words
    )
    # Ces indices prouvent un virement sortant, y compris avec les erreurs
    # OCR observées ``FATEUR``/``FAVEER``. Ils sont évalués avant toute
    # tolérance positive afin de ne jamais compter un virement émis.
    if has_sent or has_favour:
        return False
    if re.search(INCOMING_OPERATION_PATTERN, semantic_text):
        return True
    # Après une perte partielle de cellules, ``RECU DE X`` ou même ``DE X``
    # peut être le seul libellé restant sur une ligne de la colonne crédit.
    if re.search(r"\b(?:recu|reception)\s+(?:de|du|des)\b", semantic_text):
        return True
    if re.search(
        r"(?:^|[^a-z])(?:de|du|des|do|dx|dk)\s+[a-z][a-z ]{2,}$",
        semantic_text,
    ):
        return True
    has_transfer = any(
        word == "virt" or _similar_word(word, ("virement", "versement"), 0.68)
        for word in words
    )
    has_received = any(
        _similar_word(word, ("recu", "reception", "versement"), 0.66)
        for word in words
    )
    has_source = any(word in {"de", "du", "des", "do", "dx", "dk"} for word in words)
    # Tester d'abord la paire VIREMENT + RECU évite que la similarité entre
    # « virement » et « paiement » ne rejette un vrai encaissement.
    if has_transfer and (has_received or has_source):
        return True
    if any(
        _similar_word(word, ("commission", "frais", "retrait", "paiement"), 0.68)
        for word in words
    ):
        return False
    return False


def _outgoing_description(description):
    """Reconnaît un débit même lorsque EMIS/FAVEUR est déformé par l'OCR."""
    text = _norm(description)
    if re.search(OUTGOING_OPERATION_PATTERN, text):
        return True
    words = re.findall(r"[a-z]{3,}", text)
    has_sent = any(_similar_word(word, ("emis",), 0.65) for word in words)
    has_favour = any(_similar_word(word, ("faveur",), 0.67) for word in words)
    # « en faveur de » prouve un mouvement sortant sur les relevés CIH,
    # même si VIREMENT ou EMIS a été partiellement perdu.
    return has_sent or has_favour


def _date(value, default_year=None):
    raw = re.sub(r"\s+", " ", str(value or "")).strip()
    short = re.fullmatch(
        r"(\d{1,2})(?:\s*[./-]\s*|\s+)(\d{1,2})", raw
    )
    if short and default_year:
        raw = f"{short.group(1)}/{short.group(2)}/{default_year}"
    spaced = re.fullmatch(r"(\d{1,2})\s+(\d{1,2})\s+(\d{2,4})", raw)
    if spaced:
        raw = "/".join(spaced.groups())
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
                "%d/%m/%y", "%d-%m-%y", "%d.%m.%y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            pass
    return None


def _statement_year(pages):
    """Déduit l'année de période pour les lignes qui n'affichent que JJ/MM."""
    text = " ".join(str(item.get("text") or "") for item in pages or [])
    period = re.search(
        r"(?i)(?:relev[ée]\s+)?du\s+\d{1,2}[./-]\d{1,2}[./-](\d{2,4})"
        r"\s+au\s+\d{1,2}[./-]\d{1,2}[./-](\d{2,4})",
        text,
    )
    if period:
        raw_year = int(period.group(2))
        return raw_year + 2000 if raw_year < 100 else raw_year

    # Beaucoup de relevés n'affichent pas « Du ... au ... » : l'année reste
    # néanmoins prouvée sur « Solde départ au », « ancien solde » ou dans une
    # date complète d'opération. Aucun nom de banque n'est nécessaire.
    anchor = re.search(
        r"(?i)(?:solde\s+(?:de\s+)?d[ée]part|ancien\s+solde|nouveau\s+solde|"
        r"relev[ée].{0,30}?au).{0,60}?\d{1,2}[./-]\d{1,2}[./-](\d{2,4})",
        text,
    )
    if anchor:
        raw_year = int(anchor.group(1))
        return raw_year + 2000 if raw_year < 100 else raw_year
    years = re.findall(r"(?<!\d)((?:19|20)\d{2})(?!\d)", text)
    if not years:
        return None
    raw_year = int(statistics.mode(years))
    return raw_year + 2000 if raw_year < 100 else raw_year


def _statement_anchor_dates(pages):
    """Dates complètes réellement visibles, utilisées pour dater JJ/MM."""
    text = " ".join(str(item.get("text") or "") for item in pages or [])
    pattern = re.compile(
        r"(?<!\d)\d{1,2}(?:\s*[./-]\s*|\s+)\d{1,2}"
        r"(?:\s*[./-]\s*|\s+)\d{2,4}(?!\d)"
    )
    anchors = []
    for match in pattern.finditer(text):
        parsed = _date(match.group(0))
        if parsed is not None:
            anchors.append(parsed)
    return anchors


def _transaction_date(value, pages):
    """Interprète une date d'opération, y compris au changement d'année."""
    parsed = _date(value)
    if parsed is not None:
        return parsed
    raw = re.sub(r"\s+", " ", str(value or "")).strip()
    short = re.fullmatch(
        r"(\d{1,2})(?:\s*[./-]\s*|\s+)(\d{1,2})", raw
    )
    if not short:
        return None
    day, month = (int(part) for part in short.groups())
    anchors = _statement_anchor_dates(pages)
    years = {anchor.year for anchor in anchors}
    if not years:
        fallback = _statement_year(pages)
        years = {fallback} if fallback else set()
    candidates = []
    for year in years:
        try:
            candidate = datetime(year, month, day).date()
        except ValueError:
            continue
        distance = min(
            (abs((candidate - anchor).days) for anchor in anchors),
            default=0,
        )
        candidates.append((distance, candidate))
    return min(candidates, key=lambda item: item[0])[1] if candidates else None


def _statement_month(pages):
    """Mois unique attendu uniquement si la période explicite le prouve."""
    text = " ".join(str(item.get("text") or "") for item in pages or [])
    period = re.search(
        r"(?i)(?:relev[ée]\s+)?du\s+"
        r"(\d{1,2}(?:\s*[./-]\s*|\s+)\d{1,2}(?:\s*[./-]\s*|\s+)\d{2,4})"
        r"\s+au\s+"
        r"(\d{1,2}(?:\s*[./-]\s*|\s+)\d{1,2}(?:\s*[./-]\s*|\s+)\d{2,4})",
        text,
    )
    if period:
        start, end = _date(period.group(1)), _date(period.group(2))
        if start and end and (start.year, start.month) == (end.year, end.month):
            return start.strftime("%Y-%m")
    # Relevés mensuels sans borne « Du/Au » (notamment CIH) : un solde de
    # départ daté du dernier jour du mois, suivi d'un vrai tableau comprenant
    # plusieurs opérations, prouve que la période commence le lendemain.
    # Cette ancre permet de corriger les mois OCR déformés comme 02/0102/80
    # alors que le document affiche un solde au 31/08/2023.
    opening = re.search(
        # « SOGOE DEPART » est une déformation observée de « SOLDE DEPART ».
        r"(?i)(?:solde|so[a-z]{2,4}e)\s+(?:de\s+)?d[ée]part\s+au.{0,80}?"
        r"(\d{1,2}\s*[./-]\s*\d{1,2}\s*[./-]\s*\d{2,4})",
        text,
        re.S,
    )
    if opening:
        opening_date = _date(opening.group(1))
        operation_count = len(re.findall(
            r"(?i)\b(?:virement|virenent|virem[a-z]*|virt|retrait|paiement|"
            r"commission|frais|recharge|prelevement)\b",
            text,
        ))
        if (
            opening_date
            and opening_date.day == calendar.monthrange(
                opening_date.year, opening_date.month
            )[1]
            and operation_count >= 3
        ):
            return (opening_date + timedelta(days=1)).strftime("%Y-%m")
    return None


def _force_statement_month(day, expected_month):
    """Rattache une date OCR au mois mensuel explicitement ancré."""
    if day is None or not expected_month:
        return day
    year, month = (int(part) for part in expected_month.split("-"))
    try:
        return day.replace(year=year, month=month)
    except ValueError:
        return None


def _amount(value):
    """Accepte les nombres JSON et les montants OCR simples (ex. -2 300,00)."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        cleaned = value.replace("\u00a0", "").replace(" ", "").replace(",", ".")
        cleaned = re.sub(r"[^0-9.+-]", "", cleaned)
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _page_map(pages):
    return {
        item.get("page"): _norm(item.get("text"))
        for item in pages or []
        if type(item.get("page")) is int
    }


def _transaction_evidence(item, pages):
    """Vérifie une transaction même si la citation du LLM est légèrement reformulée.

    L'OCR des tableaux insère parfois des espaces ou des séparateurs différents.
    On exige alors que la page contienne simultanément la date, le montant et au
    moins deux mots significatifs du libellé. Cette vérification reste fondée sur
    le document, sans faire confiance au drapeau produit par le modèle.
    """
    page = item.get("page")
    page_map = _page_map(pages)
    if type(page) is not int or page not in page_map:
        return None
    page_text = page_map[page]
    quote = item.get("quote")
    if isinstance(quote, str) and _norm(quote) and _norm(quote) in page_text:
        return quote.strip()

    day = _transaction_date(item.get("date"), pages)
    amount = _amount(item.get("montant"))
    description = _norm(item.get("description"))
    if day is None or amount is None or not description:
        return None
    date_forms = {
        day.strftime("%d/%m/%Y"), day.strftime("%d-%m-%Y"),
        day.strftime("%Y-%m-%d"), day.strftime("%d.%m.%Y"),
        day.strftime("%d/%m"), day.strftime("%d-%m"), day.strftime("%d.%m"),
    }
    amount_forms = {
        f"{abs(amount):.2f}", f"{abs(amount):.2f}".replace(".", ","),
        f"{abs(amount):,.2f}".replace(",", " "),
        f"{abs(amount):,.2f}".replace(",", " ").replace(".", ","),
    }
    tokens = [token for token in re.findall(r"[a-z]{3,}", description)
              if token not in {"avec", "dans", "pour", "carte"}]
    token_hits = sum(token in page_text for token in dict.fromkeys(tokens))
    if (any(_norm(value) in page_text for value in date_forms)
            and any(_norm(value) in page_text for value in amount_forms)
            and token_hits >= min(2, len(set(tokens)))):
        return str(quote or f"{item.get('date')} | {item.get('description')} | {item.get('montant')}").strip()
    return None


def _statement_activity_evidence(transactions, pages):
    """Retourne une preuve qu'un tableau d'opérations a réellement été lu."""
    for item in transactions or []:
        if not isinstance(item, dict):
            continue
        quote = _transaction_evidence(item, pages)
        if quote:
            return item.get("page"), quote
    for page_item in pages or []:
        raw = str(page_item.get("text") or "")
        marked = re.search(
            r"(?im)^.*\b(?:DEBIT|CREDIT)\s*:\s*"
            r"(?:\d{1,3}(?:[ .\u00a0]\d{3})+|\d+)[,.]\d{2}.*$",
            raw,
        )
        if marked and type(page_item.get("page")) is int:
            return page_item["page"], " ".join(marked.group(0).split())
        match = re.search(
            r"(?i)(date.{0,180}(?:libell[ée]|nature\s+op[ée]ration|"
            r"op[ée]ration[- ]?r[ée]f[ée]rence|r[ée]f[ée]rence)"
            r".{0,180}(?:montant\s+)?d[ée]bit.{0,120}"
            r"(?:montant\s+)?cr[ée]dit)",
            raw,
            re.S,
        )
        if match and type(page_item.get("page")) is int:
            return page_item["page"], " ".join(match.group(1).split())
        # Sur certains scans, les traits du tableau font perdre l'en-tête,
        # alors que le solde de départ et les libellés d'opération restent
        # parfaitement lisibles. Cette combinaison atteste l'activité sans
        # inventer une transaction ou un montant.
        normalized = _norm(raw)
        operation = re.search(
            r"(?im)^.*\b(?:virement|virt|retrait|paiement|commission|frais|"
            r"echeance|prelevement|versement)\w*\b.*$",
            raw,
        )
        if ("solde depart" in normalized or "ancien solde" in normalized) and operation:
            return page_item["page"], " ".join(operation.group(0).split())
    return None


def _zero_proposal(transactions, pages, document_path, document_sha256, method):
    """Propose zéro seulement lorsqu'un tableau d'opérations est attesté.

    Il s'agit d'une proposition à faible confiance : le client doit toujours la
    confirmer. Une page illisible ou sans opérations continue donc à produire
    ``None`` au lieu d'un faux zéro.
    """
    evidence = _statement_activity_evidence(transactions, pages)
    if not evidence:
        return None
    page, quote = evidence
    return {
        "value": 0.0,
        "confidence": 0.35,
        "source": {
            "document": Path(document_path).name if document_path else None,
            "sha256": document_sha256,
            "page": page,
            "quote": quote,
            "verified": True,
            "evidence": [],
            "method": method,
            "absence_based": True,
        },
    }


def _ocr_keyword_transactions(pages, keywords, transaction_type):
    """Relit les lignes OCR aplaties quand le LLM omet le tableau.

    Les relevés marocains rencontrés placent parfois la date valeur avant le
    libellé et parfois après. Le motif accepte les deux organisations tout en
    exigeant une date, un mot-clé métier et un montant décimal sur la même
    ligne logique délimitée par ``|``.
    """
    date_pattern = (
        r"\d{1,2}(?:\s*[./-]\s*|\s+)\d{1,2}"
        r"(?:(?:\s*[./-]\s*|\s+)\d{2,4})?"
    )
    keyword_pattern = (
        keywords
        if isinstance(keywords, str)
        else "|".join(re.escape(_norm(word)) for word in keywords)
    )
    amount_pattern = r"(\d{1,3}(?:[ .]\d{3})*|\d+)[,.](\d{2})"
    pattern = re.compile(
        rf"(?P<date>{date_pattern})\s*\|\s*"
        rf"(?:{date_pattern}\s*\|\s*)?"
        rf"(?:[^|]{{1,35}}\|\s*){{0,2}}"
        rf"(?P<description>[^|]{{0,120}}?(?:{keyword_pattern})[^|]{{0,120}}?)\s*\|\s*"
        rf"(?:{date_pattern}\s*\|\s*)?"
        rf"(?:\|\s*)?"
        rf"(?P<amount>{amount_pattern})",
        re.I,
    )
    found = []
    expected_month = _statement_month(pages)

    def valid_day(day):
        # Une date OCR isolée qui sort du mois explicitement attesté par le
        # relevé est ignorée. On ne la corrige pas arbitrairement.
        return day is not None and (
            expected_month is None or day.strftime("%Y-%m") == expected_month
        )
    for page_item in pages or []:
        page_number = page_item.get("page")
        if type(page_number) is not int:
            continue
        raw_page_text = str(page_item.get("text") or "")

        # Ne jamais exécuter le motif structuré sur toute la page aplatie.
        # Sur CIH, cela pouvait partir de « SOLDE DEPART 25/12/2024 »,
        # traverser le retour à la ligne et attribuer cette date au virement
        # du 05/01. La série se retrouvait alors artificiellement répartie
        # sur deux mois et le calcul était rejeté comme irrégulier.
        for raw_line in raw_page_text.splitlines():
            normalized_line = _norm(raw_line)
            for match in pattern.finditer(normalized_line):
                day = _transaction_date(match.group("date"), pages)
                amount = _amount(match.group("amount"))
                if not valid_day(day) or amount is None or amount <= 0:
                    continue
                found.append({
                    "date": match.group("date"),
                    "description": match.group("description").strip(),
                    "montant": amount,
                    "type": transaction_type,
                    "page": page_number,
                    "quote": " ".join(raw_line.split()),
                    "month": day.strftime("%Y-%m"),
                })

        # Cette version aplatie reste réservée au dernier secours ci-dessous,
        # lorsque l'OCR a réellement séparé les cellules sur plusieurs lignes.
        page_text = _norm(" ".join(raw_page_text.split()))

        # Secours indépendant des séparateurs de colonnes. PaddleOCR peut
        # produire une ligne correcte mais accoler les deux dates
        # (« 01/0901/09 ») ou omettre les cellules vides. Le mot-clé métier,
        # une date en début de ligne et un montant décimal restent exigés.
        flexible_date = re.compile(
            r"^\s*[^0-9]{0,2}(?P<date>\d{1,2}\s*[./-]\s*\d{1,2}"
            r"(?:\s*[./-]\s*\d{2,4})?)"
        )
        flexible_amount = re.compile(
            r"(?<!\d)(?:\d{1,3}(?:[ .]\d{3})+|\d+)[,.]\d{2}(?!\d)"
        )
        for raw_line in raw_page_text.splitlines():
            line = _norm(raw_line)
            if not line or not re.search(keyword_pattern, line, re.I):
                continue
            date_match = flexible_date.search(line)
            amounts = list(flexible_amount.finditer(line))
            if not date_match or not amounts:
                continue
            day = _transaction_date(date_match.group("date"), pages)
            amount = _amount(amounts[-1].group(0))
            if not valid_day(day) or amount is None or amount <= 0:
                continue
            description = line[date_match.end():amounts[-1].start()]
            # Retirer une éventuelle deuxième date valeur accolée au début.
            description = re.sub(
                r"^\s*\d{1,2}\s*[./-]\s*\d{1,2}"
                r"(?:\s*[./-]\s*\d{2,4})?\s*\|?\s*",
                "",
                description,
            ).strip(" |-:")
            if not re.search(keyword_pattern, description, re.I):
                description = line[date_match.end():amounts[-1].start()].strip(" |-:")
            found.append({
                "date": date_match.group("date"),
                "description": description,
                "montant": amount,
                "type": transaction_type,
                "page": page_number,
                "quote": " ".join(raw_line.split()),
                "month": day.strftime("%Y-%m"),
            })

        # Dernier secours : certains OCR rendent chaque cellule du tableau sur
        # une ligne différente. On recherche alors dans le texte aplati une
        # séquence bornée « date ... libellé métier ... montant », sans exiger
        # la présence de séparateurs verticaux ni connaître la banque.
        flat_date_pattern = (
            r"(?<!\d)\d{1,2}\s*[./-]\s*\d{1,2}"
            r"(?:\s*[./-]\s*\d{2,4})?"
        )
        for keyword_match in re.finditer(keyword_pattern, page_text, re.I):
            prefix_start = max(0, keyword_match.start() - 140)
            prefix = page_text[prefix_start:keyword_match.start()]
            date_matches = list(re.finditer(flat_date_pattern, prefix, re.I))
            if not date_matches:
                continue
            nearest_date = date_matches[-1]
            suffix = page_text[keyword_match.start():keyword_match.start() + 180]
            amount_match = re.search(amount_pattern, suffix, re.I)
            if not amount_match:
                continue
            raw_date = nearest_date.group(0)
            raw_amount = amount_match.group(0)
            day = _transaction_date(raw_date, pages)
            amount = _amount(raw_amount)
            description = suffix[:amount_match.start()].strip(" |-:")
            if not valid_day(day) or amount is None or amount <= 0:
                continue
            quote_start = prefix_start + nearest_date.start()
            quote_end = keyword_match.start() + amount_match.end()
            found.append({
                "date": raw_date,
                "description": description,
                "montant": amount,
                "type": transaction_type,
                "page": page_number,
                "quote": page_text[quote_start:quote_end].strip(),
                "month": day.strftime("%Y-%m"),
            })

    # La passe structurée et la passe flexible peuvent retrouver la même
    # opération avec deux citations légèrement différentes (la seconde date
    # valeur peut manquer dans l'une d'elles). Date, montant et libellé de la
    # même page forment alors l'identité observable la plus stable. Deux lignes
    # strictement identiques resteraient de toute façon indiscernables dans le
    # texte OCR aplati et doivent être soumises à confirmation humaine.
    unique = []
    for item in found:
        identity_description = _norm(item["description"]).strip(" |-:")
        identity_description = re.sub(
            r"^(?:\d{1,2}\s*[./-]\s*\d{1,2}"
            r"(?:\s*[./-]\s*\d{2,4})?\s*\|\s*)+",
            "",
            identity_description,
        ).strip(" |-:")
        identity = (
            item["page"], item["date"], round(float(item["montant"]), 2)
        )
        duplicate = False
        for kept, kept_identity, kept_description in unique:
            same_description = (
                identity_description == kept_description
                or identity_description in kept_description
                or kept_description in identity_description
            )
            same_quote = _norm(item["quote"]) == _norm(kept["quote"])
            if identity == kept_identity and (same_description or same_quote):
                duplicate = True
                break
        if not duplicate:
            unique.append((item, identity, identity_description))
    return [item for item, _, _ in unique]


def _ocr_fuzzy_incoming_transactions(pages):
    """Relit les virements reçus dont le libellé a été déformé par l'OCR."""
    date_pattern = re.compile(
        r"^\s*[^0-9]{0,2}(?P<date>\d{1,2}\s*[./-]\s*\d{1,2}"
        r"(?:\s*[./-]\s*\d{2,4})?)"
    )
    amount_pattern = re.compile(
        r"(?<![\d:])(?:\d{1,3}(?:[ .]\d{3})+|\d+)[,.]\s*\d{2}(?!\d)"
    )
    expected_month = _statement_month(pages)
    found = []
    for page_item in pages or []:
        page_number = page_item.get("page")
        if type(page_number) is not int:
            continue
        for raw_line in str(page_item.get("text") or "").splitlines():
            normalized = _norm(raw_line)
            date_match = date_pattern.search(normalized)
            # Montant réel observé : ``880,00`` peut sortir ``88:0,00``.
            # Le deux-points n'est supprimé que s'il se trouve au milieu du
            # montant final ; les heures et les dates restent inchangées.
            amount_scan_line = re.sub(
                r"(?<=\d):(?=\d{1,3}[,.]\s*\d{2}(?!\d))", "", normalized
            )
            amounts = list(amount_pattern.finditer(amount_scan_line))
            if not date_match or not amounts:
                continue
            amount_match = amounts[-1]
            day = _transaction_date(date_match.group("date"), pages)
            day = _force_statement_month(day, expected_month)
            amount = _amount(amount_match.group(0))
            if (
                day is None or amount is None or amount <= 0
                or (expected_month and day.strftime("%Y-%m") != expected_month)
            ):
                continue
            description = amount_scan_line[date_match.end():amount_match.start()]
            # Enlever la date valeur accolée à la date opération :
            # « 02/0902/09 | VIREMEAT RECD ... ».
            description = re.sub(
                r"^\s*\d{1,2}\s*[./-]\s*\d{1,2}"
                r"(?:\s*[./-]\s*\d{2,4})?\s*\|?\s*",
                "",
                description,
            ).strip(" |-:")
            if not _incoming_description(description):
                continue
            found.append({
                "date": date_match.group("date"),
                "description": description,
                "montant": amount,
                "type": "credit",
                "page": page_number,
                "quote": " ".join(raw_line.split()),
                "month": day.strftime("%Y-%m"),
            })

    unique = []
    seen = set()
    for item in found:
        identity = (
            item["page"], item["date"], round(float(item["montant"]), 2),
            _norm(item["description"]),
        )
        if identity not in seen:
            seen.add(identity)
            unique.append(item)
    return unique


def _column_marked_transactions(pages, transaction_type):
    """Lit les lignes dont la colonne Débit/Crédit a été conservée par l'OCR.

    Les marqueurs sont produits à partir de la position horizontale des
    montants par ``lines_to_layout_text``. Ils rendent le calcul indépendant
    du libellé de la banque et évitent de deviner le sens d'une opération.
    """
    marker = "credit" if transaction_type == "credit" else "debit"
    marker_pattern = re.compile(
        rf"\b{marker}\s*:\s*(?P<amount>"
        r"(?:\d{1,3}(?:[ .\u00a0]\d{3})+|\d+)[,.]\d{2})\b",
        re.I,
    )
    date_pattern = re.compile(
        r"(?<!\d)(\d{1,2}(?:\s*[./-]\s*|\s+)\d{1,2}"
        r"(?:(?:\s*[./-]\s*|\s+)\d{2,4})?)(?!\d)"
    )
    expected_month = _statement_month(pages)
    found = []
    for page_item in pages or []:
        page_number = page_item.get("page")
        if type(page_number) is not int:
            continue
        for raw_line in str(page_item.get("text") or "").splitlines():
            amount_match = marker_pattern.search(raw_line)
            dates = list(date_pattern.finditer(raw_line[:amount_match.start()])) if amount_match else []
            if not amount_match or not dates:
                continue
            day = _transaction_date(dates[0].group(1), pages)
            amount = _amount(amount_match.group("amount"))
            if (
                day is None
                or amount is None
                or amount <= 0
                or (expected_month and day.strftime("%Y-%m") != expected_month)
            ):
                continue
            description_start = dates[-1].end()
            description = raw_line[description_start:amount_match.start()].strip(" |:-")
            if not description:
                continue
            found.append({
                "date": dates[0].group(1),
                "description": description,
                "montant": amount,
                "type": transaction_type,
                "page": page_number,
                "quote": " ".join(raw_line.split()),
                "month": day.strftime("%Y-%m"),
            })

    # Une ligne reconstruite n'est parcourue qu'une fois. Ne pas dédupliquer
    # ici : deux opérations strictement identiques peuvent être deux mouvements
    # bancaires réels et doivent toutes deux contribuer au total.
    return found


def _has_column_marker(item, marker):
    """Vrai seulement si la citation OCR prouve explicitement la colonne.

    ``type`` est une sortie du modèle et peut être erroné. Les marqueurs
    DEBIT:/CREDIT: sont, eux, ajoutés depuis la géométrie du tableau OCR.
    """
    quote = str(item.get("quote") or "")
    return bool(re.search(rf"\b{marker}\s*:", _norm(quote), re.I))


def _prefer_complete_evidence(model_transactions, ocr_transactions, metric_name):
    """Retient la série prouvée la plus complète pour un calcul mensuel.

    Le modèle peut reconnaître une première ligne puis omettre les lignes
    identiques suivantes. Le secours OCR doit donc aussi être exécuté quand
    la liste du modèle n'est pas vide. On remplace la série uniquement si le
    document fournit davantage d'opérations explicites, afin de ne pas perdre
    une extraction du modèle déjà plus riche.
    """
    if len(ocr_transactions) > len(model_transactions):
        logger.info(
            "%s: série OCR plus complète retenue (%s opérations contre %s).",
            metric_name,
            len(ocr_transactions),
            len(model_transactions),
        )
        return ocr_transactions
    return model_transactions or ocr_transactions


def _merge_evidence_series(*series):
    """Fusionne plusieurs lectures de transactions sans compter deux fois.

    Les marqueurs de colonne, le modèle et le secours OCR peuvent retrouver
    la même ligne sous des formes légèrement différentes. La citation OCR est
    l'identité la plus fiable ; à défaut, on compare page, date, montant et
    libellé normalisé. Deux lignes réellement distinctes restent conservées.
    """
    merged = []
    for items in series:
        for item in items or []:
            if not isinstance(item, dict):
                continue
            quote = _norm(item.get("quote"))
            description = _norm(item.get("description")).strip(" |-:")
            identity = (
                item.get("page"),
                _norm(item.get("date")),
                round(float(_amount(item.get("montant")) or 0.0), 2),
            )
            duplicate = False
            for kept in merged:
                kept_quote = _norm(kept.get("quote"))
                if quote and kept_quote and quote == kept_quote:
                    duplicate = True
                    break
                kept_identity = (
                    kept.get("page"),
                    _norm(kept.get("date")),
                    round(float(_amount(kept.get("montant")) or 0.0), 2),
                )
                kept_description = _norm(kept.get("description")).strip(" |-:")
                same_description = (
                    description == kept_description
                    or (description and description in kept_description)
                    or (kept_description and kept_description in description)
                )
                if identity == kept_identity and same_description:
                    duplicate = True
                    break
            if not duplicate:
                merged.append(item)
    return merged


def derive_monthly_credit_charge(transactions, pages, document_path, document_sha256):
    """Médiane des totaux mensuels prouvés ; aucun résultat sans preuve OCR."""
    eligible = []
    expected_month = _statement_month(pages)
    for item in transactions or []:
        if not isinstance(item, dict):
            continue
        description = _norm(item.get("description"))
        amount = _amount(item.get("montant"))
        day = _transaction_date(item.get("date"), pages)
        transaction_type = _norm(item.get("type"))
        quote = _transaction_evidence(item, pages)
        verified = quote is not None
        credit_label = bool(re.search(CREDIT_CHARGE_PATTERN, description))
        # Certains modèles renvoient "débit", "DEBIT", "D" ou un montant négatif.
        # Le libellé explicite de mensualité reste obligatoire pour éviter les faux positifs.
        is_debit = transaction_type in {"debit", "d", "dr"} or (
            transaction_type == "" and amount is not None and amount < 0
        )
        day_in_period = day and (
            expected_month is None or day.strftime("%Y-%m") == expected_month
        )
        if (is_debit and day_in_period and amount is not None and amount != 0
                and credit_label
                and not any(word in description for word in EXCLUDED_WORDS) and verified):
            eligible.append({**item, "montant": abs(amount), "quote": quote,
                             "month": day.strftime("%Y-%m")})
        elif credit_label:
            logger.warning(
                "Échéance de crédit ignorée: type=%r, montant=%r, date=%r, page=%r, preuve_verifiee=%s",
                item.get("type"), item.get("montant"), item.get("date"), page, verified,
            )
    # Le secours est systématique : une liste LLM partielle ne doit pas bloquer
    # la lecture des autres échéances explicitement présentes dans l'OCR.
    marked_eligible = [
        item for item in _column_marked_transactions(pages, "debit")
        if re.search(CREDIT_CHARGE_PATTERN, _norm(item["description"]))
        and not any(word in _norm(item["description"]) for word in EXCLUDED_WORDS)
    ]
    ocr_eligible = [
        item for item in _ocr_keyword_transactions(pages, CREDIT_CHARGE_PATTERN, "debit")
        if re.search(CREDIT_CHARGE_PATTERN, _norm(item["description"]))
        and not any(word in _norm(item["description"]) for word in EXCLUDED_WORDS)
    ]
    # Les marqueurs de colonne proviennent de la géométrie du tableau et
    # sont donc prioritaires. Le secours lexical aplati peut voir une même
    # échéance deux fois en traversant la ligne d'en-tête.
    ocr_eligible = marked_eligible or ocr_eligible
    eligible = (
        marked_eligible
        if marked_eligible
        else _prefer_complete_evidence(
            eligible, ocr_eligible, "Charges mensuelles de crédits"
        )
    )
    for item in ocr_eligible:
        logger.info(
            "Échéance de crédit reconnue directement dans l'OCR: page=%s, montant=%.2f",
            item["page"], item["montant"],
        )
    if not eligible:
        return _zero_proposal(
            transactions, pages, document_path, document_sha256,
            "aucune échéance de crédit explicite détectée dans les opérations du relevé",
        )
    monthly = {}
    for item in eligible:
        monthly[item["month"]] = monthly.get(item["month"], 0.0) + float(item["montant"])
    # Sur plusieurs mois, deux mois concordants sont exigés. Sur une période
    # d'un mois, un libellé explicite reste une proposition à confirmer.
    if len(monthly) > 1:
        values = list(monthly.values())
        median = statistics.median(values)
        if median == 0 or max(abs(v - median) / median for v in values) > 0.20:
            return None
    amount = float(statistics.median(monthly.values()))
    first = eligible[0]
    return {
        "value": amount, "confidence": 0.50,
        "source": {"document": Path(document_path).name, "sha256": document_sha256,
                   "page": first["page"], "quote": first["quote"], "verified": True,
                   "evidence": [{k: x.get(k) for k in ("date", "description", "montant", "page", "quote")}
                                for x in eligible],
                   "method": "médiane des totaux mensuels d'échéances de crédit vérifiées"},
    }


def derive_complementary_income(transactions, pages, document_path, document_sha256):
    """Propose le total mensuel des crédits complémentaires, salaire exclu.

    Un seul mois produit une proposition à faible confiance ; deux mois
    concordants augmentent la confiance. La confirmation du client reste
    obligatoire dans les deux cas.
    """
    eligible = []
    excluded = []
    expected_month = _statement_month(pages)
    for item in transactions or []:
        if not isinstance(item, dict):
            continue
        description = _norm(item.get("description"))
        amount = _amount(item.get("montant"))
        day = _transaction_date(item.get("date"), pages)
        transaction_type = _norm(item.get("type"))
        quote = _transaction_evidence(item, pages)
        verified = quote is not None
        incoming_label = _incoming_description(description)
        column_proven = _has_column_marker(item, "credit")
        outgoing_label = _outgoing_description(description)
        # Un type="credit" produit par le LLM ne constitue pas une preuve
        # suffisante : c'est précisément ce qui transformait « FRAIS PACK
        # ... 80,00 » en revenu sur certains relevés Crédit du Maroc. Il faut
        # soit un marqueur de colonne issu de la géométrie OCR, soit un libellé
        # entrant explicite (VIREMENT RECU, VERSEMENT, etc.).
        is_credit = column_proven or (
            transaction_type in {"credit", "c", "cr", ""}
            and incoming_label
            and not outgoing_label
        )
        day_in_period = day and (
            expected_month is None or day.strftime("%Y-%m") == expected_month
        )
        exclusion_reason = _income_exclusion_reason(description)
        if (is_credit and day_in_period and amount is not None and amount > 0 and verified):
            candidate = {**item, "montant": amount, "quote": quote,
                         "month": day.strftime("%Y-%m")}
            if exclusion_reason:
                excluded.append(_evidence_item(candidate, "exclu", exclusion_reason))
            else:
                eligible.append(candidate)
    # Le secours est systématique : le modèle extrait fréquemment la première
    # occurrence d'un virement récurrent mais oublie les suivantes.
    marked_candidates = _column_marked_transactions(pages, "credit")
    marked_eligible = [
        item for item in marked_candidates
        if _income_exclusion_reason(item["description"]) is None
        # Le marqueur CREDIT vient de la géométrie réelle du tableau. Il reste
        # une preuve suffisante si l'OCR a perdu le mot VIREMENT/RECU, à
        # condition qu'aucun indice de mouvement sortant ne soit présent.
        and not _outgoing_description(item["description"])
    ]
    marked_excluded = [
        _evidence_item(item, "exclu", _income_exclusion_reason(item["description"]))
        for item in marked_candidates
        if _income_exclusion_reason(item["description"]) is not None
    ]
    ocr_candidates = [
        item for item in _ocr_keyword_transactions(
            pages, INCOMING_OPERATION_PATTERN, "credit"
        )
        if re.search(INCOMING_OPERATION_PATTERN, _norm(item["description"]))
    ]
    ocr_eligible = [
        item for item in ocr_candidates
        if _income_exclusion_reason(item["description"]) is None
    ]
    fuzzy_candidates = _ocr_fuzzy_incoming_transactions(pages)
    fuzzy_eligible = [
        item for item in fuzzy_candidates
        if _income_exclusion_reason(item["description"]) is None
    ]
    # Une méthode ne doit jamais masquer les opérations trouvées par une
    # autre. C'était le cas Attijari : un seul faux marqueur CREDIT sur un
    # virement émis de 500 MAD supprimait deux vrais virements reçus lus par
    # le secours textuel. On fusionne les preuves, puis on déduplique par la
    # citation OCR et l'identité observable de la transaction.
    fallback_eligible = _merge_evidence_series(ocr_eligible, fuzzy_eligible)
    eligible = _merge_evidence_series(marked_eligible, fallback_eligible, eligible)
    fallback_excluded = [
        _evidence_item(item, "exclu", _income_exclusion_reason(item["description"]))
        for item in _merge_evidence_series(ocr_candidates, fuzzy_candidates)
        if _income_exclusion_reason(item["description"]) is not None
    ]
    excluded = _merge_evidence_series(marked_excluded, fallback_excluded, excluded)
    if not eligible:
        return _zero_proposal(
            transactions, pages, document_path, document_sha256,
            "aucune opération créditrice éligible détectée dans le relevé",
        )
    monthly = {}
    for item in eligible:
        monthly[item["month"]] = monthly.get(item["month"], 0.0) + float(item["montant"])
    values = list(monthly.values())
    median = statistics.median(values)
    regularity_proven = len(values) >= 2
    if median == 0 or (regularity_proven and max(abs(v - median) / median for v in values) > 0.30):
        return None
    first = eligible[0]
    return {
        "value": float(median),
        "confidence": 0.60 if regularity_proven else 0.40,
        "source": {"document": Path(document_path).name, "sha256": document_sha256,
                   "page": first["page"], "quote": first["quote"], "verified": True,
                   "evidence": [_evidence_item(x) for x in eligible],
                   "excluded_evidence": excluded,
                   "method": (
                       "entrées créditrices détectées sur un seul relevé — régularité à confirmer"
                       if not regularity_proven else
                       "médiane des crédits mensuels récurrents vérifiés"
                   ),
                   "regularity_proven": regularity_proven},
    }


def debt_ratio(net_income, monthly_credit_charge):
    net, charge = float(net_income), float(monthly_credit_charge)
    if net <= 0 or charge < 0:
        raise ValueError("Revenu net positif et charges positives requis")
    return charge / net
