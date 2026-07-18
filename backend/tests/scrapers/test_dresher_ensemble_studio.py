"""Tests for the Dresher Ensemble Studio (Tribe REST) scraper.

``parse_events`` is pure and driven from a trimmed live-API fixture
(``fixtures/dresher_2026_07.json``) exercising the venue's edge cases: a
``<br>``-separated multi-act bill, a multi-night run (one row per date), an
all-day row (skipped), and a workshop title (skipped). ``fetch_events`` is
exercised with an ``httpx.MockTransport`` so no network is touched.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import httpx

from foghorn.scrapers import dresher_ensemble_studio

FIXTURE = Path(__file__).parent.parent / "fixtures" / "dresher_2026_07.json"
TODAY = dt.date(2026, 7, 17)


def _events() -> list[dict[str, object]]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    events: list[dict[str, object]] = payload["events"]
    return events


def test_parses_fixture_shows() -> None:
    shows = dresher_ensemble_studio.parse_events(_events(), TODAY)
    titles = [show.headliner_raw for show in shows]
    # 5 real shows survive; the all-day open house and the workshop drop.
    assert len(shows) == 5
    assert "Studio Open House" not in titles
    assert "Composition Workshop with X" not in titles
    assert shows == sorted(shows, key=lambda s: s.start_local)
    assert all(show.venue_slug == "dresher_ensemble_studio" for show in shows)


def test_br_bill_splits_headliner_and_support() -> None:
    shows = dresher_ensemble_studio.parse_events(_events(), TODAY)
    bill = next(s for s in shows if s.headliner_raw == "The Sky Is A Suitcase")
    assert bill.support_raw == ["Jacob Pek + Raffi Garabedian"]
    assert bill.start_local == dt.datetime(2026, 7, 19, 19, 15)


def test_multi_night_run_yields_one_show_per_date() -> None:
    shows = dresher_ensemble_studio.parse_events(_events(), TODAY)
    nights = [s for s in shows if s.headliner_raw == "Where We Meet The Silver Moon"]
    assert len(nights) == 2
    assert len({s.start_local.date() for s in nights}) == 2


def test_window_excludes_out_of_range() -> None:
    shows = dresher_ensemble_studio.parse_events(_events(), TODAY, window_days=1)
    assert shows == []


def test_fetch_pages_through_next_rest_url() -> None:
    page_two_url = "https://dresherensemble.org/wp-json/tribe/events/v1/events?page=2"
    pages = {
        None: {"events": [{"id": 1}], "next_rest_url": page_two_url},
        "2": {"events": [{"id": 2}], "next_rest_url": None},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        page = dict(httpx.QueryParams(request.url.query)).get("page")
        return httpx.Response(200, json=pages[page])

    client = httpx.Client(transport=httpx.MockTransport(handler))
    events = dresher_ensemble_studio.fetch_events(TODAY, client=client)
    assert [e["id"] for e in events] == [1, 2]
