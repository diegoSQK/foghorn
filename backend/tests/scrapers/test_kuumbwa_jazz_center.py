"""Tests for the Kuumbwa Jazz Center (Tribe REST) scraper.

``parse_events`` is pure and driven from the venue's real cached first page
(``fixtures/kuumbwa_2026_07.json``) exercising the title conventions: a
``CANCELLED – …`` row skipped, a ``RESCHEDULED: Master Class: …`` row
skipped on the master-class signal, entity unescaping, and window
enforcement. ``fetch_events`` is exercised with an ``httpx.MockTransport``
covering both normal ``next_rest_url`` pagination and the LiteSpeed cache
trap (identical page repeated forever) that the id-seen guard must break
out of.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import httpx

from foghorn.scrapers import kuumbwa_jazz_center

FIXTURE = Path(__file__).parent.parent / "fixtures" / "kuumbwa_2026_07.json"
TODAY = dt.date(2026, 7, 17)


def _events() -> list[dict[str, object]]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    events: list[dict[str, object]] = payload["events"]
    return events


def test_parses_fixture_and_applies_title_conventions() -> None:
    shows = kuumbwa_jazz_center.parse_events(_events(), TODAY)
    titles = [show.headliner_raw for show in shows]
    # 10 fixture rows → 8 shows: the CANCELLED row and the master class drop.
    assert len(shows) == 8
    assert not any("CANCELLED" in t or "Master Class" in t for t in titles)
    # Entities unescape ("&#038;" → "&").
    assert "Peter Asher & Jeremy Clyde" in titles
    assert shows == sorted(shows, key=lambda s: s.start_local)
    assert all(show.venue_slug == "kuumbwa_jazz_center" for show in shows)


def test_rescheduled_prefix_strips_but_show_survives() -> None:
    row = {
        "id": 1,
        "title": "RESCHEDULED: Yilian Cañizares",
        "start_date": "2026-07-28 19:00:00",
        "all_day": False,
        "hide_from_listings": False,
        "cost": "",
        "website": "",
        "url": "https://www.kuumbwajazz.org/event/yilian/",
    }
    shows = kuumbwa_jazz_center.parse_events([row], TODAY)
    assert [s.headliner_raw for s in shows] == ["Yilian Cañizares"]


def test_window_excludes_out_of_range() -> None:
    assert kuumbwa_jazz_center.parse_events(_events(), TODAY, window_days=0) == []


def test_fetch_pages_through_next_rest_url() -> None:
    page_two_url = f"{kuumbwa_jazz_center.EVENTS_API}?page=2"
    pages = {
        None: {"events": [{"id": 1}], "next_rest_url": page_two_url},
        "2": {"events": [{"id": 2}], "next_rest_url": None},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        page = dict(httpx.QueryParams(request.url.query)).get("page")
        return httpx.Response(200, json=pages[page])

    client = httpx.Client(transport=httpx.MockTransport(handler))
    events = kuumbwa_jazz_center.fetch_events(TODAY, client=client)
    assert [e["id"] for e in events] == [1, 2]


def test_fetch_breaks_out_of_cached_page_loop() -> None:
    # The LiteSpeed trap: every request returns the same page with a
    # next_rest_url that never advances. The id-seen guard must terminate
    # after one pass instead of looping to MAX_PAGES.
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={
                "events": [{"id": 1}, {"id": 2}],
                "next_rest_url": f"{kuumbwa_jazz_center.EVENTS_API}?page=2",
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    events = kuumbwa_jazz_center.fetch_events(TODAY, client=client)
    assert [e["id"] for e in events] == [1, 2]
    assert calls == 2  # initial page + one repeat that added nothing
