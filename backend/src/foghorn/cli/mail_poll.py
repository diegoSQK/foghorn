"""`make mail-poll`: fetch labeled newsletter emails into the review queue.

Reads the ``FOGHORN_IMAP_*`` environment (see ``mailingest.poller``); when
it's not configured this prints how to set it and exits 0 — a cron line stays
quiet-green on machines without credentials. Not on the in-process scheduler
yet (stage 1 is manual/cron).
"""

from __future__ import annotations

from foghorn.mailingest.poller import DEFAULT_FOLDER, imap_config_from_env, poll
from foghorn.repo import db


def main() -> None:
    config = imap_config_from_env()
    if config is None:
        print(
            "IMAP polling skipped: set FOGHORN_IMAP_HOST, FOGHORN_IMAP_USER, and "
            "FOGHORN_IMAP_PASSWORD (an app password), plus optionally "
            f"FOGHORN_IMAP_FOLDER (default {DEFAULT_FOLDER!r} — the Gmail label "
            "your artist newsletters are filtered into)."
        )
        return
    conn = db.connect()
    try:
        result = poll(conn, config)
    finally:
        conn.close()
    print(
        f"{config.folder}: fetched={result.fetched} "
        f"created={result.created} skipped={result.skipped}"
    )
    if result.created:
        print("Review new drafts at http://localhost:3000/inbox")


if __name__ == "__main__":
    main()
