"""Tests for the Phase 8 mail repos: mail_senders + pending_events."""

from __future__ import annotations

import sqlite3

import pytest

from foghorn.models import PendingEvent
from foghorn.repo import mail_senders, pending_events


def _pending(**overrides: object) -> PendingEvent:
    base: dict[str, object] = {
        "received_at": "2026-07-01T12:00:00+00:00",
        "from_addr": "list@dillonvado.com",
        "subject": "Shows this week",
        "raw_text": "Tonight at the Back Room, 8pm",
    }
    base.update(overrides)
    return PendingEvent.model_validate(base)


def test_sender_upsert_lowercases_and_updates(conn: sqlite3.Connection) -> None:
    mail_senders.upsert(conn, "List@DillonVado.com", "Dillon Vado")
    stored = mail_senders.get(conn, "list@dillonvado.com")
    assert stored is not None and stored.artist_display == "Dillon Vado"
    # Re-upserting the same address (any casing) updates in place.
    mail_senders.upsert(conn, "LIST@dillonvado.com", "Dillon Vado Trio")
    assert len(mail_senders.list_all(conn)) == 1
    refreshed = mail_senders.get(conn, "list@dillonvado.com")
    assert refreshed is not None and refreshed.artist_display == "Dillon Vado Trio"


def test_sender_remove(conn: sqlite3.Connection) -> None:
    mail_senders.upsert(conn, "a@example.com", "A")
    assert mail_senders.remove(conn, "A@example.com") is True
    assert mail_senders.remove(conn, "a@example.com") is False
    assert mail_senders.list_all(conn) == []


def test_pending_add_and_list_by_status(conn: sqlite3.Connection) -> None:
    first = pending_events.add(conn, _pending(subject="one"))
    second = pending_events.add(
        conn, _pending(subject="two", received_at="2026-07-02T12:00:00+00:00")
    )
    assert first.id is not None and second.id is not None
    listed = pending_events.list_by_status(conn, "pending")
    assert [event.subject for event in listed] == ["two", "one"]  # newest first
    assert pending_events.list_by_status(conn, "approved") == []


def test_pending_add_is_idempotent_on_message_id(conn: sqlite3.Connection) -> None:
    first = pending_events.add(conn, _pending(message_id="<abc@mail>"))
    again = pending_events.add(
        conn, _pending(message_id="<abc@mail>", subject="changed")
    )
    assert again.id == first.id
    assert again.subject == first.subject  # existing row untouched
    assert len(pending_events.list_by_status(conn, "pending")) == 1


def test_pending_set_status(conn: sqlite3.Connection) -> None:
    row = pending_events.add(conn, _pending())
    assert row.id is not None
    assert pending_events.set_status(conn, row.id, "rejected") is True
    assert pending_events.list_by_status(conn, "pending") == []
    rejected = pending_events.list_by_status(conn, "rejected")
    assert [event.id for event in rejected] == [row.id]
    assert pending_events.set_status(conn, 9999, "approved") is False


def test_pending_update_draft(conn: sqlite3.Connection) -> None:
    row = pending_events.add(conn, _pending())
    assert row.id is not None
    updated = pending_events.update_draft(
        conn,
        row.id,
        {"venue_slug": "back_room", "date_guess": "2026-07-10", "time_guess": "20:00"},
    )
    assert updated is not None
    assert updated.venue_slug == "back_room"
    assert updated.date_guess == "2026-07-10"
    with pytest.raises(ValueError):
        pending_events.update_draft(conn, row.id, {"raw_text": "nope"})
    assert pending_events.update_draft(conn, 9999, {"venue_slug": "x"}) is None
