"""Connection handling for the SQLite store.

One seam, two callers: the app opens the default DB (path overridable via
``FOGHORN_DB_PATH``); tests pass an explicit path (a tmp file or ``":memory:"``).
Every connection gets ``Row`` access, foreign-key enforcement, and the schema
bootstrapped before it's handed back.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from foghorn.repo import schema

# Default location: <backend>/foghorn.db (gitignored). Overridable for ops /
# alternate environments via FOGHORN_DB_PATH.
_BACKEND_DIR = Path(__file__).resolve().parents[3]
DEFAULT_DB_PATH = Path(os.environ.get("FOGHORN_DB_PATH", _BACKEND_DIR / "foghorn.db"))


def connect(db_path: str | os.PathLike[str] | None = None) -> sqlite3.Connection:
    """Open a connection with row access + FK enforcement, schema ensured.

    Pass ``":memory:"`` or a tmp path in tests; pass nothing in app code to use
    ``DEFAULT_DB_PATH``.
    """
    target: str | os.PathLike[str] = DEFAULT_DB_PATH if db_path is None else db_path
    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    # FK enforcement is per-connection in SQLite and off by default.
    conn.execute("PRAGMA foreign_keys = ON")
    schema.init_schema(conn)
    return conn
