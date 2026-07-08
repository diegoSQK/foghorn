"""Mail-sender persistence (Phase 8): the From-address → artist mapping the
mailing-list parser prefills drafts from.

Keyed on the lowercased email address. Single-tenant, tiny (one row per
followed artist's newsletter), managed through ``/api/inbox/senders``.
"""

from __future__ import annotations

import sqlite3

from foghorn.models import MailSender


def _row_to_sender(row: sqlite3.Row) -> MailSender:
    return MailSender(email=row["email"], artist_display=row["artist_display"])


def list_all(conn: sqlite3.Connection) -> list[MailSender]:
    rows = conn.execute(
        "SELECT email, artist_display FROM mail_senders ORDER BY email"
    ).fetchall()
    return [_row_to_sender(row) for row in rows]


def get(conn: sqlite3.Connection, email: str) -> MailSender | None:
    row = conn.execute(
        "SELECT email, artist_display FROM mail_senders WHERE email = ?",
        (email.strip().lower(),),
    ).fetchone()
    return _row_to_sender(row) if row is not None else None


def upsert(conn: sqlite3.Connection, email: str, artist_display: str) -> MailSender:
    """Insert or update a mapping keyed on the lowercased address."""
    normalized = email.strip().lower()
    conn.execute(
        "INSERT INTO mail_senders (email, artist_display) VALUES (?, ?) "
        "ON CONFLICT(email) DO UPDATE SET artist_display = excluded.artist_display",
        (normalized, artist_display),
    )
    conn.commit()
    stored = get(conn, normalized)
    assert stored is not None  # just inserted/updated
    return stored


def remove(conn: sqlite3.Connection, email: str) -> bool:
    """Delete a mapping; return True if a row was removed."""
    cursor = conn.execute(
        "DELETE FROM mail_senders WHERE email = ?", (email.strip().lower(),)
    )
    conn.commit()
    return cursor.rowcount > 0
