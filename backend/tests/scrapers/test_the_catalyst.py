"""Tests for the Catalyst RHP events-list parser.

Fixture-driven and deterministic: ``parse_html`` takes an injected
``today`` (the year-less "Fri, Jul 24" dates hinge on it). The fixture
(``fixtures/the_catalyst_2026_07.html``) is a trimmed snapshot of the live
``/events/`` page exercising the edge cases — a card duplicated by the
page's grid variant (deduped; the copy has no time), a sister-venue promo
("**At Felton Music Hall**", dropped), a "**Rescheduled from 6/27**" note
(stripped from the title), a show-time-only card, and dates past the
90-day window.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from foghorn.models import ScrapedShow
from foghorn.scrapers import the_catalyst

FIXTURE = Path(__file__).parent.parent / "fixtures" / "the_catalyst_2026_07.html"
TODAY = dt.date(2026, 7, 19)


@pytest.fixture
def parsed() -> list[ScrapedShow]:
    return the_catalyst.parse_html(FIXTURE.read_text(encoding="utf-8"), today=TODAY)


def test_expected_shows_in_window(parsed: list[ScrapedShow]) -> None:
    got = [(s.start_local.isoformat(), s.headliner_raw) for s in parsed]
    # "Sports **At Felton Music Hall**" is a sister-venue promo (dropped);
    # Andre Nickatina (Nov 13) is past the 90-day window; Man Man appears
    # once despite the page's list+grid double render.
    assert got == [
        (
            "2026-07-24T18:00:00",
            "Spark in the Dark Gala featuring David J of Bauhaus and Love and Rockets",
        ),
        ("2026-08-07T21:00:00", "Live In The Atrium: Man Man"),
        ("2026-10-01T21:00:00", "Steel Pulse – Reggae Against Racism Tour"),
    ]


def test_doors_price_and_links(parsed: list[ScrapedShow]) -> None:
    man_man = next(s for s in parsed if "Man Man" in s.headliner_raw)
    assert man_man.doors_local == dt.datetime(2026, 8, 7, 20, 30)
    assert man_man.price_text == "$34.12"
    assert man_man.ticket_url is not None and "etix.com" in man_man.ticket_url
    assert man_man.source_url.startswith("https://catalystclub.com/event/")
    # The gala card states only a show time — doors stay unknown.
    gala = next(s for s in parsed if s.headliner_raw.startswith("Spark"))
    assert gala.doors_local is None


def test_rescheduled_note_stripped() -> None:
    shows = the_catalyst.parse_html(
        FIXTURE.read_text(encoding="utf-8"), today=TODAY, window_days=365
    )
    nickatina = next(s for s in shows if "Nickatina" in s.headliner_raw)
    # "Andre Nickatina **Rescheduled from 6/27**" loses the starred note
    # (and the year-less "Fri, Nov 13" resolves against injected today).
    assert nickatina.headliner_raw == "Andre Nickatina"
    assert nickatina.start_local == dt.datetime(2026, 11, 13, 21, 0)
