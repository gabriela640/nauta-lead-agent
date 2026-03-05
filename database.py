import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Optional

import os as _os
DB_PATH = _os.getenv("DB_PATH", "leads.db")


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS leads (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                email                   TEXT,
                linkedin_url            TEXT,
                first_name              TEXT,
                last_name               TEXT,
                job_title               TEXT,
                company_name            TEXT,
                company_website         TEXT,
                company_industry        TEXT,
                company_employee_count  INTEGER,
                company_revenue         TEXT,
                company_location        TEXT,
                page_visited            TEXT,
                classification          TEXT,
                intent_level            TEXT,
                reasons_json            TEXT,
                initial_email_subject   TEXT,
                initial_email_body      TEXT,
                status                  TEXT NOT NULL DEFAULT 'pending_review',
                email_sent_at           TEXT,
                follow_up_1_sent_at     TEXT,
                follow_up_2_sent_at     TEXT,
                follow_up_3_sent_at     TEXT,
                replied_at              TEXT,
                created_at              TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at              TEXT NOT NULL DEFAULT (datetime('now')),
                raw_payload_json        TEXT
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_leads_email
                ON leads (email) WHERE email IS NOT NULL;

            CREATE INDEX IF NOT EXISTS idx_leads_linkedin
                ON leads (linkedin_url) WHERE linkedin_url IS NOT NULL;

            CREATE INDEX IF NOT EXISTS idx_leads_status
                ON leads (status);

            CREATE TABLE IF NOT EXISTS emails_sent (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id     INTEGER NOT NULL REFERENCES leads(id),
                email_type  TEXT NOT NULL,
                recipient   TEXT,
                subject     TEXT,
                body        TEXT,
                sent_at     TEXT NOT NULL DEFAULT (datetime('now')),
                success     INTEGER NOT NULL DEFAULT 1
            );

            CREATE INDEX IF NOT EXISTS idx_emails_lead_id
                ON emails_sent (lead_id);
        """)
    print("[DB] Database initialized.")


def find_duplicate(email: Optional[str], linkedin_url: Optional[str]) -> Optional[int]:
    """Return lead_id if a duplicate exists, else None."""
    with get_conn() as conn:
        if email:
            row = conn.execute(
                "SELECT id FROM leads WHERE email = ?", (email,)
            ).fetchone()
            if row:
                return row["id"]
        if linkedin_url:
            row = conn.execute(
                "SELECT id FROM leads WHERE linkedin_url = ?", (linkedin_url,)
            ).fetchone()
            if row:
                return row["id"]
    return None


def save_lead(lead: Any, result: Any, raw_payload: dict) -> int:
    """Persist a new lead and return its id."""
    with get_conn() as conn:
        cursor = conn.execute(
            """
            INSERT INTO leads (
                email, linkedin_url, first_name, last_name, job_title,
                company_name, company_website, company_industry,
                company_employee_count, company_revenue, company_location,
                page_visited, classification, intent_level, reasons_json,
                initial_email_subject, initial_email_body,
                status, raw_payload_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                lead.email,
                lead.linkedin_url,
                lead.first_name,
                lead.last_name,
                lead.job_title,
                lead.company.name,
                lead.company.website,
                lead.company.industry,
                lead.company.employee_count,
                lead.company.revenue,
                lead.company.location,
                lead.page_visited,
                result.classification,
                result.intent_level,
                json.dumps(result.reasons),
                result.email_subject,
                result.email_body,
                "pending_review",
                json.dumps(raw_payload),
            ),
        )
        return cursor.lastrowid


def update_status(lead_id: int, status: str, **timestamps):
    """Update lead status and optional timestamp fields."""
    fields = {"status": status, "updated_at": datetime.utcnow().isoformat()}
    fields.update(timestamps)

    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [lead_id]

    with get_conn() as conn:
        conn.execute(
            f"UPDATE leads SET {set_clause} WHERE id = ?", values
        )


def log_email(
    lead_id: int,
    email_type: str,
    recipient: Optional[str],
    subject: str,
    body: str,
    success: bool,
):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO emails_sent (lead_id, email_type, recipient, subject, body, success)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (lead_id, email_type, recipient, subject, body, int(success)),
        )


def get_leads(
    status: Optional[str] = None,
    classification: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> list:
    filters, params = [], []
    if status:
        filters.append("status = ?")
        params.append(status)
    if classification:
        filters.append("classification = ?")
        params.append(classification)

    where = ("WHERE " + " AND ".join(filters)) if filters else ""
    params += [limit, offset]

    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM leads {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params,
        ).fetchall()
    return [dict(r) for r in rows]


def get_lead(lead_id: int) -> Optional[dict]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
    return dict(row) if row else None


def get_lead_emails(lead_id: int) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM emails_sent WHERE lead_id = ? ORDER BY sent_at",
            (lead_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_db_stats() -> dict:
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
        by_status = conn.execute(
            "SELECT status, COUNT(*) as n FROM leads GROUP BY status"
        ).fetchall()
    return {"total": total, "by_status": {r["status"]: r["n"] for r in by_status}}
