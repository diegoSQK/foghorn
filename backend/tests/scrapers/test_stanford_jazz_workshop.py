"""Tests for the Stanford Jazz Workshop (Tribe REST) scraper.

``parse_events`` is pure and driven from a trimmed live-API fixture
(``fixtures/stanford_jazz_2026_07.json``) exercising the venue's edge cases:
entity-laden titles (``&#038;``, curly-quote entities), a year-round CoHo
Jams row (tagged ``jam``, real end time), the festival's All-Star Jam closer
(left untagged for ingest), Tribe's padded ``end_date`` (dropped), an all-day
row (skipped), a hidden row (skipped), and an out-of-window row (skipped).
``fetch_events`` is exercised with an ``httpx.MockTransport`` so no network
is touched.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import httpx

from foghorn.scrapers import stanford_jazz_workshop

FIXTURE = Path(__file__).parent.parent / "fixtures" / "stanford_jazz_2026_07.json"
TODAY = dt.date(2026, 7, 1)


def _events() -> list[dict[str, object]]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    events: list[dict[str, object]] = payload["events"]
    return events


def test_parses_fixture_shows() -> None:
    shows = stanford_jazz_workshop.parse_events(_events(), TODAY)
    titles = [show.headliner_raw for show in shows]
    # 5 real shows survive; the all-day open house, the hidden row, and the
    # out-of-window November row drop.
    assert len(shows) == 5
    assert "Festival Open House" not in titles
    assert "Hidden Test Event" not in titles
    assert "Winter Season Preview Concert" not in titles
    assert shows == sorted(shows, key=lambda s: s.start_local)
    assert all(show.venue_slug == "stanford_jazz_workshop" for show in shows)


def test_unescapes_html_entities_in_titles() -> None:
    shows = stanford_jazz_workshop.parse_events(_events(), TODAY)
    titles = {show.headliner_raw for show in shows}
    assert "Stefon Harris & Blackout" in titles
    assert "Ruth Davies’ Blues Night featuring Sean “Mack” McDonald" in titles


def test_coho_jams_tagged_as_jam_with_real_end() -> None:
    shows = stanford_jazz_workshop.parse_events(_events(), TODAY)
    jam = next(s for s in shows if s.headliner_raw == "CoHo Jams")
    assert jam.event_type == "jam"
    assert jam.start_local == dt.datetime(2026, 7, 6, 20, 0)
    assert jam.end_local == dt.datetime(2026, 7, 6, 22, 0)


def test_festival_all_star_jam_is_not_tagged() -> None:
    # The ticketed festival closer is a show — event_type stays None so
    # ingest's (conservative, non-matching) default applies.
    shows = stanford_jazz_workshop.parse_events(_events(), TODAY)
    closer = next(s for s in shows if s.headliner_raw == "SJW All-Star Jam")
    assert closer.event_type is None


def test_padded_end_date_dropped() -> None:
    shows = stanford_jazz_workshop.parse_events(_events(), TODAY)
    stefon = next(s for s in shows if s.headliner_raw == "Stefon Harris & Blackout")
    assert stefon.end_local is None


def test_window_excludes_out_of_range() -> None:
    shows = stanford_jazz_workshop.parse_events(_events(), TODAY, window_days=1)
    assert shows == []


def test_fetch_pages_through_next_rest_url() -> None:
    page_two_url = "https://stanfordjazz.org/wp-json/tribe/events/v1/events?page=2"
    pages = {
        None: {"events": [{"id": 1}], "next_rest_url": page_two_url},
        "2": {"events": [{"id": 2}], "next_rest_url": None},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        page = dict(httpx.QueryParams(request.url.query)).get("page")
        return httpx.Response(200, json=pages[page])

    client = httpx.Client(transport=httpx.MockTransport(handler))
    events = stanford_jazz_workshop.fetch_events(TODAY, client=client)
    assert [e["id"] for e in events] == [1, 2]
