"""Provenance établie côté serveur ; une citation retrouvée n'est pas une
preuve de l'exactitude sémantique de la valeur. La confirmation reste requise.
"""

import re
from pathlib import Path


def page_text(pages):
    return "\n\n".join(f"[PAGE {p['page']}]\n{p['text']}" for p in pages)


def _normalize(text):
    return re.sub(r"\s+", " ", str(text)).strip().casefold()


def verify_sources(raw, pages, document_path, document_sha256):
    """Ne jamais accepter un nom de fichier/hash/flag fourni par le LLM."""
    page_map = {p["page"]: p["text"] for p in pages}
    sources = {}
    for name, field in raw.items():
        if not isinstance(field, dict) or "value" not in field:
            continue
        evidence = field.get("source") or {}
        page = evidence.get("page")
        quote = evidence.get("quote")
        verified = bool(
            field.get("value") is not None
            and type(page) is int
            and page in page_map
            and isinstance(quote, str)
            and _normalize(quote)
            and _normalize(quote) in _normalize(page_map[page])
        )
        sources[name] = {
            "document": Path(document_path).name if document_path else None,
            "sha256": document_sha256,
            "page": page if verified else None,
            "quote": quote if verified else None,
            "verified": verified,
        }
    return sources
