"""Tests for the Old First Concerts parser, driven from a trimmed homepage
snapshot: title/date/time from the product-link anchor text, year roll-forward
with the weekday guard, image-only-link dedup, and window enforcement."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from foghorn.scrapers import old_first_concerts

FIXTURE = Path(__file__).parent.parent / "fixtures" / "old_first_concerts_2026_07.html"
TODAY = dt.date(2026, 7, 19)


def test_parses_all_menu_concerts() -> None:
    shows = old_first_concerts.parse_html(FIXTURE.read_text(encoding="utf-8"), TODAY)
    assert [(s.start_local.isoformat(), s.headliner_raw) for s in shows] == [
        ("2026-08-21T20:00:00", "San Francisco International Piano Festival – Opening Night"),
        ("2026-08-23T16:00:00", "San Francisco International Piano Festival – Alexandre Dossin"),
        (
            "2026-08-28T20:00:00",
            "San Francisco International Piano Festival – Stephen Prutsman and TNTeague Duo",
        ),
        ("2026-08-30T16:00:00", "San Francisco International Piano Festival – Festival Finale"),
        ("2026-09-06T16:00:00", "Mike Greensill & Friends – Celebrating his 80th birthday!"),
        ("2026-09-13T16:00:00", "Pianist Kevin Lee Sun & Friends – Look to This Day"),
        ("2026-09-20T16:00:00", "Noël Wan – Les fleurs du mal"),
    ]


def test_product_page_is_ticket_and_source_url() -> None:
    show = old_first_concerts.parse_html(FIXTURE.read_text(encoding="utf-8"), TODAY)[0]
    assert show.ticket_url == show.source_url
    assert show.source_url is not None and "/performance/" in show.source_url


def test_weekday_guard_drops_stale_entries() -> None:
    # "Friday, August 21" matches 2026 — but from a today late enough that the
    # roll-forward lands in 2027 (where Aug 21 is a Saturday), the entry drops
    # instead of being pinned to a wrong year.
    shows = old_first_concerts.parse_html(
        FIXTURE.read_text(encoding="utf-8"), dt.date(2026, 10, 1)
    )
    assert shows == []


def test_window_excludes_far_out_dates() -> None:
    shows = old_first_concerts.parse_html(
        FIXTURE.read_text(encoding="utf-8"), TODAY, window_days=40
    )
    assert [s.start_local.date().isoformat() for s in shows] == [
        "2026-08-21",
        "2026-08-23",
        "2026-08-28",
    ]
