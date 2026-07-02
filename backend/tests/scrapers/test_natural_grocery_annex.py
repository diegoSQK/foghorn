"""Tests for the El Cerrito Natural Grocery Annex (Tribe Events REST API) scraper.

``parse_events`` is pure and driven from a saved API-response fixture
(``fixtures/natural_grocery_annex_2026_07.json``) with an injected ``today`` so
the 90-day window doesn't depend on the clock. The fixture is a trimmed
snapshot of the live company-wide calendar exercising the edge cases — two
shows on one day, the "The Annex Sessions:" prefix (present and absent), HTML
entities in titles, store programming (wine tasting) to drop, an all-day
"No Music Tonight" marker, an event at the Berkeley store (wrong venue), a
past event, and an out-of-window event. ``fetch_events`` pagination is
exercised with an ``httpx.MockTransport`` so no network is touched.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from foghorn.models import ScrapedShow
from foghorn.scrapers import natural_grocery_annex

FIXTURE = Path(__file__).parent.parent / "fixtures" / "natural_grocery_annex_2026_07.json"
TODAY = dt.date(2026, 7, 2)


@pytest.fixture
def parsed() -> list[ScrapedShow]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return natural_grocery_annex.parse_events(payload["events"], today=TODAY)


def test_returns_expected_shows_sorted(parsed: list[ScrapedShow]) -> None:
    got = [(s.start_local.isoformat(), s.headliner_raw) for s in parsed]
    assert got == [
        # Series prefix stripped from headliner_raw.
        ("2026-07-08T18:00:00", "Marina Lavalle and Pedro Rosales"),
        ("2026-07-08T20:30:00", "The Key System"),  # same day, later set
        ("2026-07-15T18:00:00", "Modupue Wednesday"),
        ("2026-07-22T18:00:00", "Carlos Caminos, Jesse Torre, Mellissa Cruz"),
        ("2026-07-29T18:00:00", "Charged Particles with Tod Dickow"),  # no prefix
        ("2026-08-05T18:00:00", "Ruben Hurtado & Orestes Vilato"),  # &#038; decoded
    ]


def test_excludes_past_and_out_of_window(parsed: list[ScrapedShow]) -> None:
    titles = {s.headliner_raw for s in parsed}
    # July 1 is the day before the pinned today.
    assert "Chris Trinidad’s Chroma Tonic" not in titles
    # October 21 is ~111 days past the pinned today (> 90-day window).
    assert "The Shadow Band" not in titles


def test_window_size_is_respected() -> None:
    # A 7-day window from today catches only the two July 8 sets.
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    shows = natural_grocery_annex.parse_events(
        payload["events"], today=TODAY, window_days=7
    )
    assert [s.headliner_raw for s in shows] == [
        "Marina Lavalle and Pedro Rosales",
        "The Key System",
    ]


def test_excludes_store_programming_and_all_day(parsed: list[ScrapedShow]) -> None:
    titles = {s.headliner_raw for s in parsed}
    assert "Mini Wine Tasting: Bistue Cellars" not in titles  # non-music
    assert "No Music Tonight" not in titles  # all-day closure marker


def test_excludes_events_not_at_the_annex(parsed: list[ScrapedShow]) -> None:
    # The calendar is company-wide; the Berkeley-store event must not attach
    # to this venue.
    assert not any("Berkeley" in s.headliner_raw for s in parsed)


def test_ticket_url_and_price_captured_when_present(parsed: list[ScrapedShow]) -> None:
    key_system = next(s for s in parsed if s.headliner_raw == "The Key System")
    assert key_system.price_text == "$10"
    assert key_system.ticket_url == (
        "https://www.eventbrite.com/e/the-key-system-at-the-annex-tickets-1000000000"
    )


def test_free_event_has_null_ticket_and_price(parsed: list[ScrapedShow]) -> None:
    marina = next(s for s in parsed if s.headliner_raw.startswith("Marina Lavalle"))
    assert marina.ticket_url is None
    assert marina.price_text is None


def test_source_url_is_per_event_page(parsed: list[ScrapedShow]) -> None:
    marina = next(s for s in parsed if s.headliner_raw.startswith("Marina Lavalle"))
    assert marina.source_url == (
        "https://naturalgrocery.com/event/"
        "the-annex-sessions-marina-la-valle-and-pedro-rosales/"
    )


def test_optional_fields_default(parsed: list[ScrapedShow]) -> None:
    show = parsed[0]
    assert show.venue_slug == "natural_grocery_annex"
    assert show.support_raw == []
    assert show.doors_local is None


def test_fetch_events_paginates() -> None:
    page1: dict[str, Any] = {
        "events": [{"id": 1, "title": "Act One", "start_date": "2026-07-08 18:00:00"}],
        "next_rest_url": (
            "https://naturalgrocery.com/wp-json/tribe/events/v1/events?page=2"
        ),
    }
    page2: dict[str, Any] = {
        "events": [{"id": 2, "title": "Act Two", "start_date": "2026-07-15 18:00:00"}]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if "page=2" in str(request.url):
            return httpx.Response(200, json=page2)
        return httpx.Response(200, json=page1)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    events = natural_grocery_annex.fetch_events(dt.date(2026, 7, 2), client=client)
    assert [e["title"] for e in events] == ["Act One", "Act Two"]


def test_fetch_events_stops_on_404_past_last_page() -> None:
    payload: dict[str, Any] = {
        "events": [{"id": 1, "title": "Only Act", "start_date": "2026-07-08 18:00:00"}],
        "next_rest_url": (
            "https://naturalgrocery.com/wp-json/tribe/events/v1/events?page=2"
        ),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if "page=2" in str(request.url):
            return httpx.Response(404, json={"error": "page not found"})
        return httpx.Response(200, json=payload)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    events = natural_grocery_annex.fetch_events(dt.date(2026, 7, 2), client=client)
    assert [e["title"] for e in events] == ["Only Act"]
