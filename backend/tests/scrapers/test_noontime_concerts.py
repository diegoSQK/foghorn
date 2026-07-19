"""Tests for the Noontime Concerts parser, driven from a trimmed snapshot of
the server-rendered ``/upcoming-concerts/`` Concert Calendar. The card's
``data-date`` is the performance date — the site's ``concerts`` REST CPT
carries only WP post publish dates (empty ``acf``/``meta``, no content),
which is why this surface exists at all — so the tests pin that dates come
from the cards, plus the series-constant 12:30 start, the Mint-Sunday skip,
malformed-date handling, and window enforcement."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from foghorn.scrapers import noontime_concerts

FIXTURE = Path(__file__).parent.parent / "fixtures" / "noontime_concerts_2026_07.html"
TODAY = dt.date(2026, 7, 19)


def test_parses_cards_with_series_start_time() -> None:
    shows = noontime_concerts.parse_html(FIXTURE.read_text(encoding="utf-8"), TODAY)
    assert [(s.start_local.isoformat(), s.headliner_raw) for s in shows] == [
        (
            "2026-08-11T12:30:00",
            "Musicians of Old Saint Mary's Cathedral and Chinese Mission",
        ),
        ("2026-08-25T12:30:00", "SF Piano Festival Presents Karina Tseng"),
    ]


def test_source_url_is_detail_page_without_tracking_query() -> None:
    shows = noontime_concerts.parse_html(FIXTURE.read_text(encoding="utf-8"), TODAY)
    assert shows[1].source_url == (
        "https://noontimeconcerts.org/concerts/"
        "san-francisco-piano-festival-presents-karina-tseng/"
    )
    assert all("?" not in s.source_url for s in shows)


def test_card_date_wins_over_any_publish_date() -> None:
    # The performance date must come from data-date — a card published (and
    # dated by WP) in July still parses to its August concert date.
    shows = noontime_concerts.parse_html(FIXTURE.read_text(encoding="utf-8"), TODAY)
    assert [s.start_local.date().isoformat() for s in shows] == [
        "2026-08-11",
        "2026-08-25",
    ]


def _card(date: str, title: str) -> str:
    return (
        f'<div class="concert-card" data-title="{title}" data-vid="" '
        f'data-date="{date}"><div class="concert-details">'
        f'<h3 class="concert-date">{date}</h3>'
        f'<p class="concert-title"><strong>{title}</strong></p>'
        "</div></div>"
    )


def test_malformed_or_missing_date_drops_card() -> None:
    html = (
        _card("TBA", "Date To Be Announced")
        + '<div class="concert-card" data-title="No Date At All" data-vid=""></div>'
        + _card("08/11/2026", "Real Concert")
    )
    shows = noontime_concerts.parse_html(html, TODAY)
    assert [s.headliner_raw for s in shows] == ["Real Concert"]


def test_non_tuesday_mint_cards_are_skipped() -> None:
    # 2026-08-16 is a Sunday — the SF Mint series, a different room with no
    # stated time; it must not be attributed to Old St. Mary's.
    html = _card("08/16/2026", "Mint Sunday Special") + _card(
        "08/11/2026", "Tuesday Concert"
    )
    shows = noontime_concerts.parse_html(html, TODAY)
    assert [s.headliner_raw for s in shows] == ["Tuesday Concert"]


def test_window_excludes_far_out_dates() -> None:
    shows = noontime_concerts.parse_html(
        FIXTURE.read_text(encoding="utf-8"), TODAY, window_days=30
    )
    assert [s.start_local.date().isoformat() for s in shows] == ["2026-08-11"]
