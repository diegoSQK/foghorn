"""Tests for The Lost Church (SF) parser, driven from a trimmed PatronTicket
``fetchEvents`` remoting response: the San-Francisco + Music category filter
(Santa Rosa, Comedy, and Rental events drop), title cleanup, doors/genre out
of instance names, tiered price collapsing, and window enforcement."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

from foghorn.scrapers import the_lost_church

FIXTURE = Path(__file__).parent.parent / "fixtures" / "the_lost_church_2026_07.json"
TODAY = dt.date(2026, 7, 19)


def _events() -> list[dict[str, Any]]:
    return the_lost_church.unwrap_remoting(
        json.loads(FIXTURE.read_text(encoding="utf-8"))
    )


def test_keeps_only_sf_music_events() -> None:
    shows = the_lost_church.parse_events(_events(), TODAY)
    # Dropped: Jayne-Russell (Santa Rosa), Private Event (Rental), Brittany
    # Carney + Benny Feldman (Comedy). Titles lose the city suffix, the
    # "LIVE at The Lost Church" tail, and the bare "Matinée" note.
    assert [(s.start_local.isoformat(), s.headliner_raw) for s in shows] == [
        ("2026-07-23T20:15:00", "Teona Zak + JinTheQueen"),
        ("2026-08-09T16:00:00", "Kaimera (feat. Bellydance by Chantal)"),
        ("2026-09-18T20:15:00", "Theo Kandel with Remy Sher"),
    ]


def test_doors_genre_and_price_from_instance() -> None:
    show = the_lost_church.parse_events(_events(), TODAY)[0]
    assert show.doors_local == dt.datetime(2026, 7, 23, 19, 30)
    assert show.genre == "Soul/R&B/Pop/Singer-Songwriter"
    assert show.price_text == "$15–$20"
    assert show.ticket_url is not None and "/ticket/#/instances/" in show.ticket_url
    assert show.source_url is not None and "/ticket/#/events/" in show.source_url


def test_window() -> None:
    shows = the_lost_church.parse_events(_events(), TODAY, window_days=30)
    assert [s.headliner_raw for s in shows] == [
        "Teona Zak + JinTheQueen",
        "Kaimera (feat. Bellydance by Chantal)",
    ]


def test_unwrap_remoting_raises_on_failure() -> None:
    try:
        the_lost_church.unwrap_remoting([{"statusCode": 400, "method": "fetchEvents"}])
    except RuntimeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected RuntimeError")
