"""Tests for the Madrone Art Bar (Tribe Events REST API) scraper.

``parse_events`` is pure and driven from a saved API-response fixture
(``fixtures/madrone_art_bar_2026_07.json``) — a trimmed real snapshot with a
pinned ``today`` exercising the edge cases: an all-day entry (Madrone's 04:00
day-boundary artifact), same-day multiples, non-music titles (World Cup
screening, karaoke, figure drawing, book sale, fundraiser, private event), an
entity-encoded title, a ticketed vs. unticketed event, and an out-of-window
event that Tribe returned past the requested ``end_date``. ``fetch_events``
pagination is exercised with an ``httpx.MockTransport`` so no network is
touched.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from foghorn.models import ScrapedShow
from foghorn.scrapers import madrone_art_bar

FIXTURE = Path(__file__).parent.parent / "fixtures" / "madrone_art_bar_2026_07.json"
TODAY = dt.date(2026, 7, 2)


@pytest.fixture
def parsed() -> list[ScrapedShow]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return madrone_art_bar.parse_events(payload["events"], today=TODAY)


def test_returns_expected_shows_sorted(parsed: list[ScrapedShow]) -> None:
    got = [(s.start_local.isoformat(), s.headliner_raw) for s in parsed]
    assert got == [
        ("2026-07-02T21:30:00", "Brazilian Disco"),
        ("2026-07-06T19:00:00", "Motown on Mondays"),
        ("2026-07-11T19:00:00", "HEAVY SOUNDS"),  # same day, two shows
        ("2026-07-11T21:00:00", "STRAIGHTEN IT OUT"),
        ("2026-07-22T18:30:00", "SPIKE SPINS OSCAR’S JAZZ RECORDS"),  # entity decoded
    ]


def test_excludes_all_day_entries(parsed: list[ScrapedShow]) -> None:
    # "Brazilian Wax" is an all-day entry at Madrone's 04:00 day boundary — no
    # real start time, so it's skipped.
    assert not any(s.headliner_raw == "Brazilian Wax" for s in parsed)


def test_excludes_non_music_and_private_events(parsed: list[ScrapedShow]) -> None:
    titles = {s.headliner_raw for s in parsed}
    assert "WORLD CUP: QUARTER FINAL" not in titles  # sports screening
    assert "Karaoke" not in titles
    assert "LIVE MODEL TUESDAY SKETCH" not in titles  # figure drawing
    assert "Madrone Community Book Sale 📚" not in titles
    assert "SF Ed Fund – Summer Fundraiser" not in titles
    assert "PRIVATE EVENT" not in titles


def test_excludes_out_of_window(parsed: list[ScrapedShow]) -> None:
    # Tribe returned "Pop Life" (Oct 3) despite an end_date of Sep 30; the
    # parser re-enforces the 90-day window.
    assert not any(s.headliner_raw == "Pop Life" for s in parsed)


def test_window_size_is_respected() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    shows = madrone_art_bar.parse_events(payload["events"], today=TODAY, window_days=7)
    assert [s.headliner_raw for s in shows] == ["Brazilian Disco", "Motown on Mondays"]


def test_ticket_url_captured_when_present(parsed: list[ScrapedShow]) -> None:
    motown = next(s for s in parsed if s.headliner_raw == "Motown on Mondays")
    assert motown.ticket_url == (
        "https://www.eventbrite.com/e/motown-on-mondays-tickets-1392987917359"
    )


def test_ticket_url_none_when_absent(parsed: list[ScrapedShow]) -> None:
    disco = next(s for s in parsed if s.headliner_raw == "Brazilian Disco")
    assert disco.ticket_url is None


def test_source_url_is_per_event_page(parsed: list[ScrapedShow]) -> None:
    heavy = next(s for s in parsed if s.headliner_raw == "HEAVY SOUNDS")
    assert heavy.source_url == (
        "https://madroneartbar.com/event/heavy-sounds-2025-12-13/2026-07-11/"
    )


def test_optional_fields_default(parsed: list[ScrapedShow]) -> None:
    show = parsed[0]
    assert show.venue_slug == "madrone_art_bar"
    assert show.support_raw == []
    assert show.doors_local is None
    assert show.price_text is None


def test_fetch_events_paginates() -> None:
    page1: dict[str, Any] = {
        "events": [{"id": 1, "title": "Act One", "start_date": "2026-07-03 21:00:00"}],
        "next_rest_url": "https://madroneartbar.com/wp-json/tribe/events/v1/events?page=2",
    }
    page2: dict[str, Any] = {
        "events": [{"id": 2, "title": "Act Two", "start_date": "2026-07-04 21:00:00"}]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if "page=2" in str(request.url):
            return httpx.Response(200, json=page2)
        return httpx.Response(200, json=page1)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    events = madrone_art_bar.fetch_events(TODAY, client=client)
    assert [e["title"] for e in events] == ["Act One", "Act Two"]


def test_fetch_events_stops_on_404_past_last_page() -> None:
    payload: dict[str, Any] = {
        "events": [{"id": 1, "title": "Only Act", "start_date": "2026-07-03 21:00:00"}],
        "next_rest_url": "https://madroneartbar.com/wp-json/tribe/events/v1/events?page=2",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if "page=2" in str(request.url):
            return httpx.Response(404, json={"error": "page not found"})
        return httpx.Response(200, json=payload)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    events = madrone_art_bar.fetch_events(TODAY, client=client)
    assert [e["title"] for e in events] == ["Only Act"]
