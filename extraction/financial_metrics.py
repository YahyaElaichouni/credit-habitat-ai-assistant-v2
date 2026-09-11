"""Calculs déterministes proposés à la revue humaine, jamais décisions LLM."""
import re
import statistics
import unicodedata
import logging
from datetime import datetime
from pathlib import Path

CREDIT_WORDS = (
    "mensualite credit", "mensualite de credit", "mensualite pret",
    "echeance credit", "echeance de credit", "echeance pret", "echeance de pret",
    "prelevement credit", "prelevement de credit", "prelevement pret",
    "reglement credit", "remboursement credit", "remboursement pret",
    "credit immobilier", "credit habitat", "credit logement",
    "credit auto", "credit consommation",
)
EXCLUDED_WORDS = ("assurance", "remboursement anticipe", "solde du pret")
EXTRA_INCOME_WORDS = (
    "prime", "virement complementaire", "revenu complementaire",
    "allocation", "loyer recu", "pension", "vir-inst de",
    "virement recu", "virement en votre faveur", "vir crediteur",
)
OCR_EXTRA_INCOME_WORDS = (
    "vir-inst de", "virement recu", "virement en votre faveur",
    "vir crediteur", "virement complementaire", "loyer recu",
)
EXTRA_INCOME_EXCLUDED = (
    "salaire", "paie", "remboursement", "annulation", "contrepassation",
    "solde initial", "ancien solde", "nouveau solde", "total mouvement",
)

logger = logging.getLogger(__name__)


def _verified_transactions(transactions, pages):
    """Transactions dont la citation est réellement présente sur la page OCR."""
    page_map = {p["page"]: _norm(p["text"]) for p in pages}
    verified = []
    for item in transactions or []:
        page, quote = item.get("page"), item.get("quote")
        if (type(page) is int and page in page_map and isinstance(quote, str)
                and _norm(quote) and _norm(quote) in page_map[page]):
            verified.append(item)
    return verified


def _norm(value):
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", text).strip()


def _date(value):
    raw = re.sub(r"\s+", " ", str(value or "")).strip()
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

    day = _date(item.get("date"))
    amount = _amount(item.get("montant"))
    description = _norm(item.get("description"))
    if day is None or amount is None or not description:
        return None
    date_forms = {
        day.strftime("%d/%m/%Y"), day.strftime("%d-%m-%Y"),
        day.strftime("%Y-%m-%d"), day.strftime("%d.%m.%Y"),
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
        match = re.search(
            r"(?i)(date.{0,140}(?:libell[ée]|nature\s+op[ée]ration|r[ée]f[ée]rence)"
            r".{0,140}d[ée]bit.{0,80}cr[ée]dit)",
            raw,
        )
        if match and type(page_item.get("page")) is int:
            return page_item["page"], " ".join(match.group(1).split())
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
    date_pattern = r"\d{1,2}(?:\s*[./-]\s*|\s+)\d{1,2}(?:\s*[./-]\s*|\s+)\d{2,4}"
    keyword_pattern = "|".join(re.escape(_norm(word)) for word in keywords)
    amount_pattern = r"(\d{1,3}(?:[ .]\d{3})*|\d+)[,.](\d{2})"
    pattern = re.compile(
        rf"(?P<date>{date_pattern})\s*\|\s*"
        rf"(?:{date_pattern}\s*\|\s*)?"
        rf"(?:[^|]{{1,35}}\|\s*){{0,2}}"
        rf"(?P<description>[^|]{{0,120}}?(?:{keyword_pattern})[^|]{{0,120}}?)\s*\|\s*"
        rf"(?:{date_pattern}\s*\|\s*)?"
        rf"(?P<amount>{amount_pattern})",
        re.I,
    )
    found = []
    for page_item in pages or []:
        page_number = page_item.get("page")
        if type(page_number) is not int:
            continue
        page_text = _norm(" ".join(str(page_item.get("text") or "").split()))
        for match in pattern.finditer(page_text):
            day = _date(match.group("date"))
            amount = _amount(match.group("amount"))
            if day is None or amount is None or amount <= 0:
                continue
            found.append({
                "date": match.group("date"),
                "description": match.group("description").strip(),
                "montant": amount,
                "type": transaction_type,
                "page": page_number,
                "quote": match.group(0).strip(),
                "month": day.strftime("%Y-%m"),
            })
    return found


def derive_monthly_credit_charge(transactions, pages, document_path, document_sha256):
    """Médiane des totaux mensuels prouvés ; aucun résultat sans preuve OCR."""
    eligible = []
    for item in transactions or []:
        if not isinstance(item, dict):
            continue
        description = _norm(item.get("description"))
        amount, day = _amount(item.get("montant")), _date(item.get("date"))
        transaction_type = _norm(item.get("type"))
        page = item.get("page")
        quote = _transaction_evidence(item, pages)
        verified = quote is not None
        credit_label = any(word in description for word in CREDIT_WORDS)
        # Certains modèles renvoient "débit", "DEBIT", "D" ou un montant négatif.
        # Le libellé explicite de mensualité reste obligatoire pour éviter les faux positifs.
        is_debit = transaction_type in {"debit", "d", "dr"} or (
            transaction_type == "" and amount is not None and amount < 0
        )
        if (is_debit and day and amount is not None and amount != 0
                and credit_label
                and not any(word in description for word in EXCLUDED_WORDS) and verified):
            eligible.append({**item, "montant": abs(amount), "quote": quote,
                             "month": day.strftime("%Y-%m")})
        elif credit_label:
            logger.warning(
                "Échéance de crédit ignorée: type=%r, montant=%r, date=%r, page=%r, preuve_verifiee=%s",
                item.get("type"), item.get("montant"), item.get("date"), page, verified,
            )
    # Secours déterministe : le LLM peut oublier la transaction ou mal typer
    # débit/crédit. Une ligne OCR portant un libellé explicite d'échéance suffit
    # à proposer le montant qui suit immédiatement ce libellé.
    if not eligible:
        eligible = [
            item for item in _ocr_keyword_transactions(pages, CREDIT_WORDS, "debit")
            if not any(word in _norm(item["description"]) for word in EXCLUDED_WORDS)
        ]
        for item in eligible:
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
    for item in transactions or []:
        if not isinstance(item, dict):
            continue
        description = _norm(item.get("description"))
        amount, day = _amount(item.get("montant")), _date(item.get("date"))
        transaction_type = _norm(item.get("type"))
        page = item.get("page")
        quote = _transaction_evidence(item, pages)
        verified = quote is not None
        incoming_label = any(word in description for word in EXTRA_INCOME_WORDS)
        is_credit = transaction_type in {"credit", "c", "cr"} or (
            transaction_type == "" and incoming_label
        )
        if (is_credit and day and amount is not None and amount > 0
                and any(word in description for word in EXTRA_INCOME_WORDS)
                and not any(word in description for word in EXTRA_INCOME_EXCLUDED) and verified):
            eligible.append({**item, "montant": amount, "quote": quote,
                             "month": day.strftime("%Y-%m")})
    # Secours sur le texte tabulaire lorsque le le LLM oublie certaines
    # transactions. « VIR-INST DE » désigne ici un virement entrant explicite.
    if not eligible:
        eligible = [
            item for item in _ocr_keyword_transactions(pages, OCR_EXTRA_INCOME_WORDS, "credit")
            if not any(word in _norm(item["description"]) for word in EXTRA_INCOME_EXCLUDED)
        ]
    if not eligible:
        return _zero_proposal(
            transactions, pages, document_path, document_sha256,
            "aucun revenu complémentaire explicite détecté dans les crédits du relevé",
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
                   "evidence": [{k: x.get(k) for k in ("date", "description", "montant", "page", "quote")}
                                for x in eligible],
                   "method": "médiane des totaux mensuels de revenus complémentaires vérifiés",
                   "regularity_proven": regularity_proven},
    }


def debt_ratio(net_income, monthly_credit_charge):
    net, charge = float(net_income), float(monthly_credit_charge)
    if net <= 0 or charge < 0:
        raise ValueError("Revenu net positif et charges positives requis")
    return charge / net
