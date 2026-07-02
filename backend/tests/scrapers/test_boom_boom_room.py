"""Tests for the Boom Boom Room (rhp-events list view) HTML parser.

Fixture-driven and deterministic: ``parse_html`` takes an injected ``today`` so
the 90-day window doesn't depend on the clock. The fixture
(``fixtures/boom_boom_room_2026_07.html``) is a trimmed snapshot of the live
``/events/`` page exercising the edge cases — two shows on one day, "Doors: //
Show:" time lines with and without minutes, a bare unlabeled time (no doors),
an event with no Buy Tickets CTA, comedy/karaoke nights to drop, curly quotes
and accents in titles, and an event under a later month separator that falls
outside the window.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from foghorn.models import ScrapedShow
from foghorn.scrapers import boom_boom_room

FIXTURE = Path(__file__).parent.parent / "fixtures" / "boom_boom_room_2026_07.html"
TODAY = dt.date(2026, 7, 2)

DAY_PARTY = (
    "Boom Boom’s Day Party SAT w/ *MUZIEK* ~ “Tribute to MARVIN & MAZE” ~ "
    "BBR FILLMORE FEST ~ (no cover all day!)"
)
RICKY_G = "RICKY G & THE ALL-STAR FUNK THROWDOWN (ft. mbrs of KARL DENSON’S TINY UNIVERSE+)"


@pytest.fixture
def parsed() -> list[ScrapedShow]:
    return boom_boom_room.parse_html(FIXTURE.read_text(encoding="utf-8"), today=TODAY)


def test_returns_expected_shows_sorted(parsed: list[ScrapedShow]) -> None:
    got = [(s.start_local.isoformat(), s.headliner_raw) for s in parsed]
    assert got == [
        ("2026-07-02T21:15:00", "SHELDON ALEXANDER FUNK JAM! (no cover charge)"),
        ("2026-07-04T15:00:00", DAY_PARTY),  # afternoon show, curly quotes
        ("2026-07-04T20:30:00", RICKY_G),  # same day, evening show
        # Source title has a double space after "KATDELIC"; whitespace collapses.
        ("2026-07-17T21:00:00", "KATDELIC (*P-Funk Allstar & Grammy Winner Ronkat*) w/ SONAMÓ"),
        ("2026-07-25T21:00:00", "FUNK NUGGET & LOMA ALTA"),
        ("2026-07-29T21:00:00", "NO MERCY BAND (no cover charge!)"),
    ]


def test_doors_parsed_from_time_line(parsed: list[ScrapedShow]) -> None:
    # "Doors: 7 pm // Show: 9:15 pm" — doors and a start with minutes.
    sheldon = parsed[0]
    assert sheldon.start_local == dt.datetime(2026, 7, 2, 21, 15)
    assert sheldon.doors_local == dt.datetime(2026, 7, 2, 19, 0)


def test_bare_time_is_start_with_no_doors(parsed: list[ScrapedShow]) -> None:
    # NO MERCY BAND's time line is just "9 pm" — treated as the start.
    no_mercy = next(s for s in parsed if s.headliner_raw.startswith("NO MERCY"))
    assert no_mercy.start_local == dt.datetime(2026, 7, 29, 21, 0)
    assert no_mercy.doors_local is None


def test_excludes_non_music_nights(parsed: list[ScrapedShow]) -> None:
    titles = {s.headliner_raw for s in parsed}
    assert not any("COMEDY" in t for t in titles)
    assert not any("KARAOKE" in t for t in titles)


def test_excludes_out_of_window(parsed: list[ScrapedShow]) -> None:
    # TEA POT LOGIC sits under the "October 2026" separator — Oct 15 is ~105
    # days past the pinned today (> 90-day window).
    assert not any(s.headliner_raw.startswith("TEA POT LOGIC") for s in parsed)


def test_window_size_is_respected() -> None:
    # A 7-day window from today catches only the July 2 and July 4 shows.
    shows = boom_boom_room.parse_html(
        FIXTURE.read_text(encoding="utf-8"), today=TODAY, window_days=7
    )
    assert [s.start_local.date().isoformat() for s in shows] == [
        "2026-07-02",
        "2026-07-04",
        "2026-07-04",
    ]


def test_ticket_url_captured_when_present(parsed: list[ScrapedShow]) -> None:
    sheldon = parsed[0]
    assert sheldon.ticket_url == (
        "https://www.etix.com/ticket/p/51992228/"
        "sheldon-alexander-funk-jamno-cover-charge-san-francisco-the-boom-boom-room"
        "?partner_id=100"
    )


def test_ticket_url_none_when_absent(parsed: list[ScrapedShow]) -> None:
    funk_nugget = next(s for s in parsed if s.headliner_raw == "FUNK NUGGET & LOMA ALTA")
    assert funk_nugget.ticket_url is None


def test_source_url_is_per_event_page(parsed: list[ScrapedShow]) -> None:
    sheldon = parsed[0]
    assert sheldon.source_url == (
        "https://boomboomroom.com/event/sheldon-alexander-funk-jam-no-cover-charge-3/"
        "client-club-demo/san-francisco-california/"
    )


def test_optional_fields_default(parsed: list[ScrapedShow]) -> None:
    show = parsed[0]
    assert show.venue_slug == "boom_boom_room"
    assert show.support_raw == []
    assert show.price_text is None  # list view carries no price data


def test_year_inferred_without_separator() -> None:
    # With no month separator, a date whose month/day already passed this year
    # must land in the next year — the page never lists past shows.
    html = """
    <div class="rhpSingleEvent">
      <a id="eventTitle" href="https://boomboomroom.com/event/nye-band/">NYE HANGOVER BAND</a>
      <div id="eventDate">Wed, Jan 06</div>
      <span class="rhp-event__time-text--list">Doors: 8 pm // Show: 9 pm</span>
    </div>
    """
    shows = boom_boom_room.parse_html(html, today=dt.date(2026, 12, 30))
    assert [s.start_local for s in shows] == [dt.datetime(2027, 1, 6, 21, 0)]
