"""Tests for the Meyhouse Jazz (Wix scheduling JSON) scraper: UTC→local
conversion, fullwidth-paren seating-suffix + site-suffix stripping, and the
Palo Alto location filter."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from foghorn.scrapers import meyhouse_jazz

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_event_page_parses_scheduling_and_cleans_title() -> None:
    page = (FIXTURES / "meyhouse_event.html").read_text()
    show = meyhouse_jazz.parse_event_page(page, "https://www.meyhousejazz.com/e")
    assert show is not None
    # 2026-07-26T00:00Z == Sat 7/25 5pm PDT; fullwidth "（Sat 7/25 - 5pm)"
    # and "| Meyhouse Jazz" both come off the billing.
    assert show.headliner_raw == "Michael Wolff Remembers Cal Tjader"
    assert show.start_local == dt.datetime(2026, 7, 25, 17, 0)
    assert show.ticket_url == "https://www.meyhousejazz.com/e"


def test_non_palo_alto_stage_is_dropped() -> None:
    page = (FIXTURES / "meyhouse_event_sanramon.html").read_text()
    assert meyhouse_jazz.parse_event_page(page, "u") is None


def test_listing_links_dedupe() -> None:
    html = (
        '<a href="https://www.meyhousejazz.com/event-details/a">1</a>'
        '<a href="https://www.meyhousejazz.com/event-details/a">2</a>'
        '<a href="https://www.meyhousejazz.com/event-details/b">3</a>'
    )
    assert meyhouse_jazz.parse_event_links(html) == [
        "https://www.meyhousejazz.com/event-details/a",
        "https://www.meyhousejazz.com/event-details/b",
    ]
