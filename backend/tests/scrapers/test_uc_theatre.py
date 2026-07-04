"""Tests for The UC Theatre Webflow events-page parser.

Fixture-driven and deterministic: ``parse_html`` takes an injected ``today``
so the 90-day window doesn't depend on the clock. The fixture
(``fixtures/uc_theatre_2026_07.html``) is a trimmed snapshot of the live
``/events/`` CMS items exercising the edge cases — a no-support item whose
hidden Webflow button variant ("BUY TICKETS" with ``w-condition-invisible``)
sits next to the visible priced one, a single- and a multi-act support line,
an unpriced/untagged item (empty genre and bare BUY TICKETS button), an item
on the exact window boundary (Oct 1 = today + 90, inclusive), an out-of-window
multi-support item (Oct 8), and a next-calendar-year item (Feb 17 — dates
carry no year). One item is synthesized from the same real markup because no
live example existed at snapshot time: a Comedy-tagged card (the non-music
genre filter).
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from foghorn.models import ScrapedShow
from foghorn.scrapers import uc_theatre

FIXTURE = Path(__file__).parent.parent / "fixtures" / "uc_theatre_2026_07.html"
TODAY = dt.date(2026, 7, 3)


@pytest.fixture
def parsed() -> list[ScrapedShow]:
    return uc_theatre.parse_html(FIXTURE.read_text(encoding="utf-8"), today=TODAY)


def test_returns_expected_shows_sorted(parsed: list[ScrapedShow]) -> None:
    got = [(s.start_local.isoformat(), s.headliner_raw) for s in parsed]
    assert got == [
        ("2026-07-11T20:00:00", 'Babyface Ray x 42 Dugg "4 The Trenches Tour"'),
        ("2026-07-28T20:00:00", "Jazz Is Dead: Marcos Valle"),
        ("2026-08-01T20:00:00", "John and The Locals"),
        ("2026-10-01T20:00:00", "Fruit Bats"),
    ]


def test_window_boundary_inclusive(parsed: list[ScrapedShow]) -> None:
    # Fruit Bats is Oct 1 = TODAY + exactly 90 days: inclusive, kept.
    assert any(s.headliner_raw == "Fruit Bats" for s in parsed)


def test_support_single_act(parsed: list[ScrapedShow]) -> None:
    marcos = next(s for s in parsed if s.headliner_raw == "Jazz Is Dead: Marcos Valle")
    assert marcos.support_raw == ["Fabiano do Nascimento"]
    assert marcos.genre == "jazz"


def test_support_multi_act_split() -> None:
    # Dying Fetus (Oct 8) is outside the default window; widen it to check the
    # comma-split of the three-act support line.
    wide = uc_theatre.parse_html(
        FIXTURE.read_text(encoding="utf-8"), today=TODAY, window_days=120
    )
    dying_fetus = next(s for s in wide if s.headliner_raw == "DYING FETUS AND SANGUISUGABOGG")
    assert dying_fetus.support_raw == ["Crowbar", "Left to Suffer", "Deterioration"]
    assert dying_fetus.start_local == dt.datetime(2026, 10, 8, 18, 30)
    assert dying_fetus.doors_local == dt.datetime(2026, 10, 8, 17, 30)


def test_doors_and_showtime(parsed: list[ScrapedShow]) -> None:
    babyface = parsed[0]
    assert babyface.start_local == dt.datetime(2026, 7, 11, 20, 0)
    assert babyface.doors_local == dt.datetime(2026, 7, 11, 19, 0)


def test_price_from_visible_button_variant(parsed: list[ScrapedShow]) -> None:
    # The hidden "BUY TICKETS" variant (w-condition-invisible) is skipped; the
    # visible one carries the price tail.
    babyface = parsed[0]
    assert babyface.price_text == "$40 + FEES"


def test_unpriced_and_untagged_item(parsed: list[ScrapedShow]) -> None:
    # John and The Locals: bare BUY TICKETS button and empty genre div.
    john = next(s for s in parsed if s.headliner_raw == "John and The Locals")
    assert john.price_text is None
    assert john.genre is None
    assert john.support_raw == []


def test_ticket_and_source_urls(parsed: list[ScrapedShow]) -> None:
    # Tickets sell through the venue's own per-show page: ticket_url and
    # source_url are the same absolute URL.
    babyface = parsed[0]
    expected = "https://www.theuctheatre.org/shows/babyface-ray-x-42-dugg-4-the-streets-tour-11-jul"
    assert babyface.ticket_url == expected
    assert babyface.source_url == expected


def test_excludes_out_of_window_with_year_rollover(parsed: list[ScrapedShow]) -> None:
    # "Feb 17" resolves forward to 2027-02-17 (~229 days out): excluded at the
    # default window and still excluded at 200 days.
    assert not any("BOUNCING SOULS" in s.headliner_raw for s in parsed)
    wide = uc_theatre.parse_html(
        FIXTURE.read_text(encoding="utf-8"), today=TODAY, window_days=200
    )
    assert not any("BOUNCING SOULS" in s.headliner_raw for s in wide)


def test_year_rollover_resolves_forward() -> None:
    # At 400 days the Feb item is in-window and lands in the *next* year.
    wide = uc_theatre.parse_html(
        FIXTURE.read_text(encoding="utf-8"), today=TODAY, window_days=400
    )
    souls = next(s for s in wide if "BOUNCING SOULS" in s.headliner_raw)
    assert souls.start_local == dt.datetime(2027, 2, 17, 19, 0)
    assert souls.support_raw == ["The Suicide Machines", "The Aggrolites", "Dead Bars"]


def test_non_music_genre_dropped(parsed: list[ScrapedShow]) -> None:
    # The Comedy-tagged item (Sep 25) is in-window, so its absence is the
    # genre filter, not the date filter.
    assert not any(s.headliner_raw == "Berkeley Comedy Night" for s in parsed)


def test_optional_fields_default(parsed: list[ScrapedShow]) -> None:
    show = parsed[0]
    assert show.venue_slug == "uc_theatre"
    assert show.genre == "hip-hop/rap"  # per-event genre passed through
