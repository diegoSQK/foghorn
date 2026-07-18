"""Tests for the Indexical (listing + detail pages) scraper: slug dates +
meetup prefilter from the real listing's links, and detail parsing incl.
the "Event at" phrasing and FREE pricing."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from foghorn.scrapers import indexical

FIXTURES = Path(__file__).parent.parent / "fixtures"
TODAY = dt.date(2026, 7, 18)


def test_listing_links_filter_by_date_and_slug() -> None:
    listing = (FIXTURES / "indexical_listing.html").read_text()
    links = indexical.parse_event_links(listing, TODAY)
    # 8 links in the fixture: June ones are past, the 7/9 meetup is past
    # AND a meetup, the 7/23 open mic and 7/27 concert survive.
    assert [date.isoformat() for _url, date in links] == ["2026-07-23", "2026-07-27"]


def test_event_page_with_show_time_and_price() -> None:
    page = (FIXTURES / "indexical_event.html").read_text()
    show = indexical.parse_event_page(page, "https://indexical.org/e", dt.date(2026, 7, 27))
    assert show is not None
    assert show.headliner_raw.startswith("Indexical x Cabrillo Festival")
    assert show.start_local == dt.datetime(2026, 7, 27, 19, 0)
    assert show.doors_local == dt.datetime(2026, 7, 27, 18, 30)
    assert show.price_text == "$16"


def test_event_page_with_event_at_and_free() -> None:
    page = (FIXTURES / "indexical_event_free.html").read_text()
    show = indexical.parse_event_page(page, "https://indexical.org/e", dt.date(2026, 7, 23))
    assert show is not None
    assert show.start_local.time() == dt.time(19, 0)
    assert show.price_text == "Free"


def test_page_without_time_is_skipped() -> None:
    page = "<html><title>Indexical | X</title><body>no times here</body></html>"
    assert indexical.parse_event_page(page, "u", TODAY) is None
