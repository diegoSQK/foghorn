"""Tests for the Thee Stork Club SeeTickets-card parser.

Fixture-driven and deterministic: ``parse_html`` takes an injected ``today`` so
the 90-day window doesn't depend on the clock. The fixture
(``fixtures/thee_stork_club_2026_07.html``) is a trimmed snapshot of the live
``/calendar/`` list cards exercising the edge cases — a DJ-night card with an
empty headliners line (title fallback), a karaoke card (music-adjacent genre,
kept), a real supporting-talent list, a co-billed multi-act headliners line,
and a Mosswood Meltdown afterparty card whose venue line says "at Eli's Mile
High Club" (off-site, dropped). Two cards are synthesized from the same real
markup because no live example existed at snapshot time: a Stand-Up card (the
non-music genre filter) and a February card (year rollover — card dates carry
no year). It also carries the AJAX nonce script and the six-page pagination
strip the pager helpers read.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from foghorn.models import ScrapedShow
from foghorn.scrapers import thee_stork_club

FIXTURE = Path(__file__).parent.parent / "fixtures" / "thee_stork_club_2026_07.html"
TODAY = dt.date(2026, 7, 3)


@pytest.fixture
def parsed() -> list[ScrapedShow]:
    return thee_stork_club.parse_html(FIXTURE.read_text(encoding="utf-8"), today=TODAY)


def test_returns_expected_shows_sorted(parsed: list[ScrapedShow]) -> None:
    got = [(s.start_local.isoformat(), s.headliner_raw) for s in parsed]
    assert got == [
        ("2026-07-03T21:00:00", "Queer Club Classics w/ DJ Louie El Ser 7/3"),
        ("2026-07-06T20:00:00", "Freakyoke 7/6"),
        ("2026-07-09T20:00:00", "Cave Clove"),
        ("2026-07-14T21:00:00", "Lana Del Rabies"),
    ]


def test_empty_headliners_falls_back_to_title(parsed: list[ScrapedShow]) -> None:
    # DJ-night cards leave p.headliners empty; the card title is the billing.
    dj_night = parsed[0]
    assert dj_night.headliner_raw == "Queer Club Classics w/ DJ Louie El Ser 7/3"
    assert dj_night.support_raw == []
    assert dj_night.genre == "dj/dance"


def test_karaoke_genre_kept(parsed: list[ScrapedShow]) -> None:
    # "Karaoke" is music-adjacent (ambiguous → keep), unlike Stand-Up.
    assert any(s.headliner_raw == "Freakyoke 7/6" for s in parsed)


def test_supporting_talent_parsed(parsed: list[ScrapedShow]) -> None:
    # "Supporting Talent: Hot Brother, Rowdy Boys" — label stripped, split.
    cave_clove = next(s for s in parsed if s.headliner_raw == "Cave Clove")
    assert cave_clove.support_raw == ["Hot Brother", "Rowdy Boys"]


def test_cobilled_headliners_split_top_billing_first(parsed: list[ScrapedShow]) -> None:
    # p.headliners "Lana Del Rabies, Trace Amount, Insula Iscariot": first is
    # the headliner, the rest join the supporting-talent act ("Ex-Heir").
    lana = next(s for s in parsed if s.headliner_raw == "Lana Del Rabies")
    assert lana.support_raw == ["Trace Amount", "Insula Iscariot", "Ex-Heir"]


def test_doors_and_showtime(parsed: list[ScrapedShow]) -> None:
    # "Doors at 8:00PM / Show at 9:00PM" — show is start, doors kept separately.
    lana = next(s for s in parsed if s.headliner_raw == "Lana Del Rabies")
    assert lana.start_local == dt.datetime(2026, 7, 14, 21, 0)
    assert lana.doors_local == dt.datetime(2026, 7, 14, 20, 0)


def test_price_and_ticket_and_source(parsed: list[ScrapedShow]) -> None:
    cave_clove = next(s for s in parsed if s.headliner_raw == "Cave Clove")
    expected_url = "https://wl.seetickets.us/event/cave-clove/691952?afflky=TheeStorkClub"
    assert cave_clove.price_text == "$10.00-$12.00"
    # The per-event SeeTickets page is both provenance and the ticket link.
    assert cave_clove.ticket_url == expected_url
    assert cave_clove.source_url == expected_url


def test_offsite_venue_card_dropped(parsed: list[ScrapedShow]) -> None:
    # The Mosswood Meltdown closing party's venue line says "at Eli's Mile
    # High Club" — not a Stork Club show, dropped despite being in-window.
    assert not any("Jenny Don't" in s.headliner_raw for s in parsed)


def test_non_music_genre_dropped(parsed: list[ScrapedShow]) -> None:
    # The Stand-Up card is dated Sep 20 — inside the 90-day window from
    # TODAY, so its absence is the genre filter, not the date filter.
    assert not any(s.headliner_raw == "Comedy Open Mic" for s in parsed)


def test_excludes_out_of_window_with_year_rollover(parsed: list[ScrapedShow]) -> None:
    # "Fri Feb 19" resolves forward to 2027-02-19 (~231 days out): excluded at
    # the default window and still excluded at 200 days.
    assert not any(s.headliner_raw == "Winter Formal" for s in parsed)
    wide = thee_stork_club.parse_html(
        FIXTURE.read_text(encoding="utf-8"), today=TODAY, window_days=200
    )
    assert not any(s.headliner_raw == "Winter Formal" for s in wide)


def test_year_rollover_resolves_forward() -> None:
    # At 400 days the Feb card is in-window and lands in the *next* year; its
    # "support tba" placeholder line stays empty.
    wide = thee_stork_club.parse_html(
        FIXTURE.read_text(encoding="utf-8"), today=TODAY, window_days=400
    )
    winter = next(s for s in wide if s.headliner_raw == "Winter Formal")
    assert winter.start_local == dt.datetime(2027, 2, 19, 21, 0)
    assert winter.support_raw == []


def test_pager_helpers_read_nonce_and_total_pages() -> None:
    html = FIXTURE.read_text(encoding="utf-8")
    assert thee_stork_club._extract_nonce(html) == "fbeb1c4846"
    assert thee_stork_club._extract_total_pages(html) == 6


def test_optional_fields_default(parsed: list[ScrapedShow]) -> None:
    dj_night = parsed[0]
    assert dj_night.venue_slug == "thee_stork_club"
    assert dj_night.doors_local is None  # show-time-only card
    assert dj_night.price_text == "$5.00"
