"""User persistence (multi-user, August 2026).

A user row is created at invite time; the invite token is the durable login
credential (see ``models.User``). Tokens are random ``secrets.token_urlsafe``
strings stored verbatim — they are capability URLs, not passwords, and the
admin needs to read them back out to re-send a link.
"""

from __future__ import annotations

import secrets
import sqlite3
from datetime import UTC, datetime

from foghorn.models import User

_COLUMNS = "id, display_name, email, invite_token, is_admin, disabled, created_at, claimed_at"


def _row_to_user(row: sqlite3.Row) -> User:
    return User(
        id=row["id"],
        display_name=row["display_name"],
        email=row["email"],
        invite_token=row["invite_token"],
        is_admin=bool(row["is_admin"]),
        disabled=bool(row["disabled"]),
        created_at=row["created_at"],
        claimed_at=row["claimed_at"],
    )


def get_by_id(conn: sqlite3.Connection, user_id: int) -> User | None:
    row = conn.execute(
        f"SELECT {_COLUMNS} FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    return _row_to_user(row) if row is not None else None


def get_by_invite_token(conn: sqlite3.Connection, token: str) -> User | None:
    row = conn.execute(
        f"SELECT {_COLUMNS} FROM users WHERE invite_token = ?", (token,)
    ).fetchone()
    return _row_to_user(row) if row is not None else None


def list_all(conn: sqlite3.Connection) -> list[User]:
    rows = conn.execute(f"SELECT {_COLUMNS} FROM users ORDER BY id").fetchall()
    return [_row_to_user(row) for row in rows]


def create_invite(
    conn: sqlite3.Connection, display_name: str, *, is_admin: bool = False
) -> User:
    """Create an unclaimed user with a fresh invite token."""
    created_at = datetime.now(UTC).isoformat()
    token = secrets.token_urlsafe(24)
    cursor = conn.execute(
        "INSERT INTO users (display_name, invite_token, is_admin, created_at) "
        "VALUES (?, ?, ?, ?)",
        (display_name, token, int(is_admin), created_at),
    )
    conn.commit()
    assert cursor.lastrowid is not None
    return User(
        id=cursor.lastrowid,
        display_name=display_name,
        invite_token=token,
        is_admin=is_admin,
        created_at=created_at,
    )


def claim(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    display_name: str | None = None,
    email: str | None = None,
) -> User:
    """Record an invite-link use: stamp ``claimed_at`` on first open and apply
    any name/email the claimant provided. Later opens (link-as-login) leave
    ``claimed_at`` alone but may still update the optional fields."""
    user = get_by_id(conn, user_id)
    assert user is not None
    if user.claimed_at is None:
        conn.execute(
            "UPDATE users SET claimed_at = ? WHERE id = ?",
            (datetime.now(UTC).isoformat(), user_id),
        )
    if display_name is not None and display_name.strip():
        conn.execute(
            "UPDATE users SET display_name = ? WHERE id = ?",
            (display_name.strip(), user_id),
        )
    if email is not None and email.strip():
        conn.execute(
            "UPDATE users SET email = ? WHERE id = ?", (email.strip(), user_id)
        )
    conn.commit()
    refreshed = get_by_id(conn, user_id)
    assert refreshed is not None
    return refreshed


def regenerate_token(conn: sqlite3.Connection, user_id: int) -> User:
    """Issue a new invite/login token, invalidating the old link (existing
    sessions are untouched — revoke those via ``disabled`` instead)."""
    token = secrets.token_urlsafe(24)
    conn.execute("UPDATE users SET invite_token = ? WHERE id = ?", (token, user_id))
    conn.commit()
    user = get_by_id(conn, user_id)
    assert user is not None
    return user


def set_disabled(conn: sqlite3.Connection, user_id: int, disabled: bool) -> User:
    """Disable (or re-enable) an account. Disabling also drops the user's
    sessions so open browsers are signed out, not just new logins blocked."""
    conn.execute(
        "UPDATE users SET disabled = ? WHERE id = ?", (int(disabled), user_id)
    )
    if disabled:
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    conn.commit()
    user = get_by_id(conn, user_id)
    assert user is not None
    return user
