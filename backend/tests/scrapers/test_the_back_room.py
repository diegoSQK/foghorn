"""Tests for The Back Room (Humanitix collection) parser.

Fixture-driven and deterministic: ``parse`` takes an injected ``today`` so the
90-day window doesn't depend on the clock, and both inputs are fixtures — the
trimmed collection page (``fixtures/the_back_room_2026_07.html``: host
ProfilePage JSON-LD to ignore, ItemList JSON-LD with per-tier Offer prices,
and the serialized event-id list) plus the trimmed tRPC
``events.getEventsFromIds`` payload (``fixtures/the_back_room_2026_07.json``).
The tRPC fixture adds events beyond the JSON-LD (price unknown), two
out-of-window fall shows, and one synthetic comedy booking exercising the
non-music filter.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import pytest

from foghorn.models import ScrapedShow
from foghorn.scrapers import the_back_room

FIXTURES = Path(__file__).parent.parent / "fixtures"
HTML_FIXTURE = FIXTURES / "the_back_room_2026_07.html"
EVENTS_FIXTURE = FIXTURES / "the_back_room_2026_07.json"
TODAY = dt.date(2026, 7, 2)


def _html() -> str:
    return HTML_FIXTURE.read_text(encoding="utf-8")


def _events() -> list[dict[str, Any]]:
    data: list[dict[str, Any]] = json.loads(EVENTS_FIXTURE.read_text(encoding="utf-8"))
    return data


@pytest.fixture
def parsed() -> list[ScrapedShow]:
    return the_back_room.parse(_html(), _events(), today=TODAY)


def test_returns_expected_shows_sorted(parsed: list[ScrapedShow]) -> None:
    got = [(s.start_local.isoformat(), s.headliner_raw) for s in parsed]
    assert got == [
        ("2026-07-03T20:00:00", "Sedge Green Group"),
        # &amp; entities unescaped; 3pm matinee (offset-qualified startDate)
        ("2026-07-12T15:00:00", "Blues & Jazz Singers Jam Session with Sam Rudin & Pamela Rose"),
        ("2026-07-16T20:00:00", "Larry Ochs, Ben Davis, Darren Johnston, Lisa Mezzacappa"
         " - Subconscious Life"),
        ("2026-07-18T20:00:00", "Mark Hummel Band w/ Steve Freund"),
        # Present only in the tRPC payload (behind the page's load-more)
        ("2026-08-06T20:00:00", "Miss Maybell & Her Ragtime Romeos"),
    ]


def test_excludes_out_of_window(parsed: list[ScrapedShow]) -> None:
    # Newberry & Verch (Oct 29) and My Darling Clementine (Nov 6) are past the
    # 90-day window from the pinned today (ends Sep 30).
    assert not any(s.start_local.date() > dt.date(2026, 9, 30) for s in parsed)


def test_window_size_is_respected() -> None:
    # A 12-day window from today (ends Jul 14) keeps only the July 3 and
    # July 12 shows.
    shows = the_back_room.parse(_html(), _events(), today=TODAY, window_days=12)
    assert [s.start_local.date() for s in shows] == [
        dt.date(2026, 7, 3),
        dt.date(2026, 7, 12),
    ]


def test_non_music_dropped() -> None:
    # The synthetic "An Evening of Stand-Up Comedy" (Aug 15) is in-window but
    # not music — dropped even with a huge window.
    shows = the_back_room.parse(_html(), _events(), today=TODAY, window_days=365)
    assert not any("Comedy" in s.headliner_raw for s in shows)


def test_price_range_from_offer_tiers(parsed: list[ScrapedShow]) -> None:
    # Sedge Green Group: GA $20 + student $15 tiers -> a range.
    sedge = next(s for s in parsed if s.headliner_raw == "Sedge Green Group")
    assert sedge.price_text == "$15–$20"


def test_single_tier_prices(parsed: list[ScrapedShow]) -> None:
    hummel = next(s for s in parsed if s.headliner_raw.startswith("Mark Hummel"))
    assert hummel.price_text == "$30"
    # Decimal prices pass through the "%g" formatting.
    ochs = next(s for s in parsed if s.headliner_raw.startswith("Larry Ochs"))
    assert ochs.price_text == "$22.5"


def test_trpc_only_event_has_no_price(parsed: list[ScrapedShow]) -> None:
    # Events past the JSON-LD's first page come from tRPC, which carries no
    # pricing — unknown, not free.
    maybell = next(s for s in parsed if s.headliner_raw.startswith("Miss Maybell"))
    assert maybell.price_text is None


def test_ticket_and_source_urls_stripped_of_tracking(parsed: list[ScrapedShow]) -> None:
    # tRPC urls carry ?hxchl=hex-col; JSON-LD urls are bare. Both normalize.
    for show in parsed:
        assert show.ticket_url is not None and "?" not in show.ticket_url
        assert "?" not in show.source_url
    maybell = next(s for s in parsed if s.headliner_raw.startswith("Miss Maybell"))
    assert maybell.ticket_url == (
        "https://events.humanitix.com/miss-maybell-and-her-ragtime-romeos/tickets"
    )
    assert maybell.source_url == (
        "https://events.humanitix.com/miss-maybell-and-her-ragtime-romeos"
    )


def test_source_url_is_per_event_page(parsed: list[ScrapedShow]) -> None:
    sedge = next(s for s in parsed if s.headliner_raw == "Sedge Green Group")
    assert sedge.source_url == "https://events.humanitix.com/sedge-green-group"


def test_extract_event_ids() -> None:
    ids = the_back_room.extract_event_ids(_html())
    # The fixture's serialized state lists all 8 collection events — more than
    # the 4 server-rendered into JSON-LD.
    assert len(ids) == 8
    assert ids[0] == "6a35674d7df96ef076ecfc11"
    assert all(len(event_id) == 24 for event_id in ids)


def test_extract_event_ids_missing_marker() -> None:
    assert the_back_room.extract_event_ids("<html><body>nope</body></html>") == []


def test_parse_without_trpc_events_falls_back_to_json_ld() -> None:
    # If the tRPC fetch yields nothing, the server-rendered JSON-LD events
    # still make the near-term calendar.
    shows = the_back_room.parse(_html(), [], today=TODAY)
    assert [s.headliner_raw for s in shows][:1] == ["Sedge Green Group"]
    assert len(shows) == 4


def test_optional_fields_default(parsed: list[ScrapedShow]) -> None:
    show = parsed[0]
    assert show.venue_slug == "the_back_room"
    # Humanitix structures no per-event performer lists, so no support acts.
    assert show.support_raw == []
    assert show.doors_local is None
