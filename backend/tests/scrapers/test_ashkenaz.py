"""Tests for the Ashkenaz (VenuePilot GraphQL) scraper.

``parse_events`` is pure and driven from a trimmed snapshot of the live
``publicEvents`` response (``fixtures/ashkenaz_2026_08.json``): twelve real
events plus four synthesized edge cases the live window didn't contain — a
blank name, a missing start time, a past-midnight end, and a date beyond the
window.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from foghorn.ingest.pipeline import normalize_genre
from foghorn.models import ScrapedShow
from foghorn.scrapers import ashkenaz

FIXTURE = Path(__file__).parent.parent / "fixtures" / "ashkenaz_2026_08.json"
TODAY = dt.date(2026, 8, 13)


def _events() -> list[dict[str, Any]]:
    data: list[dict[str, Any]] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return data


@pytest.fixture
def parsed() -> list[ScrapedShow]:
    return ashkenaz.parse_events(_events(), today=TODAY)


def test_parses_the_live_window(parsed: list[ScrapedShow]) -> None:
    assert parsed
    assert all(s.venue_slug == "ashkenaz" for s in parsed)
    assert parsed == sorted(parsed, key=lambda s: (s.start_local, s.headliner_raw))
    names = {s.headliner_raw for s in parsed}
    assert "Kanekoa" in names


def test_support_is_not_treated_as_a_support_act(parsed: list[ScrapedShow]) -> None:
    """The trap this venue sets.

    VenuePilot's ``support`` is free text, and Ashkenaz uses it as a subtitle —
    "Cajun/Zydeco", "A Grateful Dead Night", "Just Announced!". Not one value in
    a six-month window was a billed act, so putting it in ``support_raw`` would
    invent performers named "Just Announced!" and expose them to watchlist
    matching.
    """
    assert all(s.support_raw == [] for s in parsed)
    # It survives as the genre string instead, which is what it usually is.
    zydeco = next(s for s in parsed if s.headliner_raw.startswith("Blackcat"))
    assert zydeco.genre == "Cajun/Zydeco"


def test_notice_style_support_values_normalize_away(parsed: list[ScrapedShow]) -> None:
    # "Just Announced!" / "Fundraising Event" carry no genre keyword, so ingest
    # drops them to None and the venue default applies — the reason routing
    # them through `genre` is safe.
    notices = [
        s.genre for s in parsed if s.genre in {"Just Announced!", "Fundraising Event"}
    ]
    assert notices, "fixture should include a notice-style support value"
    assert all(normalize_genre(g) is None for g in notices)


def test_real_genre_strings_do_normalize(parsed: list[ScrapedShow]) -> None:
    by_name = {s.headliner_raw: s.genre for s in parsed}
    assert normalize_genre(by_name["Guajirón"]) == "jazz"  # "…& Tropical Jazz"


def test_doors_and_end_times_are_carried(parsed: list[ScrapedShow]) -> None:
    zydeco = next(s for s in parsed if s.headliner_raw.startswith("Blackcat"))
    assert zydeco.start_local == dt.datetime(2026, 8, 13, 20, 0)
    assert zydeco.doors_local == dt.datetime(2026, 8, 13, 19, 30)
    assert zydeco.end_local == dt.datetime(2026, 8, 13, 23, 30)


def test_past_midnight_end_is_kept(parsed: list[ScrapedShow]) -> None:
    # An end earlier than the start is the documented past-midnight shape.
    late = next(s for s in parsed if s.headliner_raw == "Past Midnight Show")
    assert late.end_local is not None
    assert late.end_local < late.start_local


def test_events_without_a_name_or_start_are_skipped(parsed: list[ScrapedShow]) -> None:
    names = {s.headliner_raw for s in parsed}
    assert "No Time Announced" not in names  # never invent a time
    assert all(name.strip() for name in names)  # the blank-name row is gone


def test_window_is_respected(parsed: list[ScrapedShow]) -> None:
    horizon = TODAY + dt.timedelta(days=ashkenaz.SCRAPE_WINDOW_DAYS)
    assert all(TODAY <= s.start_local.date() <= horizon for s in parsed)
    assert not any(s.headliner_raw == "Beyond The Window" for s in parsed)


def test_ticket_and_source_urls(parsed: list[ScrapedShow]) -> None:
    assert all(s.source_url for s in parsed)
    ticketed = [s for s in parsed if s.ticket_url]
    assert ticketed, "the live capture had a ticket URL on every event"


# --------------------------------------------------------------------------
# fetch side
# --------------------------------------------------------------------------


def test_fetch_posts_the_window_and_account() -> None:
    captured: dict[str, Any] = {}

    class _Response:
        def read(self) -> bytes:
            return json.dumps({"data": {"publicEvents": []}}).encode()

        def __enter__(self) -> _Response:
            return self

        def __exit__(self, *exc: object) -> None:
            return None

    def _fake(request: Any, timeout: float | None = None) -> _Response:
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode())
        return _Response()

    with patch("urllib.request.urlopen", _fake):
        assert ashkenaz.fetch_events(TODAY, window_days=30) == []

    assert captured["url"] == ashkenaz.GRAPHQL_URL
    variables = captured["body"]["variables"]
    assert variables["accountIds"] == [ashkenaz.ACCOUNT_ID]
    assert variables["startDate"] == "2026-08-13"
    assert variables["endDate"] == "2026-09-12"
    # The endpoint has introspection disabled, so the query text is
    # load-bearing — it came out of the widget bundle, not the schema.
    assert "publicEvents" in captured["body"]["query"]


def test_graphql_errors_fail_loudly() -> None:
    class _Response:
        def read(self) -> bytes:
            return json.dumps({"errors": [{"message": "nope"}]}).encode()

        def __enter__(self) -> _Response:
            return self

        def __exit__(self, *exc: object) -> None:
            return None

    with patch("urllib.request.urlopen", return_value=_Response()):
        with pytest.raises(ashkenaz.AshkenazSourceError, match="rejected"):
            ashkenaz.fetch_events(TODAY)


def test_missing_payload_fails_loudly() -> None:
    class _Response:
        def read(self) -> bytes:
            return json.dumps({"data": {}}).encode()

        def __enter__(self) -> _Response:
            return self

        def __exit__(self, *exc: object) -> None:
            return None

    with patch("urllib.request.urlopen", return_value=_Response()):
        with pytest.raises(ashkenaz.AshkenazSourceError, match="no publicEvents"):
            ashkenaz.fetch_events(TODAY)
