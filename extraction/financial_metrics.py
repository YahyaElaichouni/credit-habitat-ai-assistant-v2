"""Calculs déterministes proposés à la revue humaine, jamais décisions LLM."""
import re
import statistics
import unicodedata
import logging
from datetime import datetime
from pathlib import Path

CREDIT_WORDS = ("mensualite credit", "echeance credit", "echeance pret", "prelevement pret",
                "credit immobilier", "credit habitat", "credit auto", "credit consommation")
EXCLUDED_WORDS = ("assurance", "remboursement anticipe", "solde du pret")
EXTRA_INCOME_WORDS = ("prime", "virement complementaire", "revenu complementaire",
                      "allocation", "loyer recu", "pension")
EXTRA_INCOME_EXCLUDED = ("salaire", "remboursement", "annulation", "contrepassation")

logger = logging.getLogger(__name__)


def _norm(value):
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", text).strip()


def _date(value):
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(str(value), fmt).date()
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


def derive_monthly_credit_charge(transactions, pages, document_path, document_sha256):
    """Médiane des totaux mensuels prouvés ; aucun résultat sans preuve OCR."""
    page_map = {p["page"]: _norm(p["text"]) for p in pages}
    eligible = []
    for item in transactions or []:
        description = _norm(item.get("description"))
        amount, day = _amount(item.get("montant")), _date(item.get("date"))
        transaction_type = _norm(item.get("type"))
        page, quote = item.get("page"), item.get("quote")
        verified = (type(page) is int and page in page_map and isinstance(quote, str)
                    and _norm(quote) and _norm(quote) in page_map[page])
        credit_label = any(word in description for word in CREDIT_WORDS)
        # Certains modèles renvoient "débit", "DEBIT", "D" ou un montant négatif.
        # Le libellé explicite de mensualité reste obligatoire pour éviter les faux positifs.
        is_debit = transaction_type in {"debit", "d", "dr"} or (
            transaction_type == "" and amount is not None and amount < 0
        )
        if (is_debit and day and amount is not None and amount != 0
                and credit_label
                and not any(word in description for word in EXCLUDED_WORDS) and verified):
            eligible.append({**item, "montant": abs(amount), "month": day.strftime("%Y-%m")})
        elif credit_label:
            logger.warning(
                "Échéance de crédit ignorée: type=%r, montant=%r, date=%r, page=%r, preuve_verifiee=%s",
                item.get("type"), item.get("montant"), item.get("date"), page, verified,
            )
    # Secours déterministe : le LLM peut oublier la transaction ou mal typer
    # débit/crédit. Une ligne OCR portant un libellé explicite d'échéance suffit
    # à proposer le montant qui suit immédiatement ce libellé.
    if not eligible:
        for page_item in pages:
            page_number = page_item.get("page")
            for raw_line in str(page_item.get("text") or "").splitlines():
                line = _norm(raw_line)
                matched_word = next((word for word in CREDIT_WORDS if word in line), None)
                if not matched_word or any(word in line for word in EXCLUDED_WORDS):
                    continue
                tail = line.split(matched_word, 1)[1]
                amount_match = re.search(r"(?<!\d)(\d{1,3}(?:[ .]\d{3})+|\d+)(?:[,.](\d{1,2}))?", tail)
                date_match = re.search(r"\b(\d{2}[/-]\d{2}[/-]\d{4}|\d{4}-\d{2}-\d{2})\b", line)
                if not amount_match or not date_match or type(page_number) is not int:
                    continue
                amount_text = amount_match.group(1).replace(" ", "")
                if amount_match.group(2):
                    amount_text += "." + amount_match.group(2)
                amount = _amount(amount_text)
                day = _date(date_match.group(1))
                if amount is None or amount <= 0 or day is None:
                    continue
                eligible.append({
                    "date": date_match.group(1), "description": matched_word,
                    "montant": amount, "type": "debit", "page": page_number,
                    "quote": raw_line.strip(), "month": day.strftime("%Y-%m"),
                })
                logger.info(
                    "Échéance de crédit reconnue directement dans l'OCR: page=%s, montant=%.2f",
                    page_number, amount,
                )
    if not eligible:
        return None
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
    """Somme mensuelle des crédits complémentaires prouvés, salaire exclu.

    Sur un seul mois, la valeur est un candidat observé et sa régularité reste
    à confirmer. Sur plusieurs mois, une variation supérieure à 30 % bloque la
    proposition automatique.
    """
    page_map = {p["page"]: _norm(p["text"]) for p in pages}
    eligible = []
    for item in transactions or []:
        description = _norm(item.get("description"))
        amount, day = item.get("montant"), _date(item.get("date"))
        page, quote = item.get("page"), item.get("quote")
        verified = (type(page) is int and page in page_map and isinstance(quote, str)
                    and _norm(quote) and _norm(quote) in page_map[page])
        if (item.get("type") == "credit" and day and isinstance(amount, (int, float)) and amount > 0
                and any(word in description for word in EXTRA_INCOME_WORDS)
                and not any(word in description for word in EXTRA_INCOME_EXCLUDED) and verified):
            eligible.append({**item, "month": day.strftime("%Y-%m")})
    if not eligible:
        return None
    monthly = {}
    for item in eligible:
        monthly[item["month"]] = monthly.get(item["month"], 0.0) + float(item["montant"])
    values = list(monthly.values())
    median = statistics.median(values)
    if len(values) > 1 and (median == 0 or max(abs(v - median) / median for v in values) > 0.30):
        return None
    first = eligible[0]
    regularity_proven = len(monthly) >= 2
    return {
        "value": float(median), "confidence": 0.60 if regularity_proven else 0.40,
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