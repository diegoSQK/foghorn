"""Tests for the Smiley's Saloon parser, driven from a trimmed /music/
snapshot: date/time/title/ticket/price per event card, room-suffix stripping
("- INSIDE"/"- OUTSIDE"/"- FREE", glued or stacked), the karaoke filter, and
window enforcement."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from foghorn.scrapers import smileys_saloon

FIXTURE = Path(__file__).parent.parent / "fixtures" / "smileys_saloon_2026_07.html"
TODAY = dt.date(2026, 7, 18)


def test_parses_cards_and_strips_room_suffixes() -> None:
    shows = smileys_saloon.parse_html(FIXTURE.read_text(encoding="utf-8"), TODAY)
    assert [(s.start_local.isoformat(), s.headliner_raw, s.price_text) for s in shows] == [
        ("2026-07-18T20:30:00", "Space Suit + Olright", "$12.51"),
        # "…Eaton- OUTSIDE - FREE": stacked suffixes, one glued without a space.
        ("2026-07-19T15:00:00", "Fiddle Camp Pre-Party & Thomas Bryan Eaton", "$23.18"),
        ("2026-07-23T20:00:00", "Open Mic Hosted By Olright", None),  # bare "$" price
        ("2026-09-27T15:00:00", "Deep Basement Shakers", None),
    ]
    # LARRY-OKE (karaoke, Aug 13) is dropped as a non-performance.


def test_eventbrite_ticket_urls() -> None:
    shows = smileys_saloon.parse_html(FIXTURE.read_text(encoding="utf-8"), TODAY)
    assert all(
        s.ticket_url is not None and s.ticket_url.startswith("https://www.eventbrite.com/e/")
        for s in shows
    )


def test_window() -> None:
    shows = smileys_saloon.parse_html(
        FIXTURE.read_text(encoding="utf-8"), TODAY, window_days=30
    )
    assert [s.headliner_raw for s in shows] == [
        "Space Suit + Olright",
        "Fiddle Camp Pre-Party & Thomas Bryan Eaton",
        "Open Mic Hosted By Olright",
    ]
