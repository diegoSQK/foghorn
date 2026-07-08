"""Load `backend/.env` (gitignored local secrets) into the environment.

foghorn's config is plain environment variables; this shim lets a checkout
carry its secrets in a gitignored file instead of requiring every shell and
service to export them. KEY=VALUE lines only (# comments and an optional
`export ` prefix allowed); real environment variables always win.
"""

from __future__ import annotations

import os
from pathlib import Path

# src/foghorn/localenv.py -> backend/
_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
_loaded = False


def load_local_env() -> None:
    """Idempotently merge backend/.env into os.environ (existing vars win)."""
    global _loaded
    if _loaded:
        return
    _loaded = True
    if not _ENV_PATH.is_file():
        return
    for line in _ENV_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
