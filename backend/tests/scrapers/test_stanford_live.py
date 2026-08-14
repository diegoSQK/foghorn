"""Tests for the Stanford Live (Spektrix) scraper.

``parse`` is pure and driven from trimmed snapshots of the live ``/events`` and
``/instances`` payloads. Spektrix returns the whole catalogue — past seasons
included — and splits productions from dated performances, so the fixtures
cover the join, the window filter, cancellations, and an instance whose
production is missing.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from foghorn.models import ScrapedShow
from foghorn.scrapers import stanford_live

FIXTURES = Path(__file__).parent.parent / "fixtures"
TODAY = dt.date(2026, 8, 13)


def _payloads() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    events = json.loads(
        (FIXTURES / "stanford_live_events_2026_08.json").read_text(encoding="utf-8")
    )
    instances = json.loads(
        (FIXTURES / "stanford_live_instances_2026_08.json").read_text(encoding="utf-8")
    )
    return events, instances


@pytest.fixture
def parsed() -> list[ScrapedShow]:
    events, instances = _payloads()
    return stanford_live.parse(events, instances, today=TODAY)


def test_joins_instances_to_their_production(parsed: list[ScrapedShow]) -> None:
    # An instance carries only a date and an event id; the name comes from the
    # production, so an empty result would mean the join broke.
    assert parsed
    assert all(s.headliner_raw.strip() for s in parsed)
    assert all(s.venue_slug == "stanford_live" for s in parsed)
    assert parsed == sorted(parsed, key=lambda s: (s.start_local, s.headliner_raw))


def test_past_seasons_are_filtered_out(parsed: list[ScrapedShow]) -> None:
    """The window filter is load-bearing here, not a nicety.

    Spektrix hands back the entire catalogue — the live payload spans
    2025-09 to 2027-05 — so without it the calendar would fill with last
    season's dates.
    """
    horizon = TODAY + dt.timedelta(days=stanford_live.SCRAPE_WINDOW_DAYS)
    assert all(TODAY <= s.start_local.date() <= horizon for s in parsed)
    assert all(s.start_local.year >= 2026 for s in parsed)


def test_cancelled_instances_are_skipped(parsed: list[ScrapedShow]) -> None:
    assert not any(s.start_local == dt.datetime(2026, 9, 9, 20, 0) for s in parsed)


def test_instance_without_a_production_is_skipped(parsed: list[ScrapedShow]) -> None:
    # Nothing to name it with, so it can't become a show.
    assert not any(s.start_local == dt.datetime(2026, 9, 10, 20, 0) for s in parsed)


def test_comedy_comes_from_the_sources_genre(parsed: list[ScrapedShow]) -> None:
    comedy = [s for s in parsed if s.event_type == "comedy"]
    assert comedy, "fixture should contain a Comedy-genre production"
    assert all((s.genre or "").casefold() == "comedy" for s in comedy)
    # Everything else keeps the pipeline's own show/jam inference.
    assert all(s.event_type is None for s in parsed if s.event_type != "comedy")


def test_source_genre_rides_along(parsed: list[ScrapedShow]) -> None:
    genres = {s.genre for s in parsed if s.genre}
    assert genres, "Spektrix classifies productions; that should survive"


def test_no_ticket_urls_are_invented(parsed: list[ScrapedShow]) -> None:
    # webEventId is unpopulated on every event, so there is no per-event page
    # and no basket link. Provenance is the calendar, honestly labelled.
    assert all(s.ticket_url is None for s in parsed)
    assert all(s.source_url == stanford_live.CALENDAR_URL for s in parsed)


def test_rooms_are_left_empty(parsed: list[ScrapedShow]) -> None:
    # Instances carry no venue, so shows can't be routed to Bing vs Frost vs
    # Memorial. Better empty than guessed.
    assert all(s.room is None for s in parsed)


# --------------------------------------------------------------------------
# fetch side
# --------------------------------------------------------------------------


def test_fetch_hits_both_spektrix_endpoints() -> None:
    calls: list[str] = []
    events, instances = _payloads()

    class _Response:
        def __init__(self, payload: Any) -> None:
            self._payload = payload

        def read(self) -> bytes:
            return json.dumps(self._payload).encode()

        def __enter__(self) -> _Response:
            return self

        def __exit__(self, *exc: object) -> None:
            return None

    def _fake(request: Any, timeout: float | None = None) -> _Response:
        calls.append(request.full_url)
        return _Response(events if request.full_url.endswith("/events") else instances)

    with patch("urllib.request.urlopen", _fake):
        got_events, got_instances = stanford_live.fetch_events_and_instances()

    assert calls == [f"{stanford_live.API_BASE}/events", f"{stanford_live.API_BASE}/instances"]
    assert got_events == events and got_instances == instances


def test_non_list_payload_fails_loudly() -> None:
    class _Response:
        def read(self) -> bytes:
            return b'{"error": "nope"}'

        def __enter__(self) -> _Response:
            return self

        def __exit__(self, *exc: object) -> None:
            return None

    with patch("urllib.request.urlopen", return_value=_Response()):
        with pytest.raises(stanford_live.StanfordLiveSourceError, match="non-list"):
            stanford_live.fetch_events_and_instances()
