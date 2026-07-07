"""IMAP poller (Phase 8 stage 1): fetch artist-newsletter emails into the
review queue.

Local-first: a Gmail filter auto-labels the newsletters, and this polls that
label (an IMAP folder) with an app password from the environment —
``FOGHORN_IMAP_HOST`` / ``FOGHORN_IMAP_USER`` / ``FOGHORN_IMAP_PASSWORD``
(+ optional ``FOGHORN_IMAP_FOLDER``, default ``foghorn``). No public inbound
endpoint.

Idempotent by construction: the folder is opened read-only, every message is
fetched, and ``pending_events.add`` no-ops on a Message-ID the queue already
has — re-running never duplicates rows or mutates mailbox state. Not wired to
the scheduler yet; run ``make mail-poll`` manually or from cron.
"""

from __future__ import annotations

import datetime as dt
import email
import email.policy
import html
import imaplib
import os
import re
import sqlite3
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import parsedate_to_datetime
from typing import cast

from pydantic import BaseModel

from foghorn.mailingest.parser import parse_email
from foghorn.models import PendingEvent
from foghorn.repo import mail_senders as mail_senders_repo
from foghorn.repo import pending_events as pending_events_repo
from foghorn.repo import venues as venues_repo

DEFAULT_FOLDER = "foghorn"


@dataclass(frozen=True)
class ImapConfig:
    host: str
    user: str
    password: str
    folder: str = DEFAULT_FOLDER


def imap_config_from_env() -> ImapConfig | None:
    """Read ``FOGHORN_IMAP_*``; None (poll is skipped) unless host, user, and
    password are all set."""
    host = os.environ.get("FOGHORN_IMAP_HOST", "").strip()
    user = os.environ.get("FOGHORN_IMAP_USER", "").strip()
    password = os.environ.get("FOGHORN_IMAP_PASSWORD", "")
    if not (host and user and password):
        return None
    folder = os.environ.get("FOGHORN_IMAP_FOLDER", "").strip() or DEFAULT_FOLDER
    return ImapConfig(host=host, user=user, password=password, folder=folder)


class PollResult(BaseModel):
    fetched: int = 0  # messages seen in the folder
    created: int = 0  # new pending_events rows
    skipped: int = 0  # already-queued (or unparseable) messages


_HTML_DROP_RE = re.compile(
    r"<(script|style)\b[^>]*>.*?</\1\s*>", re.IGNORECASE | re.DOTALL
)
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(markup: str) -> str:
    """A newsletter's HTML part flattened to reviewable text (tags → spaces,
    entities unescaped, whitespace collapsed per line)."""
    without_blocks = _HTML_DROP_RE.sub(" ", markup)
    text = html.unescape(_HTML_TAG_RE.sub(" ", without_blocks))
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def extract_text(message: EmailMessage) -> str:
    """The text/plain body, falling back to the stripped HTML part."""
    plain = message.get_body(preferencelist=("plain",))
    if plain is not None:
        return str(cast(EmailMessage, plain).get_content()).strip()
    rich = message.get_body(preferencelist=("html",))
    if rich is not None:
        return _strip_html(str(cast(EmailMessage, rich).get_content())).strip()
    return ""


def _received_at(message: EmailMessage) -> str:
    """The Date: header as ISO UTC; now() when absent/unparseable."""
    raw = message.get("Date")
    if raw:
        try:
            return parsedate_to_datetime(raw).astimezone(dt.UTC).isoformat()
        except ValueError:
            pass
    return dt.datetime.now(dt.UTC).isoformat()


def process_message(
    conn: sqlite3.Connection, raw: bytes, today: dt.date | None = None
) -> PendingEvent | None:
    """Parse one raw RFC 822 message into a pending row. Returns None when the
    queue already has its Message-ID (the idempotency path)."""
    message = email.message_from_bytes(raw, policy=email.policy.default)
    message_id = (message.get("Message-ID") or "").strip() or None
    if message_id is not None:
        if pending_events_repo.get_by_message_id(conn, message_id) is not None:
            return None
    from_addr = str(message.get("From") or "")
    subject = str(message.get("Subject") or "")
    text = extract_text(message)
    draft = parse_email(
        from_addr,
        subject,
        text,
        venues=venues_repo.list_all(conn),
        senders={s.email: s.artist_display for s in mail_senders_repo.list_all(conn)},
        today=today or dt.date.today(),
    )
    return pending_events_repo.add(
        conn,
        PendingEvent(
            received_at=_received_at(message),
            from_addr=from_addr,
            subject=subject,
            message_id=message_id,
            raw_text=text,
            **draft.model_dump(),
        ),
    )


def poll(conn: sqlite3.Connection, config: ImapConfig) -> PollResult:
    """Fetch every message in the configured folder and queue the new ones.

    The folder is selected read-only (nothing is marked \\Seen), so dedup
    rides entirely on Message-ID — safe to re-run any time.
    """
    result = PollResult()
    client = imaplib.IMAP4_SSL(config.host)
    try:
        client.login(config.user, config.password)
        status, _ = client.select(f'"{config.folder}"', readonly=True)
        if status != "OK":
            raise RuntimeError(f"cannot select IMAP folder {config.folder!r}")
        _, data = client.search(None, "ALL")
        message_numbers = data[0].split() if data and data[0] else []
        for number in message_numbers:
            _, fetched = client.fetch(number, "(RFC822)")
            raw = _fetched_bytes(fetched)
            if raw is None:
                result.skipped += 1
                continue
            result.fetched += 1
            if process_message(conn, raw) is not None:
                result.created += 1
            else:
                result.skipped += 1
    finally:
        try:
            client.logout()
        except imaplib.IMAP4.error:
            pass
    return result


def _fetched_bytes(
    fetched: list[bytes | tuple[bytes, bytes]] | list[None],
) -> bytes | None:
    """Pull the raw message out of an imaplib FETCH response (a list mixing
    ``(envelope, body)`` tuples and bare delimiters)."""
    for part in fetched or []:
        if isinstance(part, tuple) and len(part) >= 2:
            return part[1]
    return None
