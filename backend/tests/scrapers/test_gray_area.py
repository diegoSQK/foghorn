"""Tests for the Gray Area (listing walk + JSON-LD event pages) scraper.

``parse_event_links`` is driven from a hand-built listing snippet covering
absolute/relative hrefs, dedup, and the pre-fetch slug filter (courses, the
book club, talks). ``parse_event_page`` is driven from a trimmed real event
page (``fixtures/gray_area_event_matmos.html``) whose Event node hides
inside a Yoast ``@graph`` next to WebPage/Organization nodes — the Yoast
site suffix comes off the name, the ISO offset drops to naive local, and
the in-house tickets link is captured.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from foghorn.scrapers import gray_area

FIXTURE = Path(__file__).parent.parent / "fixtures" / "gray_area_event_matmos.html"

LISTING = """
<a href="https://grayarea.org/event/matmos-with-dick-slessig-combo/">Matmos</a>
<a href="/event/aaa-kit-clayton/">Kit Clayton</a>
<a href="https://grayarea.org/event/matmos-with-dick-slessig-combo/">dup</a>
<a href="https://grayarea.org/event/online-intensive-course-personal-worldbuilding/">course</a>
<a href="https://grayarea.org/event/cybersentics-book-club-july-2026/">book club</a>
<a href="https://grayarea.org/event/creative-intelligence-more-than-human-systems/">talk</a>
<a href="https://grayarea.org/event/xr-show-tell-gray-area/">meetup</a>
"""


def test_listing_links_filtered_and_deduped() -> None:
    urls = gray_area.parse_event_links(LISTING)
    assert urls == [
        "https://grayarea.org/event/matmos-with-dick-slessig-combo/",
        "https://grayarea.org/event/aaa-kit-clayton/",
    ]


def test_event_page_parses_graph_event() -> None:
    url = "https://grayarea.org/event/matmos-with-dick-slessig-combo/"
    show = gray_area.parse_event_page(FIXTURE.read_text(encoding="utf-8"), url)
    assert show is not None
    assert show.venue_slug == "gray_area_art_and_technology"
    # Yoast's " - Gray Area" suffix is stripped; the presenter billing stays.
    assert (
        show.headliner_raw
        == "Recombinant Media Labs and Gray Area present Matmos with Dick Slessig Combo"
    )
    # "2026-08-15T20:00:00-07:00" → naive venue-local.
    assert show.start_local == dt.datetime(2026, 8, 15, 20, 0)
    assert show.ticket_url is not None and show.ticket_url.startswith(
        "https://tickets.grayarea.org/"
    )
    assert show.source_url == url


def test_date_suffix_comes_off_multi_night_names() -> None:
    page = FIXTURE.read_text(encoding="utf-8").replace(
        "present Matmos with Dick Slessig Combo - Gray Area",
        "present Matmos with Dick Slessig Combo Friday, August 15 - Gray Area",
    )
    show = gray_area.parse_event_page(page, "https://grayarea.org/event/x/")
    assert show is not None
    assert show.headliner_raw.endswith("Matmos with Dick Slessig Combo")


def test_page_without_event_node_returns_none() -> None:
    html = '<script type="application/ld+json">{"@type": "WebPage"}</script>'
    assert gray_area.parse_event_page(html, "https://grayarea.org/event/x/") is None
