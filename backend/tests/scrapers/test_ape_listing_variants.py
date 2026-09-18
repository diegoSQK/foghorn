"""`_ape_listing` reads both generations of the APE theme (#131).

Fox Oakland and the Greek run the original markup; Bill Graham Civic runs a
newer one. Both are read here rather than forked, because the *rules* —
cancelled shows stay listed, non-music bookings need dropping, support lines
carry annotations — belong to the template, not the venue, and two copies
would drift. These tests pin the two shapes against one another so a change
made for one generation can't quietly break the other.
"""

from __future__ import annotations

import datetime as dt

import pytest

from foghorn.scrapers._ape_listing import _parse_content_datetime, parse_listing_html

TODAY = dt.date(2026, 9, 18)

CLASSIC = """
<div class="mix detail-information">
  <div class="topline">A Tour Name</div>
  <h2 class="show-title">Headline Act</h2>
  <div class="support">Opener One<br>Opener Two</div>
  <div class="single-date-show" content="October 10, 2026 8:00 pm"></div>
  <p>Doors: <span class="event__doors-open">7:00 pm</span></p>
  <div class="entry"><a href="/events/headline-act">More</a></div>
  <a itemprop="url" href="https://ticketmaster.com/x">Buy Tickets</a>
</div>
"""

MODERN = """
<article class="event">
  <header>
    <div class="topline">A Tour Name</div>
    <h2 class="show-title">Headline Act</h2>
    <div class="bottomline">Opener One<br>Opener Two</div>
  </header>
  <p class="event__start-date" content="2026-10-10 20:00">Sat Oct 10</p>
  <p>Doors: <span class="event__doors-open">7:00 pm</span></p>
  <a itemprop="url" href="https://ticketmaster.com/x">Buy Tickets</a>
  <a class="more-info" href="/events/headline-act">More Info</a>
</article>
"""


def _parse(markup: str) -> list:
    return parse_listing_html(
        markup,
        venue_slug="a_venue",
        today=TODAY,
        window_days=200,
        fallback_source_url="https://example.test/calendar/",
    )


def test_both_generations_yield_the_same_show() -> None:
    classic = _parse(CLASSIC)
    modern = _parse(MODERN)
    assert len(classic) == len(modern) == 1
    for field in (
        "headliner_raw",
        "support_raw",
        "start_local",
        "doors_local",
        "ticket_url",
        "source_url",
        "price_text",
    ):
        assert getattr(classic[0], field) == getattr(modern[0], field), field


def test_the_shared_rules_apply_to_the_new_markup() -> None:
    cancelled = MODERN.replace("A Tour Name", "SHOW CANCELLED")
    assert _parse(cancelled) == []
    comedy = MODERN.replace("A Tour Name", "An Evening of Comedy")
    assert _parse(comedy) == []


def test_a_mixed_page_parses_both() -> None:
    """Belt and braces for a theme caught mid-migration: pairing each block
    with its own selector set means a mixed page isn't half-empty."""
    both = _parse(CLASSIC + MODERN)
    assert len(both) == 2


@pytest.mark.parametrize(
    "content,expected",
    [
        ("October 10, 2026 8:00 pm", dt.datetime(2026, 10, 10, 20, 0)),
        ("July 7, 2026 8pm", dt.datetime(2026, 7, 7, 20, 0)),
        ("2026-10-10 20:00", dt.datetime(2026, 10, 10, 20, 0)),
        ("2026-10-10 20:00:00", dt.datetime(2026, 10, 10, 20, 0)),
        ("not a date", None),
    ],
)
def test_content_datetime_formats(content: str, expected: dt.datetime | None) -> None:
    assert _parse_content_datetime(content) == expected
