"""Tests for the Great American Music Hall SeeTickets-card parser.

Fixture-driven and deterministic: ``parse_html`` takes an injected ``today`` so
the 90-day window doesn't depend on the clock. The fixture
(``fixtures/great_american_music_hall_2026_07.html``) is a trimmed snapshot of
the live ``/calendar/`` list cards exercising the edge cases — a "with …"
supporting-talent line (this site's flavor of the plugin), a multi-act support
list, a co-billed headliners line, a Sports General (FIFA watch party) card, a
"PRIVATE EVENT" hold card, a next-calendar-year card (dates carry no year),
and a bare "SOLD OUT" placeholder card with no times. It also carries the
SeeTickets AJAX nonce script — preceded by a decoy nonce from another
WordPress plugin, as on the live page — and the pagination strip the pager
helpers read.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from foghorn.models import ScrapedShow
from foghorn.scrapers import great_american_music_hall

FIXTURE = Path(__file__).parent.parent / "fixtures" / "great_american_music_hall_2026_07.html"
TODAY = dt.date(2026, 7, 2)


@pytest.fixture
def parsed() -> list[ScrapedShow]:
    return great_american_music_hall.parse_html(FIXTURE.read_text(encoding="utf-8"), today=TODAY)


def test_returns_expected_shows_sorted(parsed: list[ScrapedShow]) -> None:
    got = [(s.start_local.isoformat(), s.headliner_raw) for s in parsed]
    assert got == [
        ("2026-07-08T20:00:00", "Wolfmother"),
        ("2026-07-13T19:30:00", "Corrosion of Conformity"),
        ("2026-07-18T20:00:00", "Gabe Bondoc"),
        ("2026-09-05T20:00:00", "Pallbearer"),
    ]


def test_with_prefixed_support_parsed(parsed: list[ScrapedShow]) -> None:
    # GAMH's supporting-talent line reads "with Whores., Crobot" — the "with"
    # label is stripped and the rest comma-split.
    coc = next(s for s in parsed if s.headliner_raw == "Corrosion of Conformity")
    assert coc.support_raw == ["Whores.", "Crobot"]


def test_cobilled_headliners_split_top_billing_first(parsed: list[ScrapedShow]) -> None:
    # p.headliners "Gabe Bondoc, Jeremy Passion": first is headliner.
    gabe = next(s for s in parsed if s.headliner_raw == "Gabe Bondoc")
    assert gabe.support_raw == ["Jeremy Passion"]


def test_doors_and_showtime(parsed: list[ScrapedShow]) -> None:
    # "Event Doortime: 7:00PM / Event Showtime: 8:00PM" — show is start, doors
    # kept separately.
    wolfmother = next(s for s in parsed if s.headliner_raw == "Wolfmother")
    assert wolfmother.start_local == dt.datetime(2026, 7, 8, 20, 0)
    assert wolfmother.doors_local == dt.datetime(2026, 7, 8, 19, 0)


def test_price_and_ticket_and_source(parsed: list[ScrapedShow]) -> None:
    wolfmother = next(s for s in parsed if s.headliner_raw == "Wolfmother")
    expected_url = (
        "https://wl.seetickets.us/event/wolfmother-20th-anniversary-tour/"
        "669680?afflky=GreatAmericanMusicHall"
    )
    assert wolfmother.price_text == "$45.00-$50.00"
    # The per-event SeeTickets page is both provenance and the ticket link.
    assert wolfmother.ticket_url == expected_url
    assert wolfmother.source_url == expected_url


def test_excludes_out_of_window(parsed: list[ScrapedShow]) -> None:
    # "Sat Jan 9" resolves forward to 2027-01-09 (~191 days out): excluded at
    # the default 90-day window.
    assert not any(s.headliner_raw == "Eihwar" for s in parsed)


def test_year_rollover_resolves_forward() -> None:
    # At 250 days the Jan card is in-window and lands in the *next* year.
    wide = great_american_music_hall.parse_html(
        FIXTURE.read_text(encoding="utf-8"), today=TODAY, window_days=250
    )
    eihwar = next(s for s in wide if s.headliner_raw == "Eihwar")
    assert eihwar.start_local == dt.datetime(2027, 1, 9, 20, 0)


def test_sports_genre_dropped(parsed: list[ScrapedShow]) -> None:
    # The FIFA watch party is tagged "Sports General"; Jul 3 is inside the
    # window, so its absence is the genre filter, not the date filter.
    assert not any("Argentina" in s.headliner_raw for s in parsed)


def test_private_event_hold_card_dropped(parsed: list[ScrapedShow]) -> None:
    # "PRIVATE EVENT" (Aug 29, in-window) has times but no public billing; its
    # genre ("Other Content") is kept by house policy, so it's matched by name.
    assert not any(s.headliner_raw.lower() == "private event" for s in parsed)


def test_placeholder_card_without_times_skipped() -> None:
    # The bare "SOLD OUT - Thank You!" tile has no doors/show times: skipped
    # even when its date (Apr 2027) falls inside a 400-day window.
    wide = great_american_music_hall.parse_html(
        FIXTURE.read_text(encoding="utf-8"), today=TODAY, window_days=400
    )
    assert not any("SOLD OUT" in s.headliner_raw for s in wide)


def test_pager_helpers_read_nonce_and_total_pages() -> None:
    html = FIXTURE.read_text(encoding="utf-8")
    # The decoy nonce ("a5e2c23ecf") from another plugin appears first in the
    # file; the seetickets_ajax_obj anchor must win.
    assert great_american_music_hall._extract_nonce(html) == "0f13fb1395"
    assert great_american_music_hall._extract_total_pages(html) == 2


def test_optional_fields_default(parsed: list[ScrapedShow]) -> None:
    show = parsed[0]
    assert show.venue_slug == "great_american_music_hall"
    assert show.doors_local is not None  # doors are given on real cards
    assert show.price_text is not None
