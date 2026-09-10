"""Comptes clients persistants pour le prototype local Streamlit.

SQLite convient à une démonstration mono-machine. Une mise en production doit
utiliser PostgreSQL, HTTPS, un coffre à secrets et une authentification gérée.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


DB_PATH = Path(os.getenv("CREDIT_HABITAT_DB", "data/client_portal.db"))
PBKDF2_ITERATIONS = 600_000


def _connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def init_database():
    with _connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS customers (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                password_hash BLOB NOT NULL,
                password_salt BLOB NOT NULL,
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                phone TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_login_at TEXT
            );
            CREATE TABLE IF NOT EXISTS housing_projects (
                customer_id TEXT PRIMARY KEY REFERENCES customers(id) ON DELETE CASCADE,
                city TEXT,
                property_type TEXT,
                purchase_price REAL,
                contribution REAL,
                duration_years INTEGER,
                updated_at TEXT NOT NULL
                            );
            CREATE TABLE IF NOT EXISTS customer_documents (
                document_id TEXT PRIMARY KEY,
                customer_id TEXT NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
                document_type TEXT NOT NULL,
                filename TEXT NOT NULL,
                document_path TEXT,
                status TEXT NOT NULL,
                result_json TEXT,
                confirmed_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )


def _normalize_email(email):
    return str(email or "").strip().casefold()


def _password_digest(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)


def validate_password(password):
    if len(password or "") < 10:
        raise ValueError("Le mot de passe doit contenir au moins 10 caractères.")
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        raise ValueError("Le mot de passe doit contenir au moins une lettre et un chiffre.")


def create_customer(email, password, first_name, last_name, phone):
    email = _normalize_email(email)
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise ValueError("Adresse e-mail invalide.")
    validate_password(password)
    if not all(str(value or "").strip() for value in (first_name, last_name, phone)):
        raise ValueError("Prénom, nom et téléphone sont obligatoires.")
    customer_id = str(uuid.uuid4())
    salt = os.urandom(16)
    digest = _password_digest(password, salt)
    now = datetime.now(timezone.utc).isoformat()
    try:
        with _connection() as connection:
            connection.execute(
                """INSERT INTO customers
                   (id,email,password_hash,password_salt,first_name,last_name,phone,created_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (customer_id, email, digest, salt, first_name.strip(), last_name.strip(), phone.strip(), now),
            )
    except sqlite3.IntegrityError as exc:
        raise ValueError("Un compte existe déjà avec cette adresse e-mail.") from exc
    return get_customer(customer_id)


def authenticate(email, password):
    with _connection() as connection:
        row = connection.execute(
            "SELECT * FROM customers WHERE email = ?", (_normalize_email(email),)
        ).fetchone()
        if row is None or not hmac.compare_digest(
            bytes(row["password_hash"]), _password_digest(password or "", bytes(row["password_salt"]))
        ):
            return None
        connection.execute(
            "UPDATE customers SET last_login_at = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), row["id"]),
        )
    return get_customer(row["id"])


def get_customer(customer_id):
    with _connection() as connection:
        row = connection.execute(
            "SELECT id,email,first_name,last_name,phone,created_at,last_login_at FROM customers WHERE id = ?",
            (customer_id,),
        ).fetchone()
    return dict(row) if row else None


def save_project(customer_id, city, property_type, purchase_price, contribution, duration_years):
    now = datetime.now(timezone.utc).isoformat()
    with _connection() as connection:
        connection.execute(
            """INSERT INTO housing_projects
               (customer_id,city,property_type,purchase_price,contribution,duration_years,updated_at)
               VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(customer_id) DO UPDATE SET
               city=excluded.city, property_type=excluded.property_type,
               purchase_price=excluded.purchase_price, contribution=excluded.contribution,
               duration_years=excluded.duration_years, updated_at=excluded.updated_at""",
            (customer_id, city, property_type, purchase_price, contribution, duration_years, now),
        )


def load_project(customer_id):
    with _connection() as connection:
        row = connection.execute(
            "SELECT * FROM housing_projects WHERE customer_id = ?", (customer_id,)
        ).fetchone()
    return dict(row) if row else None


def save_document(customer_id, document_id, document):
    now = datetime.now(timezone.utc).isoformat()
    payload = json.dumps(document.get("result"), ensure_ascii=False, default=str)
    confirmed = json.dumps(document.get("confirmed_fields") or {}, ensure_ascii=False, default=str)
    with _connection() as connection:
        connection.execute(
            """INSERT INTO customer_documents
               (document_id,customer_id,document_type,filename,document_path,status,
                result_json,confirmed_json,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(document_id) DO UPDATE SET
               status=excluded.status, result_json=excluded.result_json,
               confirmed_json=excluded.confirmed_json, document_path=excluded.document_path,
               updated_at=excluded.updated_at""",
            (document_id, customer_id, document.get("type"), document.get("filename") or "Document",
             document.get("document_path"), document.get("status") or "processing", payload,
             confirmed, document.get("timestamp") or now, now),
        )


def load_documents(customer_id):
    with _connection() as connection:
        rows = connection.execute(
            "SELECT * FROM customer_documents WHERE customer_id = ? ORDER BY created_at DESC",
            (customer_id,),
        ).fetchall()
    documents = {}
    for row in rows:
        documents[row["document_id"]] = {
            "client_id": customer_id, "type": row["document_type"],
            "filename": row["filename"], "document_path": row["document_path"],
            "status": row["status"], "result": json.loads(row["result_json"] or "null"),
            "confirmed_fields": json.loads(row["confirmed_json"] or "{}"),
            "timestamp": row["created_at"],
        }
    return documents


def delete_document(customer_id, document_id):
    with _connection() as connection:
        connection.execute(
            "DELETE FROM customer_documents WHERE customer_id = ? AND document_id = ?",
            (customer_id, document_id),
        )


def delete_all_documents(customer_id):
    """Supprime les justificatifs persistés et retourne leurs chemins de fichiers.

    Le compte client et le projet immobilier sont volontairement conservés. Les
    chemins sont renvoyés pour permettre à l'interface de supprimer ensuite les
    fichiers physiques uniquement s'ils se trouvent dans ``data/uploads``.
    """
    with _connection() as connection:
        rows = connection.execute(
            "SELECT document_path FROM customer_documents WHERE customer_id = ?",
            (customer_id,),
        ).fetchall()
        connection.execute(
            "DELETE FROM customer_documents WHERE customer_id = ?",
            (customer_id,),
        )
    return [row["document_path"] for row in rows if row["document_path"]]


init_database()
