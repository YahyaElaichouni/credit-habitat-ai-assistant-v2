"""Calculs déterministes proposés à la revue humaine, jamais décisions LLM."""
import re
import statistics
import unicodedata
import logging
from datetime import datetime, timedelta
from pathlib import Path

CREDIT_CHARGE_PATTERN = (
    r"\b(?:mensualite|echeance|prelevement|reglement|remboursement|traite)\w*"
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
    r"(?:recu|de)\b"
    r"|\brecept(?:ion)?\b.{0,24}\bvir(?:ement)?\b"
    r"|\b(?:vers(?:ement|t)?|depot|remise|allocation|pension|loyer|prime|"
    r"distribution|dividende|benefice)\w*\b"
    r"|\binteret\s+crediteur\b"
)
EXTRA_INCOME_EXCLUDED = (
    "salaire", "paie", "remboursement", "annulation", "contrepassation",
    "solde initial", "ancien solde", "nouveau solde", "total mouvement",
    "virement emis", "commission", "retrait", "frais", "paiement",
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


def _date(value, default_year=None):
    raw = re.sub(r"\s+", " ", str(value or "")).strip()
    short = re.fullmatch(r"(\d{1,2})[./-](\d{1,2})", raw)
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
    years = re.findall(r"(?<!\d)\d{1,2}[./-]\d{1,2}[./-](\d{4})(?!\d)", text)
    if not years:
        return None
    raw_year = int(statistics.mode(years))
    return raw_year + 2000 if raw_year < 100 else raw_year


def _statement_month(pages):
    """Mois attendu, déduit d'une période ou du solde de départ précédent."""
    text = " ".join(str(item.get("text") or "") for item in pages or [])
    period = re.search(
        r"(?i)(?:relev[ée]\s+)?du\s+(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})"
        r"\s+au\s+\d{1,2}[./-]\d{1,2}[./-]\d{2,4}",
        text,
    )
    if period:
        year = int(period.group(3))
        if year < 100:
            year += 2000
        return f"{year:04d}-{int(period.group(2)):02d}"

    opening = re.search(
        r"(?i)(?:solde\s+(?:de\s+)?d[ée]part|ancien\s+solde)"
        r".{0,80}?(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})",
        text,
    )
    if not opening:
        return None
    day, month, year = (int(part) for part in opening.groups())
    if year < 100:
        year += 2000
    try:
        following_day = datetime(year, month, day).date() + timedelta(days=1)
    except ValueError:
        return None
    return following_day.strftime("%Y-%m")


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

    day = _date(item.get("date"), _statement_year(pages))
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
        match = re.search(
            r"(?i)(date.{0,140}(?:libell[ée]|nature\s+op[ée]ration|r[ée]f[ée]rence)"
            r".{0,140}d[ée]bit.{0,80}cr[ée]dit)",
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
        page_text = _norm(" ".join(str(page_item.get("text") or "").split()))
        for match in pattern.finditer(page_text):
            day = _date(match.group("date"), _statement_year(pages))
            amount = _amount(match.group("amount"))
            if not valid_day(day) or amount is None or amount <= 0:
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
        for raw_line in str(page_item.get("text") or "").splitlines():
            line = _norm(raw_line)
            if not line or not re.search(keyword_pattern, line, re.I):
                continue
            date_match = flexible_date.search(line)
            amounts = list(flexible_amount.finditer(line))
            if not date_match or not amounts:
                continue
            day = _date(date_match.group("date"), _statement_year(pages))
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
            day = _date(raw_date, _statement_year(pages))
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


def derive_monthly_credit_charge(transactions, pages, document_path, document_sha256):
    """Médiane des totaux mensuels prouvés ; aucun résultat sans preuve OCR."""
    eligible = []
    expected_month = _statement_month(pages)
    for item in transactions or []:
        if not isinstance(item, dict):
            continue
        description = _norm(item.get("description"))
        amount = _amount(item.get("montant"))
        day = _date(item.get("date"), _statement_year(pages))
        transaction_type = _norm(item.get("type"))
        page = item.get("page")
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
    ocr_eligible = [
        item for item in _ocr_keyword_transactions(pages, CREDIT_CHARGE_PATTERN, "debit")
        if not any(word in _norm(item["description"]) for word in EXCLUDED_WORDS)
    ]
    eligible = _prefer_complete_evidence(
        eligible, ocr_eligible, "Charges mensuelles de crédits"
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
    expected_month = _statement_month(pages)
    for item in transactions or []:
        if not isinstance(item, dict):
            continue
        description = _norm(item.get("description"))
        amount = _amount(item.get("montant"))
        day = _date(item.get("date"), _statement_year(pages))
        transaction_type = _norm(item.get("type"))
        page = item.get("page")
        quote = _transaction_evidence(item, pages)
        verified = quote is not None
        incoming_label = bool(re.search(INCOMING_OPERATION_PATTERN, description))
        is_credit = transaction_type in {"credit", "c", "cr"} or (
            transaction_type == "" and incoming_label
        )
        day_in_period = day and (
            expected_month is None or day.strftime("%Y-%m") == expected_month
        )
        if (is_credit and day_in_period and amount is not None and amount > 0
                and not any(word in description for word in EXTRA_INCOME_EXCLUDED) and verified):
            eligible.append({**item, "montant": amount, "quote": quote,
                             "month": day.strftime("%Y-%m")})
    # Le secours est systématique : le modèle extrait fréquemment la première
    # occurrence d'un virement récurrent mais oublie les suivantes.
    ocr_eligible = [
        item for item in _ocr_keyword_transactions(
            pages, INCOMING_OPERATION_PATTERN, "credit"
        )
        if not any(
            word in _norm(item["description"])
            for word in EXTRA_INCOME_EXCLUDED
        )
    ]
    eligible = _prefer_complete_evidence(
        eligible, ocr_eligible, "Revenus complémentaires"
    )
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
                   "evidence": [{k: x.get(k) for k in ("date", "description", "montant", "page", "quote")}
                                for x in eligible],
                   "method": "médiane des crédits mensuels vérifiés, salaire et opérations techniques exclus",
                   "regularity_proven": regularity_proven},
    }


def debt_ratio(net_income, monthly_credit_charge):
    net, charge = float(net_income), float(monthly_credit_charge)
    if net <= 0 or charge < 0:
        raise ValueError("Revenu net positif et charges positives requis")
    return charge / net
