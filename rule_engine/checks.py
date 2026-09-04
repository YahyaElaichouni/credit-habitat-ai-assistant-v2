"""
===========================================================
Business Rules
Projet PFE Crédit Agricole du Maroc
===========================================================
"""

from datetime import datetime
import re


# =========================================================
# OUTILS
# =========================================================

def is_not_empty(value):
    return value is not None and str(value).strip() != ""


def is_valid_date(date_string):
    if not is_not_empty(date_string):
        return False

    formats = [
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y-%m-%d"
    ]

    for fmt in formats:
        try:
            datetime.strptime(str(date_string), fmt)
            return True
        except ValueError:
            continue

    return False


def is_valid_cin(cin):
    if not is_not_empty(cin):
        return False

    return bool(
        re.match(
            r"^[A-Z]{1,2}[0-9]{5,8}$",
            str(cin).upper()
        )
    )


def is_positive_number(value):
    if value is None:
        return False

    try:
        return float(value) >= 0
    except (ValueError, TypeError):
        return False


# =========================================================
# CARTE IDENTITE
# =========================================================

def validate_carte_identite(data):

    results = []

    if is_not_empty(data.get("cin")):
        results.append({
            "rule": "cin_format",
            "passed": is_valid_cin(data["cin"]),
            "message": "Format du CIN valide"
            if is_valid_cin(data["cin"])
            else "Format du CIN invalide"
        })

    results.append({
        "rule": "nom_present",
        "passed": is_not_empty(data.get("nom")),
        "message": "Nom présent"
        if is_not_empty(data.get("nom"))
        else "Nom absent"
    })

    results.append({
        "rule": "prenom_present",
        "passed": is_not_empty(data.get("prenom")),
        "message": "Prénom présent"
        if is_not_empty(data.get("prenom"))
        else "Prénom absent"
    })

    if is_not_empty(data.get("date_naissance")):
        valid = is_valid_date(data["date_naissance"])
        results.append({
            "rule": "date_naissance",
            "passed": valid,
            "message": "Date de naissance valide"
            if valid
            else "Date de naissance invalide"
        })

    if is_not_empty(data.get("date_expiration")):
        valid = is_valid_date(data["date_expiration"])
        results.append({
            "rule": "date_expiration",
            "passed": valid,
            "message": "Date d'expiration valide"
            if valid
            else "Date d'expiration invalide"
        })

    return results


# =========================================================
# BULLETIN
# =========================================================

def validate_bulletin(data):

    results = []

    if is_not_empty(data.get("date_embauche")):
        valid = False
        for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
            try:
                valid = datetime.strptime(str(data["date_embauche"]), fmt).date() <= datetime.now().date()
                break
            except ValueError:
                continue
        results.append({"rule": "date_embauche", "passed": valid,
                        "message": "Date d'embauche valide" if valid else "Date d'embauche invalide ou future"})

    if data.get("salaire_brut") is not None:
        valid = is_positive_number(data["salaire_brut"])
        results.append({
            "rule": "salaire_brut_positif",
            "passed": valid,
            "message": "Salaire brut valide"
            if valid
            else "Salaire brut invalide"
        })

    if data.get("salaire_net") is not None:
        valid = is_positive_number(data["salaire_net"])
        results.append({
            "rule": "salaire_net_positif",
            "passed": valid,
            "message": "Salaire net valide"
            if valid
            else "Salaire net invalide"
        })

    brut = data.get("salaire_brut")
    net = data.get("salaire_net")

    if brut is not None and net is not None:
        valid = float(net) <= float(brut)
        results.append({
            "rule": "net_inferieur_brut",
            "passed": valid,
            "message": "Salaire net inférieur ou égal au brut"
            if valid
            else "Salaire net supérieur au brut"
        })

    return results


# =========================================================
# RELEVE BANCAIRE
# =========================================================

def validate_releve(data):

    results = []

    for field in ("charge_mensuelle_credits", "revenus_complementaires"):
        if data.get(field) is not None:
            valid = is_positive_number(data[field])
            results.append({"rule": field, "passed": valid,
                            "message": f"{field} : " + ("valide" if valid else "montant invalide")})

    if data.get("solde_initial") is not None:
        valid = is_positive_number(data["solde_initial"])
        results.append({
            "rule": "solde_initial_valide",
            "passed": valid,
            "message": "Solde initial valide"
            if valid
            else "Solde initial invalide"
        })

    if data.get("solde_final") is not None:
        valid = is_positive_number(data["solde_final"])
        results.append({
            "rule": "solde_final_valide",
            "passed": valid,
            "message": "Solde final valide"
            if valid
            else "Solde final invalide"
        })

    transactions = data.get("transactions", [])

    for i, transaction in enumerate(transactions):
        montant = transaction.get("montant")
        if montant is not None:
            valid = is_positive_number(montant)
            results.append({
                "rule": f"transaction_{i}_montant",
                "passed": valid,
                "message": "Montant valide"
                if valid
                else "Montant invalide"
            })

    return results


# =========================================================
# COMPROMIS
# =========================================================

def validate_compromis(data):

    results = []

    results.append({
        "rule": "acheteur_present",
        "passed": is_not_empty(data.get("acheteur_nom")),
        "message": "Acheteur présent"
        if is_not_empty(data.get("acheteur_nom"))
        else "Acheteur absent"
    })

    results.append({
        "rule": "vendeur_present",
        "passed": is_not_empty(data.get("vendeur_nom")),
        "message": "Vendeur présent"
        if is_not_empty(data.get("vendeur_nom"))
        else "Vendeur absent"
    })

    if data.get("prix_vente") is not None:
        valid = is_positive_number(data["prix_vente"])
        results.append({
            "rule": "prix_vente_positif",
            "passed": valid,
            "message": "Prix de vente valide"
            if valid
            else "Prix de vente invalide"
        })

    if data.get("superficie") is not None:
        valid = is_positive_number(data["superficie"])
        results.append({
            "rule": "superficie_positive",
            "passed": valid,
            "message": "Superficie valide"
            if valid
            else "Superficie invalide"
        })

    if is_not_empty(data.get("date_signature")):
        valid = is_valid_date(data["date_signature"])
        results.append({
            "rule": "date_signature",
            "passed": valid,
            "message": "Date de signature valide"
            if valid
            else "Date de signature invalide"
        })

    return results


# =========================================================
# MAPPING
# =========================================================

RULES = {

    "carte_identite": validate_carte_identite,

    "bulletin": validate_bulletin,

    "releve": validate_releve,

    "compromis": validate_compromis
}
