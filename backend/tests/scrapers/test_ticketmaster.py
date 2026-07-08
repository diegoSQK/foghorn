"""Tests for the shared Ticketmaster Discovery parser (The Fillmore /
Regency Ballroom). Fixture is a trimmed live Discovery payload for the
Fillmore plus three synthesized edge events (cancelled, TBA time, far
future) — documented in the fixture-builder in the shipping PR."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from foghorn.models import ScrapedShow
from foghorn.scrapers import regency_ballroom, the_fillmore
from foghorn.scrapers._ticketmaster import parse_events

FIXTURE = Path(__file__).parent.parent / "fixtures" / "ticketmaster_fillmore_2026_07.json"
TODAY = dt.date(2026, 7, 7)


@pytest.fixture
def parsed() -> list[ScrapedShow]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return parse_events(payload, "the_fillmore", today=TODAY)


def test_events_parsed_sorted_with_bills(parsed: list[ScrapedShow]) -> None:
    got = [(s.start_local.isoformat(), s.headliner_raw, s.support_raw) for s in parsed]
    assert got[:3] == [
        ("2026-07-24T20:00:00", "Chance Peña", []),
        ("2026-07-25T20:00:00", "Chance Peña", ["Hans Williams"]),
        ("2026-08-05T20:00:00", "Old 97's", ["River Shook"]),
    ]
    assert len(got) == 6


def test_genre_passthrough(parsed: list[ScrapedShow]) -> None:
    by_name = {s.headliner_raw: s.genre for s in parsed}
    assert by_name["Chance Peña"] == "Rock / Pop / Music"
    assert by_name["Pi'erre Bourne"] == "Hip-Hop/Rap / Trap / Music"


def test_cancelled_tba_and_out_of_window_skipped(parsed: list[ScrapedShow]) -> None:
    names = {s.headliner_raw for s in parsed}
    assert "Cancelled Act" not in names  # status code drop
    assert "TBA Act" not in names  # no local time — never invented
    assert "Far Future Act" not in names  # outside the window


def test_ticket_and_source_urls(parsed: list[ScrapedShow]) -> None:
    show = parsed[0]
    assert show.ticket_url and "ticketmaster.com" in show.ticket_url
    assert show.source_url == show.ticket_url
    assert show.doors_local is None  # not exposed by the API


def test_missing_key_raises_clearly(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Isolate from the developer's real gitignored backend/.env.
    import foghorn.localenv as localenv

    monkeypatch.setattr(localenv, "_ENV_PATH", tmp_path / "absent.env")
    monkeypatch.setattr(localenv, "_loaded", False)
    monkeypatch.delenv("TM_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="TM_API_KEY not set"):
        the_fillmore.scrape()


def test_venue_ids_distinct() -> None:
    assert the_fillmore.TM_VENUE_ID != regency_ballroom.TM_VENUE_ID
    assert the_fillmore.VENUE_SLUG == "the_fillmore"
    assert regency_ballroom.VENUE_SLUG == "regency_ballroom"
