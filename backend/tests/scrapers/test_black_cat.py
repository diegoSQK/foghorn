"""Tests for the Black Cat (Turntable Tickets API) scraper.

``parse_performances`` is pure and driven from a saved API-response fixture
(``fixtures/black_cat_2026_07.json``) — a trimmed snapshot of the live
``/api/performance/`` payload exercising the edge cases: two sets on one night
(same show, 7:00 and 9:15), a "*CLOSED*" marker entry, a show missing
``price_per_person``, an equal low/high price pair, a not-yet-published show,
a far-future performance outside the window, curly quotes / a pipe / an
NBSP in titles, and a performance with no show id (calendar-URL fallback).
``fetch_performances`` is exercised with an ``httpx.MockTransport`` so no
network is touched.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import httpx
import pytest

from foghorn.models import ScrapedShow
from foghorn.scrapers import black_cat

FIXTURE = Path(__file__).parent.parent / "fixtures" / "black_cat_2026_07.json"
TODAY = dt.date(2026, 7, 2)

DANIEL_WINSHALL = (
    "Daniel Winshall “Denim Dream” Release ft. PHER: Reimagined Sly and the Family Stone"
)


def _performances() -> list[dict[str, object]]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    results: list[dict[str, object]] = payload["results"]
    return results


@pytest.fixture
def parsed() -> list[ScrapedShow]:
    return black_cat.parse_performances(_performances(), today=TODAY)


def test_returns_expected_shows_sorted(parsed: list[ScrapedShow]) -> None:
    # The fixture preserves the API's non-chronological order (Freddie Bryant's
    # July 8 date appears after later dates); the parser must sort. UTC
    # datetimes are converted to venue-local (America/Los_Angeles).
    got = [(s.start_local.isoformat(), s.headliner_raw) for s in parsed]
    assert got == [
        ("2026-07-02T19:00:00", "The Joe Gloss Group"),
        ("2026-07-02T21:15:00", "The Joe Gloss Group"),  # second set, same night
        ("2026-07-03T19:00:00", "A Celebration | R&B of the 2000’s"),  # curly quote
        ("2026-07-08T19:00:00", "Freddie Bryant's Kaleidoscope West Trio"),
        ("2026-07-15T19:00:00", "Sami Stevens' Homecoming"),
        ("2026-07-29T19:00:00", "Arnie Sainz Quintet"),
        ("2026-07-31T19:00:00", DANIEL_WINSHALL),  # NBSP in title collapsed to a space
        ("2026-08-05T19:00:00", "CURRENTS"),
    ]


def test_excludes_closed_markers(parsed: list[ScrapedShow]) -> None:
    assert not any("closed" in s.headliner_raw.lower() for s in parsed)


def test_excludes_not_yet_published(parsed: list[ScrapedShow]) -> None:
    # Ben Sherman's publish_datetime (2026-09-01) is after the pinned today.
    assert not any("Ben Sherman" in s.headliner_raw for s in parsed)


def test_excludes_out_of_window(parsed: list[ScrapedShow]) -> None:
    # Red Rabbit's performance was moved to December 15 (> 90 days out).
    assert not any(s.headliner_raw == "Red Rabbit" for s in parsed)


def test_window_size_is_respected() -> None:
    # A 7-day window from today keeps only the July 2-8 performances.
    shows = black_cat.parse_performances(_performances(), today=TODAY, window_days=7)
    assert [s.headliner_raw for s in shows] == [
        "The Joe Gloss Group",
        "The Joe Gloss Group",
        "A Celebration | R&B of the 2000’s",
        "Freddie Bryant's Kaleidoscope West Trio",
    ]


def test_two_sets_share_booking_url(parsed: list[ScrapedShow]) -> None:
    early, late = parsed[0], parsed[1]
    expected = "https://blackcatsf.turntabletickets.com/shows/11912/?date=2026-07-02"
    assert early.ticket_url == expected
    assert late.ticket_url == expected
    assert early.source_url == expected  # ticket page doubles as provenance


def test_booking_url_uses_local_calendar_date(parsed: list[ScrapedShow]) -> None:
    # The API datetime is 2026-07-04T02:00:00Z — July 3 in venue-local time,
    # and the ?date= parameter must be the local date.
    celebration = next(s for s in parsed if s.headliner_raw.startswith("A Celebration"))
    assert celebration.ticket_url == (
        "https://blackcatsf.turntabletickets.com/shows/11913/?date=2026-07-03"
    )


def test_missing_show_id_falls_back_to_calendar_url(parsed: list[ScrapedShow]) -> None:
    currents = next(s for s in parsed if s.headliner_raw == "CURRENTS")
    assert currents.ticket_url == "https://blackcatsf.turntabletickets.com/calendar"
    assert currents.source_url == "https://blackcatsf.turntabletickets.com/calendar"


def test_price_range_formatting(parsed: list[ScrapedShow]) -> None:
    assert parsed[0].price_text == "$14.50–$44.50"


def test_price_collapses_when_low_equals_high(parsed: list[ScrapedShow]) -> None:
    arnie = next(s for s in parsed if s.headliner_raw == "Arnie Sainz Quintet")
    assert arnie.price_text == "$25.00"


def test_price_none_when_absent(parsed: list[ScrapedShow]) -> None:
    sami = next(s for s in parsed if s.headliner_raw == "Sami Stevens' Homecoming")
    assert sami.price_text is None


def test_optional_fields_default(parsed: list[ScrapedShow]) -> None:
    show = parsed[0]
    assert show.venue_slug == "black_cat"
    assert show.support_raw == []
    assert show.doors_local is None


def test_fetch_performances_queries_window_and_unwraps_results() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"count": 1, "results": [{"id": 1}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    performances = black_cat.fetch_performances(TODAY, client=client)
    assert performances == [{"id": 1}]
    params = dict(requests[0].url.params)
    assert params == {
        "booking": "true",
        "pagination": "false",
        "start_date": "2026-07-02",
        # 90-day window + one-day buffer for the API's UTC date filtering.
        "end_date": "2026-10-01",
    }
