"""Tests for the August Hall HTML parsers.

Fixture-driven and deterministic: ``parse_html`` takes an injected ``today``
(the deployment's list dates carry a year, so only the window depends on it)
and an injected ``time_lookup`` standing in for the per-event page fetches
the live scraper does — this deployment renders no show time on its list
pages. The list fixture (``fixtures/august_hall_2026_07.html``) is a trimmed
snapshot of the live ``/events/`` page; the event fixture
(``..._event_earlybirds.html``) is the per-event page the time comes from.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from foghorn.models import ScrapedShow
from foghorn.scrapers import august_hall
from foghorn.scrapers._ticketweb_calendar import find_next_page_url, parse_event_page_time

FIXTURES = Path(__file__).parent.parent / "fixtures"
FIXTURE = FIXTURES / "august_hall_2026_07.html"
EVENT_FIXTURE = FIXTURES / "august_hall_2026_07_event_earlybirds.html"
TODAY = dt.date(2026, 7, 3)

# Stand-in for the per-event page fetches: URL -> show time. Fulton Lee is
# deliberately absent to exercise the "no time -> skipped" path.
TIMES = {
    "https://www.augusthallsf.com/tm-event/earlybirds-club/": dt.time(18, 0),
    "https://www.augusthallsf.com/tm-event/low-cut-connie-moved-to-august-hall/": dt.time(19, 0),
    (
        "https://www.augusthallsf.com/tm-event"
        "/valerie-a-tribute-to-amy-winehouse-w-special-guest-huney-knuckles/"
    ): dt.time(19, 30),
    "https://www.augusthallsf.com/tm-event/the-exploited/": dt.time(18, 30),
}


@pytest.fixture
def parsed() -> list[ScrapedShow]:
    return august_hall.parse_html(
        FIXTURE.read_text(encoding="utf-8"), today=TODAY, time_lookup=TIMES.get
    )


def test_returns_expected_shows_sorted(parsed: list[ScrapedShow]) -> None:
    got = [(s.start_local.isoformat(), s.headliner_raw) for s in parsed]
    assert got == [
        ("2026-07-11T18:00:00", "Earlybirds Club"),
        ("2026-07-15T19:00:00", "Low Cut Connie"),  # "– Moved To August Hall" stripped
        (
            "2026-09-05T19:30:00",
            "Valerie – A Tribute to Amy Winehouse (w/special guest Huney Knuckles)",
        ),
        ("2026-09-18T18:30:00", "The Exploited"),
    ]


def test_row_without_known_time_skipped_not_invented(parsed: list[ScrapedShow]) -> None:
    # Fulton Lee (Jul 21) is in the window but TIMES has no entry for it.
    assert not any(s.headliner_raw.startswith("Fulton Lee") for s in parsed)


def test_no_time_lookup_means_no_shows() -> None:
    # The list rows genuinely carry no time; nothing can be parsed without one.
    assert august_hall.parse_html(FIXTURE.read_text(encoding="utf-8"), today=TODAY) == []


def test_window_size_is_respected() -> None:
    # A 20-day window from today keeps only the two July shows.
    shows = august_hall.parse_html(
        FIXTURE.read_text(encoding="utf-8"), today=TODAY, window_days=20, time_lookup=TIMES.get
    )
    assert [s.headliner_raw for s in shows] == [
        "Earlybirds Club",
        "Low Cut Connie",
    ]


def test_full_dates_carry_their_own_year() -> None:
    # "Saturday, July 11, 2026" must not be re-inferred from today: from a
    # late-December today, a bare "July 11" would roll to 2027 — the listed
    # 2026 date instead (correctly) falls out of the window entirely.
    shows = august_hall.parse_html(
        FIXTURE.read_text(encoding="utf-8"),
        today=dt.date(2026, 12, 20),
        time_lookup=TIMES.get,
    )
    assert shows == []


def test_event_page_time_parsed_from_fixture() -> None:
    assert parse_event_page_time(EVENT_FIXTURE.read_text(encoding="utf-8")) == dt.time(18, 0)


def test_ticket_url_is_ticketmaster(parsed: list[ScrapedShow]) -> None:
    early = next(s for s in parsed if s.headliner_raw == "Earlybirds Club")
    assert early.ticket_url == (
        "https://www.ticketmaster.com/earlybirds-club-san-francisco-california"
        "-07-11-2026/event/1C0064AEE5D90B35"
    )


def test_ticket_url_none_when_absent(parsed: list[ScrapedShow]) -> None:
    valerie = next(s for s in parsed if s.headliner_raw.startswith("Valerie"))
    assert valerie.ticket_url is None


def test_source_url_is_per_event_page(parsed: list[ScrapedShow]) -> None:
    early = next(s for s in parsed if s.headliner_raw == "Earlybirds Club")
    assert early.source_url == "https://www.augusthallsf.com/tm-event/earlybirds-club/"


def test_next_page_link_found() -> None:
    # The live tm-paginate block is kept in the fixture; scrape() walks it.
    assert (
        find_next_page_url(FIXTURE.read_text(encoding="utf-8"))
        == "https://www.augusthallsf.com/events/page/2/"
    )


def test_optional_fields_default(parsed: list[ScrapedShow]) -> None:
    # Nothing on this deployment publishes doors, prices, support lines,
    # per-event genres, or event types.
    for show in parsed:
        assert show.venue_slug == "august_hall"
        assert show.support_raw == []
        assert show.doors_local is None
        assert show.price_text is None
        assert show.event_type is None
        assert show.genre is None


def test_moved_annotations_resolved() -> None:
    from foghorn.scrapers.august_hall import _resolve_moved

    def _show(title: str) -> ScrapedShow:
        return ScrapedShow(
            venue_slug="august_hall",
            headliner_raw=title,
            start_local=dt.datetime(2026, 7, 15, 19, 0),
            source_url="https://example.com/x",
        )

    here = _resolve_moved(_show("Low Cut Connie – Moved To August Hall"))
    assert here is not None and here.headliner_raw == "Low Cut Connie"
    # Moved away: the destination venue's scraper carries it — drop here.
    assert _resolve_moved(_show("Futurebirds – MOVED TO THE CHAPEL")) is None
    plain = _resolve_moved(_show("Plain Old Band"))
    assert plain is not None and plain.headliner_raw == "Plain Old Band"
