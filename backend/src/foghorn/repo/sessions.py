"""Session persistence (multi-user, August 2026).

Opaque bearer tokens delivered as an HttpOnly cookie. Only the SHA-256 hash is
stored; the plaintext token exists only in the Set-Cookie response and the
user's browser. Expiry is rolling: any authenticated request seen more than
``_REFRESH_AFTER`` past the last bump extends the session another
``SESSION_TTL_DAYS``, so active users never expire — only a device unused for
~13 months does. (The cookie's own Max-Age matches SESSION_TTL_DAYS; browsers
cap cookie lifetime around 400 days, which is why the TTL sits just under it.)
"""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
from datetime import UTC, datetime, timedelta

from foghorn.models import User
from foghorn.repo import users as users_repo

SESSION_TTL_DAYS = 390
# Bump last_seen/expiry at most this often, to avoid a DB write per request.
_REFRESH_AFTER = timedelta(hours=1)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create(conn: sqlite3.Connection, user_id: int) -> str:
    """Create a session and return the plaintext token (never stored)."""
    token = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    conn.execute(
        "INSERT INTO sessions (token_hash, user_id, created_at, last_seen_at, expires_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            _hash(token),
            user_id,
            now.isoformat(),
            now.isoformat(),
            (now + timedelta(days=SESSION_TTL_DAYS)).isoformat(),
        ),
    )
    conn.commit()
    return token


def resolve(conn: sqlite3.Connection, token: str) -> User | None:
    """Return the live user for a session token, applying rolling refresh.
    None for unknown/expired sessions and disabled users."""
    now = datetime.now(UTC)
    row = conn.execute(
        "SELECT user_id, last_seen_at, expires_at FROM sessions WHERE token_hash = ?",
        (_hash(token),),
    ).fetchone()
    if row is None:
        return None
    if datetime.fromisoformat(row["expires_at"]) < now:
        conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_hash(token),))
        conn.commit()
        return None
    user = users_repo.get_by_id(conn, row["user_id"])
    if user is None or user.disabled:
        return None
    if now - datetime.fromisoformat(row["last_seen_at"]) > _REFRESH_AFTER:
        conn.execute(
            "UPDATE sessions SET last_seen_at = ?, expires_at = ? WHERE token_hash = ?",
            (
                now.isoformat(),
                (now + timedelta(days=SESSION_TTL_DAYS)).isoformat(),
                _hash(token),
            ),
        )
        conn.commit()
    return user


def delete(conn: sqlite3.Connection, token: str) -> None:
    conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_hash(token),))
    conn.commit()
