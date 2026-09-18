"""Bill Graham Civic parser tests (#131).

The fixture is six real ``article.event`` blocks captured from the live
calendar on 2026-09-18, plus two synthesised from real markup to exercise the
drop rules (a cancelled show and a comedy booking). The room runs a **newer
generation** of the APE theme than the Fox and the Greek, so these also pin
that ``_ape_listing`` reads both — `test_ape_listing_variants` covers the
shared side.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from foghorn.models import ScrapedShow
from foghorn.scrapers import bill_graham_civic as bgc

FIXTURE = (
    Path(__file__).parent.parent / "fixtures" / "bill_graham_civic_calendar.html"
)
TODAY = dt.date(2026, 9, 18)


@pytest.fixture
def shows() -> list[ScrapedShow]:
    return bgc.parse_html(FIXTURE.read_text(encoding="utf-8"), TODAY, 200)


def _named(shows: list[ScrapedShow], fragment: str) -> list[ScrapedShow]:
    return [s for s in shows if fragment.lower() in s.headliner_raw.lower()]


def test_parses_the_listed_shows(shows: list[ScrapedShow]) -> None:
    assert shows
    assert all(s.venue_slug == "bill_graham_civic" for s in shows)
    assert shows == sorted(shows, key=lambda s: s.start_local)


def test_start_times_are_local_and_exact(shows: list[ScrapedShow]) -> None:
    """The newer template's content attribute is already unambiguous
    ("2026-09-19 19:00"), unlike the older free-text form."""
    aoki = _named(shows, "Steve Aoki")[0]
    assert aoki.start_local == dt.datetime(2026, 9, 19, 19, 0)


def test_support_acts_land_as_support(shows: list[ScrapedShow]) -> None:
    """Acceptance: Bonnie Raitt 10/10 carries Jon Cleary as support rather
    than concatenated into the headliner."""
    raitt = _named(shows, "Bonnie Raitt")[0]
    assert raitt.headliner_raw == "Bonnie Raitt"
    assert raitt.support_raw == ["Jon Cleary & The Absolute Monster Gentlemen"]


def test_multiple_support_acts_split_on_br(shows: list[ScrapedShow]) -> None:
    aoki = _named(shows, "Steve Aoki")[0]
    assert aoki.support_raw == ["FARRUKO", "Riot Ten", "HIGHSOCIETY"]


def test_a_two_night_run_is_two_rows(shows: list[ScrapedShow]) -> None:
    """Acceptance: the two Sara Bareilles nights produce two rows."""
    nights = sorted(s.start_local.date() for s in _named(shows, "Bareilles"))
    assert nights == [dt.date(2026, 10, 16), dt.date(2026, 10, 17)]


def test_sold_out_shows_still_ingest(shows: list[ScrapedShow]) -> None:
    """They're real events — someone with a ticket still wants them listed,
    and the watchlist should still match."""
    assert _named(shows, "Steve Lacy")
    assert _named(shows, "Bareilles")


def test_cancelled_shows_are_dropped(shows: list[ScrapedShow]) -> None:
    assert not _named(shows, "Cancelled Act")


def test_rescheduled_shows_are_kept(shows: list[ScrapedShow]) -> None:
    """A rescheduled show keeps a topline banner but is still happening — on
    the new date the template already shows."""
    aoki = _named(shows, "Steve Aoki")[0]
    assert aoki.start_local.date() == dt.date(2026, 9, 19)


def test_non_music_bookings_are_dropped(shows: list[ScrapedShow]) -> None:
    assert not _named(shows, "Some Comedian")


def test_per_show_provenance(shows: list[ScrapedShow]) -> None:
    aoki = _named(shows, "Steve Aoki")[0]
    assert aoki.source_url == "https://billgrahamcivic.com/events/steve-aoki-260220"
    assert aoki.ticket_url and "ticketmaster.com" in aoki.ticket_url


def test_no_prices_on_this_template(shows: list[ScrapedShow]) -> None:
    assert all(s.price_text is None for s in shows)


def test_doors_time_is_read(shows: list[ScrapedShow]) -> None:
    aoki = _named(shows, "Steve Aoki")[0]
    assert aoki.doors_local == dt.datetime(2026, 9, 19, 19, 0)


def test_window_is_respected() -> None:
    """A 3-day window from the 18th reaches the 21st, so it catches the 19th
    and excludes the 22nd."""
    shows = bgc.parse_html(FIXTURE.read_text(encoding="utf-8"), TODAY, window_days=3)
    assert [s.start_local.date() for s in shows] == [dt.date(2026, 9, 19)]


def test_registered_under_its_slug() -> None:
    from foghorn.scrapers import REGISTERED_SCRAPERS

    assert REGISTERED_SCRAPERS["bill_graham_civic"] is bgc.scrape


def test_seeded() -> None:
    from foghorn.repo.seed_venues import SEED_VENUES

    venue = next(v for v in SEED_VENUES if v.slug == "bill_graham_civic")
    assert venue.neighborhood == "Civic Center"
    assert venue.region == "SF"
    assert venue.calendar_url == bgc.CALENDAR_URL
