"""
===========================================================
Journal d'audit
Projet PFE Crédit Agricole du Maroc
===========================================================

EB-228 : traçabilité de chaque décision — qui, quand, sur quel
document, quel champ, quelle valeur, quelle décision.

Table dédiée, séparée des données métier, append-only :
volontairement, ce module n'expose AUCUNE fonction d'update ou
de delete. Une correction ne remplace jamais une entrée passée,
elle s'ajoute comme un nouvel événement — l'historique complet
reste consultable tel quel.
"""

import json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from config.settings import settings

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    advisor_id TEXT,
    session_id TEXT,
    document_path TEXT,
    document_type TEXT,
    event_type TEXT NOT NULL,
    field_name TEXT,
    value TEXT,
    decision TEXT,
    details TEXT
);
"""


# =========================================================
# CONNEXION
# =========================================================

def get_connection() -> sqlite3.Connection:

    db_path = settings.database_path
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(
        db_path,
        check_same_thread=False,
        timeout=10,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def init_audit_table() -> None:
    conn = get_connection()
    try:
        conn.execute(_SCHEMA)
        conn.commit()
    finally:
        conn.close()


# =========================================================
# ECRITURE (append-only)
# =========================================================

def log_event(
    event_type: str,
    advisor_id: Optional[str] = None,
    session_id: Optional[str] = None,
    document_path: Optional[str] = None,
    document_type: Optional[str] = None,
    field_name: Optional[str] = None,
    value: Any = None,
    decision: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    strict: bool = False,
) -> None:
    """Insertion append-only dans le journal.

    Une erreur d'écriture du journal n'interrompt jamais le
    pipeline métier (elle est logguée via `logging`, pas relancée) :
    perdre une entrée d'audit est regrettable, mais bloquer un
    conseiller en pleine consultation client à cause d'un souci
    d'écriture SQLite serait pire. À revoir si le projet passe en
    production réelle (alerte explicite plutôt que log silencieux).
    """

    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO audit_log (
                timestamp, advisor_id, session_id, document_path,
                document_type, event_type, field_name, value,
                decision, details
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now(timezone.utc).isoformat(),
                advisor_id,
                session_id,
                document_path,
                document_type,
                event_type,
                field_name,
                _to_json(value),
                decision,
                _to_json(details),
            ),
        )
        conn.commit()
    except Exception:
        logger.exception("[Audit] Échec de l'écriture du journal")
        if strict:
            raise
    finally:
        conn.close()


def _to_json(value: Any) -> Optional[str]:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, default=str)


# =========================================================
# RACCOURCIS PAR TYPE D'EVENEMENT
# =========================================================

def log_document_rejected(
    document_path: str,
    reason: str,
    advisor_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> None:
    log_event(
        event_type="document_rejected",
        advisor_id=advisor_id,
        session_id=session_id,
        document_path=document_path,
        decision="rejeté",
        details={"reason": reason},
    )


def log_security_flag(
    document_path: str,
    document_type: str,
    matched_patterns: List[str],
    advisor_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> None:
    log_event(
        event_type="security_flag",
        advisor_id=advisor_id,
        session_id=session_id,
        document_path=document_path,
        document_type=document_type,
        decision="revue_prioritaire",
        details={"matched_patterns": matched_patterns},
    )


def log_field_decision(
    document_path: str,
    document_type: str,
    field_name: str,
    value: Any,
    status: str,
    reasons: List[str],
    advisor_id: Optional[str] = None,
    session_id: Optional[str] = None,
    source: Optional[Dict[str, Any]] = None,
) -> None:
    log_event(
        event_type="field_decision",
        advisor_id=advisor_id,
        session_id=session_id,
        document_path=document_path,
        document_type=document_type,
        field_name=field_name,
        value=value,
        decision=status,  # "pre_rempli" | "signale" | "absent"
        details={"reasons": reasons, "source": source},
    )


def log_chat_interaction(
    question: str,
    answer: str,
    in_scope: bool,
    sources: List[str],
    advisor_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> None:
    """Trace chaque échange avec l'assistant conversationnel (EB-228
    s'applique aussi au RAG, pas seulement à l'extraction) : la
    question posée, si elle a été jugée dans le périmètre, la
    réponse donnée et les sources citées."""

    log_event(
        event_type="chat_interaction",
        advisor_id=advisor_id,
        session_id=session_id,
        decision="dans_perimetre" if in_scope else "hors_perimetre",
        value=answer,
        details={"question": question, "sources": sources},
    )


def log_human_confirmation(
    document_path: str,
    document_type: str,
    field_name: str,
    confirmed_value: Any,
    advisor_id: str,
    session_id: Optional[str] = None,
    original_value: Any = None,
    source: Optional[Dict[str, Any]] = None,
    confirmation_status: Optional[str] = None,
) -> None:
    """À appeler depuis l'interface, quand un conseiller confirme ou
    corrige manuellement un champ (EB-106 : rien n'est validé sans
    ce type d'événement).

    Si `original_value` est fourni et diffère de `confirmed_value`,
    l'événement est journalisé comme une correction plutôt qu'une
    simple confirmation — utile pour mesurer, a posteriori, le taux
    réel de champs corrigés par les conseillers (indicateur de
    fiabilité de l'extraction, cf. section 9 du cahier des charges)."""

    was_corrected = (confirmation_status == "corrige" if confirmation_status
                     else confirmed_value != original_value)

    log_event(
        event_type="human_confirmation",
        advisor_id=advisor_id,
        session_id=session_id,
        document_path=document_path,
        document_type=document_type,
        field_name=field_name,
        value=confirmed_value,
        decision="corrigé_par_humain" if was_corrected else "confirmé_par_humain",
        details={"valeur_extraite_initiale": original_value, "source": source},
        strict=True,
    )


# =========================================================
# LECTURE (consultation uniquement — pas d'update/delete exposé)
# =========================================================

def get_audit_trail(
    document_path: Optional[str] = None,
    session_id: Optional[str] = None,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    """Historique complet, du plus récent au plus ancien. Filtrable
    par document et/ou session. Utile pour une vue "traçabilité"
    dans l'interface, ou pour répondre à un audit externe."""

    conn = get_connection()
    try:
        query = "SELECT * FROM audit_log WHERE 1=1"
        params: List[Any] = []

        if document_path is not None:
            query += " AND document_path = ?"
            params.append(document_path)

        if session_id is not None:
            query += " AND session_id = ?"
            params.append(session_id)

        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()
