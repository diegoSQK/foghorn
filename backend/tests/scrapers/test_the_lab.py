"""Tests for The Lab (Squarespace collection JSON) scraper.

``parse_events`` is pure and driven from a trimmed live fixture
(``fixtures/the_lab_2026_07.json``) exercising: Concert-categorized items
kept, an uncategorized "Film Screening" dropped on title signal, a duplicate
item id ingested once, the Dice ticket anchor extracted from the body, and
epoch-millisecond ``startDate`` (with sub-second noise) converted to naive
venue-local time. ``fetch_events`` is exercised with an
``httpx.MockTransport`` so no network is touched.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import httpx

from foghorn.scrapers import the_lab

FIXTURE = Path(__file__).parent.parent / "fixtures" / "the_lab_2026_07.json"
TODAY = dt.date(2026, 7, 17)
WINDOW = 120  # the fixture's real events run late Aug–late Sep


def _payload() -> dict[str, object]:
    data: dict[str, object] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return data


def test_parses_concerts_and_drops_screening() -> None:
    shows = the_lab.parse_events(_payload(), TODAY, window_days=WINDOW)
    titles = [show.headliner_raw for show in shows]
    assert len(shows) == 3  # 3 unique concerts; dup id + screening dropped
    assert all("Screening" not in t for t in titles)
    assert shows == sorted(shows, key=lambda s: s.start_local)
    assert all(show.venue_slug == "the_lab" for show in shows)


def test_start_local_from_epoch_millis() -> None:
    shows = the_lab.parse_events(_payload(), TODAY, window_days=WINDOW)
    merope = next(s for s in shows if s.headliner_raw.startswith("Merope"))
    # 1787972400004 ms → 2026-08-28 20:00:00 PT, sub-second noise truncated.
    assert merope.start_local == dt.datetime(2026, 8, 28, 20, 0, 0)


def test_dice_ticket_url_and_source_url() -> None:
    shows = the_lab.parse_events(_payload(), TODAY, window_days=WINDOW)
    merope = next(s for s in shows if s.headliner_raw.startswith("Merope"))
    assert merope.ticket_url is not None and merope.ticket_url.startswith(
        "https://link.dice.fm/"
    )
    assert merope.source_url.startswith("https://www.thelab.org/projects/")


def test_window_excludes_out_of_range() -> None:
    assert the_lab.parse_events(_payload(), TODAY, window_days=7) == []


def test_fetch_returns_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["format"] == "json"
        return httpx.Response(200, json={"upcoming": []})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert the_lab.fetch_events(client=client) == {"upcoming": []}
