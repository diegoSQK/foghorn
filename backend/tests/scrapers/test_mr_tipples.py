"""Tests for the Mr. Tipple's (Tribe Events REST API) scraper.

``parse_events`` is pure and driven from a saved API-response fixture
(``fixtures/mr_tipples_2026_05.json``); ``fetch_events`` pagination is exercised
with an ``httpx.MockTransport`` so no network is touched.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from foghorn.models import ScrapedShow
from foghorn.scrapers import mr_tipples

FIXTURE = Path(__file__).parent.parent / "fixtures" / "mr_tipples_2026_05.json"


@pytest.fixture
def parsed() -> list[ScrapedShow]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return mr_tipples.parse_events(payload["events"])


def test_returns_expected_shows_sorted(parsed: list[ScrapedShow]) -> None:
    got = [(s.start_local.isoformat(), s.headliner_raw) for s in parsed]
    assert got == [
        ("2026-05-23T18:00:00", "Steven Lugerner’s SLUGish Ensemble"),  # entity decoded
        ("2026-05-24T19:00:00", "Open Mic Night"),
        ("2026-05-27T20:00:00", "José James"),  # accent preserved
    ]


def test_excludes_all_day_hidden_and_closed(parsed: list[ScrapedShow]) -> None:
    titles = {s.headliner_raw for s in parsed}
    assert "Daytime Holiday Market" not in titles  # all_day
    assert "Hidden Soundcheck" not in titles  # hide_from_listings
    assert not any("Closed" in t for t in titles)  # closure markers


def test_ticket_url_and_price_mapping(parsed: list[ScrapedShow]) -> None:
    show = parsed[0]
    assert show.price_text == "$15 – $30"
    # &amp; in the OpenTable link is unescaped to &.
    assert show.ticket_url is not None
    assert "&amp;" not in show.ticket_url
    assert show.ticket_url.startswith("http://www.opentable.com/")
    assert show.source_url == "https://mrtipplessf.com/calendar/slugish-ensemble/"
    assert show.venue_slug == "mr_tipples"
    assert show.support_raw == []


def test_free_event_has_null_ticket_and_price(parsed: list[ScrapedShow]) -> None:
    open_mic = next(s for s in parsed if s.headliner_raw == "Open Mic Night")
    assert open_mic.ticket_url is None
    assert open_mic.price_text is None


def test_fetch_events_paginates() -> None:
    page1: dict[str, Any] = {
        "events": [{"id": 1, "title": "Act One", "start_date": "2026-06-01 20:00:00"}],
        "next_rest_url": "https://mrtipplessf.com/wp-json/tribe/events/v1/events?page=2",
    }
    page2: dict[str, Any] = {
        "events": [{"id": 2, "title": "Act Two", "start_date": "2026-06-02 20:00:00"}]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if "page=2" in str(request.url):
            return httpx.Response(200, json=page2)
        return httpx.Response(200, json=page1)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    events = mr_tipples.fetch_events(dt.date(2026, 6, 1), client=client)
    assert [e["title"] for e in events] == ["Act One", "Act Two"]


def test_fetch_events_stops_on_404_past_last_page() -> None:
    payload: dict[str, Any] = {
        "events": [{"id": 1, "title": "Only Act", "start_date": "2026-06-01 20:00:00"}],
        "next_rest_url": "https://mrtipplessf.com/wp-json/tribe/events/v1/events?page=2",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if "page=2" in str(request.url):
            return httpx.Response(404, json={"error": "page not found"})
        return httpx.Response(200, json=payload)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    events = mr_tipples.fetch_events(dt.date(2026, 6, 1), client=client)
    assert [e["title"] for e in events] == ["Only Act"]
