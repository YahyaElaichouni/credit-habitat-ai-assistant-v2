"""Décodage déterministe de secours pour la MRZ d'une CNIE marocaine."""
import re
from datetime import date, datetime


PAGE_RE = re.compile(r"\[PAGE\s+(\d+)\]\s*(.*?)(?=\[PAGE\s+\d+\]|$)", re.DOTALL)


def _date_from_mrz(value, birth=False):
    try:
        parsed = datetime.strptime(value, "%y%m%d").date()
    except ValueError:
        return None
    if birth:
        current = date.today().year % 100
        year = 1900 + int(value[:2]) if int(value[:2]) > current else 2000 + int(value[:2])
    else:
        year = 2000 + int(value[:2])
    try:
        return date(year, parsed.month, parsed.day).strftime("%d/%m/%Y")
    except ValueError:
        return None


def _field(value, page, quote, confidence=0.80):
    return {
        "value": value,
        "confidence": confidence,
        "source": {"page": page, "quote": quote.strip()},
    }


def _split_names(raw_names):
    """Séparer nom/prénom malgré des chevrons lus comme C ou antislash."""
    # Initialisation explicite : la variable reste définie même si un futur
    # nettoyage ajoute une branche anticipée dans cette fonction.
    c_as_separator = False
    names = raw_names.upper().replace("\\", "<")
    names = re.split(r"\d", names, maxsplit=1)[0]
    names = re.sub(r"[<C]+$", "", names).strip("<")
    c_as_separator = "<<" not in names and "CC" in names
    if c_as_separator:
        names = names.replace("CC", "<<", 1)
    separators = list(re.finditer(r"<{2,}", names))
    if not separators:
        return None, None

    # Le dernier séparateur long conserve les noms composés :
    # EL<<AISHOUNI<<<AHMED devient EL AISHOUNI / AHMED.
    separator = separators[-1]
    surname = re.sub(r"<+", " ", names[:separator.start()]).strip()
    given_pattern = r"[<C]+" if c_as_separator else r"<+"
    given = re.sub(given_pattern, " ", names[separator.end():]).strip()
    return surname or None, given or None


def extract_visible_identity(ocr_text):
    """Extraire les champs explicitement libellés hors de la zone MRZ."""
    result = {}
    for page_text_number, page_text in PAGE_RE.findall(str(ocr_text or "")):
        page = int(page_text_number)
        lines = [line.strip() for line in page_text.splitlines() if line.strip()]
        # La reconstruction OCR peut aplatir la page : on conserve alors la
        # page entière comme citation exacte plutôt que d'inventer un extrait.
        candidates = lines or [page_text.strip()]
        for raw in candidates:
            upper = raw.upper()
            cin_match = re.search(
                r"(?:\bCIN\b|\bCNIE\b|N\s*[°ºO]?)[\s:.-]*([A-Z]{1,2}\s*\d{5,8})",
                upper,
            )
            if cin_match:
                cin = re.sub(r"\s+", "", cin_match.group(1))
                result["cin"] = _field(cin, page, raw, 0.86)

            address_match = re.search(
                # Tolère les lectures OCR « Adres », « Adress », « Adresse ».
                r"\bADRES{1,2}E?\b[\s:|.-]+(.+?)(?=\s+IDMAR|$)",
                raw,
                re.IGNORECASE,
            )
            if address_match:
                address = re.sub(r"\s+", " ", address_match.group(1)).strip(" -:.,")
                if len(address) >= 8:
                    result["adresse"] = _field(address, page, raw, 0.74)

            place_match = re.search(
                r"(?:N[ÉE]E?\s+À|N[ÉE]E?\s+A|LIEU\s+DE\s+NAISSANCE|\bÀ)"
                r"[\s:.-]+([A-Z][A-Z '\\-]{2,30})",
                upper,
            )
            if place_match:
                place = re.sub(r"\s+", " ", place_match.group(1)).strip(" -:.,")
                if place not in {"MAROC", "CARTE NATIONALE D IDENTITE"}:
                    result["lieu_naissance"] = _field(place, page, raw, 0.72)

        # Secours pour un OCR entièrement aplati, avec priorité au N° imprimé.
        if "cin" not in result:
            flat_match = re.search(
                r"(?:\bCIN\b|\bCNIE\b|N\s*[°ºO])\s*([A-Z]{1,2}\d{5,8})",
                page_text.upper(),
            )
            if flat_match:
                result["cin"] = _field(flat_match.group(1), page, page_text.strip(), 0.82)

        if "adresse" not in result:
            # Secours prudent lorsque le mot Adresse est perdu mais que la fin
            # de la ligne contient encore un motif postal clair avant IDMAR.
            flat_address = re.search(
                r"(\d{1,4}(?:\s+[A-Z]+){0,8}\s+(?:APPT|APT)\s+\d+"
                r"(?:\s+[A-Z]+){1,4})\s+IDMAR",
                page_text.upper(),
            )
            if flat_address:
                result["adresse"] = _field(
                    re.sub(r"\s+", " ", flat_address.group(1)).strip(),
                    page,
                    page_text.strip(),
                    0.58,
                )

        # Sur le recto marocain, le prénom et le nom sont immédiatement
        # suivis de « Né(e) le ». Cette preuve visuelle corrige une MRZ où
        # I/1, O/0 ou CH/6 ont été confondus.
        visible_names = re.search(
            r"(?:^|\s)(?:\d{1,4}\s+)?"
            r"([A-ZÀ-ÖØ-Þ][A-ZÀ-ÖØ-Þ'\-]{1,30})\s+"
            r"((?:EL\s+)?[A-ZÀ-ÖØ-Þ][A-ZÀ-ÖØ-Þ'\-]{1,40})\s+"
            r"N[ÉEÈ]E?\s+LE\b",
            page_text.upper(),
        )
        if visible_names:
            result["prenom"] = _field(
                visible_names.group(1), page, page_text.strip(), 0.82
            )
            result["nom"] = _field(
                visible_names.group(2), page, page_text.strip(), 0.82
            )
    return result


def extract_mrz_identity(ocr_text):
    """Extraire les informations MRZ même si les trois lignes sont aplaties."""
    result = {}
    for page_text_number, page_text in PAGE_RE.findall(str(ocr_text or "")):
        page = int(page_text_number)
        raw_lines = [line.strip() for line in page_text.splitlines() if line.strip()]
        compact_lines = [re.sub(r"[^A-Z0-9<\\]", "", line.upper()) for line in raw_lines]
        compact_page = re.sub(r"[^A-Z0-9<\\]", "", page_text.upper()).replace("\\", "<")
        id_position = compact_page.find("IDMAR")
        if id_position < 0:
            continue

        mrz = compact_page[id_position:]
        page_quote = page_text.strip()
        id_line_index = next((i for i, line in enumerate(compact_lines) if "IDMAR" in line), None)
        first_raw = raw_lines[id_line_index] if id_line_index is not None else page_quote
        first = compact_lines[id_line_index].replace("\\", "<") if id_line_index is not None else mrz[:45]

        match = re.search(r"(\d{6})\d?([MF])(\d{6})\d?MAR", mrz)
        if not match:
            continue

        # Limiter la recherche du CIN à la première ligne MRZ. Sinon, sur
        # un OCR aplati, la séquence sexe+expiration (M3204201) pourrait être
        # prise à tort pour un numéro de carte.
        first_zone = mrz[:match.start()]
        candidates = re.findall(r"([A-Z]{1,2}\d{5,8})", first_zone)
        if candidates:
            result["cin"] = _field(candidates[-1], page, first_raw, 0.68)
        second_raw = next(
            (raw_lines[i] for i, line in enumerate(compact_lines)
             if re.search(r"(\d{6})\d?([MF])(\d{6})\d?MAR", line)),
            page_quote,
        )
        birth = _date_from_mrz(match.group(1), birth=True)
        expiry = _date_from_mrz(match.group(3), birth=False)
        if birth:
            result["date_naissance"] = _field(birth, page, second_raw)
        result["sexe"] = _field(match.group(2), page, second_raw)
        if expiry:
            result["date_expiration"] = _field(expiry, page, second_raw)
        tail = mrz[match.end():]
        tail = re.sub(r"^[<C]*\d?", "", tail)
        surname, given = _split_names(tail)
        name_raw = next(
            (raw_lines[i] for i in range(len(raw_lines) - 1, -1, -1)
             if "<<" in compact_lines[i].replace("\\", "<") or "CC" in compact_lines[i]),
            page_quote,
        )
        if surname:
            result["nom"] = _field(surname, page, name_raw, 0.68)
        if given:
            result["prenom"] = _field(given, page, name_raw, 0.68)
    return result


def fill_missing_identity_fields(data, ocr_text):
    """Préférer les preuves déterministes aux associations libres du LLM."""
    enriched = dict(data or {})
    proposals = extract_mrz_identity(ocr_text)
    # Une valeur imprimée avec un libellé explicite est prioritaire sur une
    # MRZ incomplète ou mal reconnue.
    proposals.update(extract_visible_identity(ocr_text))
    deterministic_fields = {
        "cin", "nom", "prenom", "date_naissance", "date_expiration",
        "sexe", "adresse",
    }
    for name, proposed in proposals.items():
        current = enriched.get(name)
        current_value = current.get("value") if isinstance(current, dict) else None
        if name in deterministic_fields or current_value in (None, "", []):
            enriched[name] = proposed
    return enriched
