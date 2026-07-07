"""Tests for the poller's message processing (no IMAP — raw RFC 822 bytes in,
pending rows out). The network half is deliberately thin and untested; the
idempotency and extraction logic all lives here."""

from __future__ import annotations

import sqlite3
from email.message import EmailMessage

import pytest

from foghorn.mailingest import poller
from foghorn.models import Venue
from foghorn.repo import mail_senders, pending_events
from foghorn.repo import venues as venues_repo


@pytest.fixture
def mail_conn(conn: sqlite3.Connection) -> sqlite3.Connection:
    venues_repo.upsert(
        conn,
        Venue(
            slug="make_out_room",
            name="The Make-Out Room",
            tz="America/Los_Angeles",
            calendar_url="https://example.com",
        ),
    )
    mail_senders.upsert(conn, "list@dillonvado.com", "Dillon Vado")
    return conn


def _raw(
    body: str,
    subject: str = "Shows this week",
    message_id: str | None = "<m1@list>",
    html_body: str | None = None,
) -> bytes:
    message = EmailMessage()
    message["From"] = "Dillon Vado <list@dillonvado.com>"
    message["Subject"] = subject
    message["Date"] = "Tue, 07 Jul 2026 09:00:00 -0700"
    if message_id is not None:
        message["Message-ID"] = message_id
    message.set_content(body)
    if html_body is not None:
        message.add_alternative(html_body, subtype="html")
    return bytes(message)


def test_process_message_creates_parsed_pending_row(
    mail_conn: sqlite3.Connection,
) -> None:
    import datetime as dt

    row = poller.process_message(
        mail_conn,
        _raw("TONIGHT at the Make-Out Room, 8pm"),
        today=dt.date(2026, 7, 7),
    )
    assert row is not None and row.id is not None
    assert row.artist_display == "Dillon Vado"
    assert row.venue_slug == "make_out_room"
    assert row.date_guess == "2026-07-07"
    assert row.time_guess == "20:00"
    assert row.message_id == "<m1@list>"
    assert row.received_at == "2026-07-07T16:00:00+00:00"  # Date: header → UTC
    assert row.status == "pending"


def test_process_message_is_idempotent_on_message_id(
    mail_conn: sqlite3.Connection,
) -> None:
    assert poller.process_message(mail_conn, _raw("gig 7/24")) is not None
    assert poller.process_message(mail_conn, _raw("gig 7/24")) is None
    assert len(pending_events.list_by_status(mail_conn, "pending")) == 1


def test_html_only_email_falls_back_to_stripped_text(
    mail_conn: sqlite3.Connection,
) -> None:
    message = EmailMessage()
    message["From"] = "list@dillonvado.com"
    message["Subject"] = "July show"
    message["Message-ID"] = "<html@list>"
    message.add_alternative(
        "<html><style>p{color:red}</style><body><p>Friday <b>7/24</b> at the "
        "Make-Out&nbsp;Room &amp; friends, 8pm</p></body></html>",
        subtype="html",
    )
    row = poller.process_message(mail_conn, bytes(message))
    assert row is not None
    assert "<p>" not in row.raw_text and "style" not in row.raw_text
    assert "Make-Out Room & friends" in row.raw_text
    assert row.venue_slug == "make_out_room"
    assert row.time_guess == "20:00"


def test_imap_config_requires_all_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for var in (
        "FOGHORN_IMAP_HOST",
        "FOGHORN_IMAP_USER",
        "FOGHORN_IMAP_PASSWORD",
        "FOGHORN_IMAP_FOLDER",
    ):
        monkeypatch.delenv(var, raising=False)
    assert poller.imap_config_from_env() is None
    monkeypatch.setenv("FOGHORN_IMAP_HOST", "imap.gmail.com")
    monkeypatch.setenv("FOGHORN_IMAP_USER", "diego@example.com")
    assert poller.imap_config_from_env() is None  # password still missing
    monkeypatch.setenv("FOGHORN_IMAP_PASSWORD", "app-password")
    config = poller.imap_config_from_env()
    assert config is not None and config.folder == "foghorn"
    monkeypatch.setenv("FOGHORN_IMAP_FOLDER", "newsletters")
    config = poller.imap_config_from_env()
    assert config is not None and config.folder == "newsletters"
