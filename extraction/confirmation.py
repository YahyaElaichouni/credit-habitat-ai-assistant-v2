"""Validation humaine typée et export des seules valeurs confirmées.

Ce module ne dépend ni de Streamlit, ni d'Ollama : les mêmes contrôles
peuvent être réutilisés dans une future API.
"""

import csv
import io
import json
import math
from datetime import date, datetime, timezone
from typing import get_args, get_origin

from pydantic import TypeAdapter

from extraction.schema import DOCUMENT_SCHEMAS, ExtractedField


REQUIRED_FIELDS = {
    "bulletin": ("employeur", "salaire_net", "date_embauche"),
    "releve": ("charge_mensuelle_credits",),
    "carte_identite": ("nom", "prenom", "date_naissance"),
    "compromis": (),
}
DATE_FIELDS = {"date_embauche", "date_naissance", "date_expiration", "periode_debut",
               "periode_fin", "date_signature"}


def parse_confirmed_value(document_type, field_name, value):
    schema = DOCUMENT_SCHEMAS[document_type]
    if field_name == "document_type" or field_name not in schema.model_fields:
        raise ValueError("Champ non modifiable")
    annotation = schema.model_fields[field_name].annotation
    if isinstance(annotation, type) and issubclass(annotation, ExtractedField):
        annotation = annotation.model_fields["value"].annotation
    if isinstance(value, str):
        value = value.strip()
        if not value:
            value = None
    if value is None:
        if field_name in REQUIRED_FIELDS[document_type]:
            raise ValueError("Champ obligatoire : renseignez une valeur avant confirmation")
        return None
    if isinstance(value, bool):
        raise ValueError("Valeur booléenne non autorisée")
    if float in get_args(annotation) or annotation is float:
        if isinstance(value, str):
            value = value.replace("\u202f", "").replace("\u00a0", "").replace(" ", "").replace(",", ".")
        value = float(value)
        if not math.isfinite(value):
            raise ValueError("Le montant doit être fini")
        if field_name not in ("solde_initial", "solde_final") and value < 0:
            raise ValueError("Le montant doit être positif ou nul")
    elif get_origin(annotation) is list and isinstance(value, str):
        value = json.loads(value)
    if field_name in DATE_FIELDS:
        parsed = None
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                parsed = datetime.strptime(str(value), fmt).date()
                break
            except ValueError:
                pass
        if parsed is None:
            raise ValueError("Date invalide : utilisez JJ/MM/AAAA ou AAAA-MM-JJ")
        if field_name in ("date_embauche", "date_naissance", "date_signature") and parsed > date.today():
            raise ValueError("Cette date ne peut pas être dans le futur")
        value = parsed.isoformat()
    adapter = TypeAdapter(annotation)
    return adapter.dump_python(adapter.validate_python(value), mode="json")


def make_confirmation(document_type, field_name, edited_value, decision, *,
                      document_id, advisor_id, source_checked=False):
    if not advisor_id or not advisor_id.strip():
        raise ValueError("Identifiant de l'utilisateur obligatoire")
    if not source_checked:
        raise ValueError("Vérifiez le document et cochez la confirmation humaine")
    value = parse_confirmed_value(document_type, field_name, edited_value)
    original = decision.get("value")
    try:
        normalized_original = parse_confirmed_value(document_type, field_name, original)
    except (ValueError, TypeError):
        normalized_original = original
    return {
        "value": value,
        "original_value": original,
        "status": "corrige" if value != normalized_original else "confirme",
        "document_id": document_id,
        "advisor_id": advisor_id.strip(),
        "confirmed_at": datetime.now(timezone.utc).isoformat(),
        "source_checked": True,
        "source": decision.get("source"),
    }


def _csv_cell(value):
    if isinstance(value, (list, dict)):
        value = json.dumps(value, ensure_ascii=False)
    # Empêche l'interprétation de contenu documentaire comme formule Excel.
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        value = "'" + value
    return value


def export_confirmed_csv(result, document_type, confirmations, document_id):
    fields = result.get("validation_result", {}).get("fields", {})
    rows = []
    for name, decision in fields.items():
        record = confirmations.get(name)
        # Les anciennes sessions stockaient des valeurs sans preuve de confirmation.
        # Elles doivent être reconfirmées, jamais promues implicitement.
        if not isinstance(record, dict) or record.get("document_id") != document_id:
            continue
        if record.get("status") not in ("confirme", "corrige") or not record.get("source_checked"):
            continue
        if not record.get("advisor_id") or not record.get("confirmed_at"):
            continue
        value = parse_confirmed_value(document_type, name, record.get("value"))
        source = record.get("source") or {}
        rows.append({
            "Document ID": document_id, "Type document": document_type,
            "Champ": name, "Valeur finale": value, "Statut humain": record["status"],
            "Valeur extraite initiale": record.get("original_value"),
            "Utilisateur": record["advisor_id"], "Confirmation UTC": record["confirmed_at"],
            "Document source": source.get("document"), "SHA256": source.get("sha256"),
            "Page": source.get("page"), "Extrait": source.get("quote"),
            "Citation retrouvee": source.get("verified", False),
        })
    if not rows:
        return None
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows({k: _csv_cell(v) for k, v in row.items()} for row in rows)
    return buffer.getvalue().encode("utf-8-sig")
