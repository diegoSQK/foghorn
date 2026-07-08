"""Tests for the SJZ Break Room (San Jose Jazz) parsers.

Fixture-driven and deterministic: both parsers take an injected ``today`` so
the sitemap lookback and the 90-day window don't depend on the clock. The
fixtures are trimmed snapshots of the live site — the Yoast event sitemap and
the server-rendered event detail heroes — with dates shifted around the pinned
today to exercise the edges: a free jam (doors with a ";" separator), a
ticketed show (minutes in the doors time, CTA rendered as a link), an
in-window event at a different venue, a past event, and a far-future event.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from foghorn.models import ScrapedShow
from foghorn.scrapers import sjz_break_room

FIXTURES = Path(__file__).parent.parent / "fixtures"
TODAY = dt.date(2026, 7, 7)


def _parse(name: str) -> ScrapedShow | None:
    html = (FIXTURES / f"sjz_break_room_2026_07_event_{name}.html").read_text(encoding="utf-8")
    return sjz_break_room.parse_event_page(
        html, f"https://sanjosejazz.org/events/{name}/", today=TODAY
    )


def test_sitemap_keeps_recent_event_pages_only() -> None:
    xml = (FIXTURES / "sjz_break_room_2026_07_sitemap.xml").read_text(encoding="utf-8")
    urls = sjz_break_room.parse_sitemap(xml, today=TODAY)
    # The 2020 entry is outside the lookback; the bare /events/ archive URL is
    # not a detail page. Sitemap order is preserved.
    assert urls == [
        "https://sanjosejazz.org/events/jc-smith-2/",
        "https://sanjosejazz.org/events/wepa-fest/",
        "https://sanjosejazz.org/events/sjz-break-room-jazz-jam-ft-summer-jazz-camp-faculty/",
    ]


def test_sitemap_lookback_is_respected() -> None:
    xml = (FIXTURES / "sjz_break_room_2026_07_sitemap.xml").read_text(encoding="utf-8")
    # A 45-day lookback (cutoff 2026-05-23) drops the March entry too.
    urls = sjz_break_room.parse_sitemap(xml, today=TODAY, lookback_days=45)
    assert urls == [
        "https://sanjosejazz.org/events/wepa-fest/",
        "https://sanjosejazz.org/events/sjz-break-room-jazz-jam-ft-summer-jazz-camp-faculty/",
    ]


def test_free_jam_parsed() -> None:
    show = _parse("jam")
    assert show is not None
    assert show.headliner_raw == "SJZ Break Room Jazz Jam Ft. Summer Jazz Camp Faculty"
    assert show.start_local == dt.datetime(2026, 7, 10, 19, 0)  # 7pm showtime
    assert show.doors_local == dt.datetime(2026, 7, 10, 17, 0)  # "5pm Doors;"
    assert show.price_text == "Free Admission"
    assert show.ticket_url is None  # free show: CTA is an inert <span>
    assert show.source_url == "https://sanjosejazz.org/events/jam/"


def test_ticketed_show_parsed() -> None:
    show = _parse("ticketed")
    assert show is not None
    assert show.headliner_raw == "Dolphin Hyperspace"
    assert show.start_local == dt.datetime(2026, 7, 25, 20, 0)  # 8pm showtime
    assert show.doors_local == dt.datetime(2026, 7, 25, 18, 30)  # "6:30pm Doors,"
    assert show.price_text == "$27 (Incl. fees)"
    assert show.ticket_url == "https://tix.sanjosejazz.org/e/dolphin-hyperspace"


def test_other_venue_dropped() -> None:
    # ¡WEPA! Fest is in-window but at Parque de los Pobladores, not the Break Room.
    assert _parse("other_venue") is None


def test_past_event_dropped() -> None:
    # Verbatim live page: "Fri, Jun 5" is before the pinned today.
    assert _parse("past") is None


def test_far_future_event_dropped() -> None:
    # "Sat, Dec 12" is ~158 days out — beyond the 90-day window.
    assert _parse("far_future") is None


def test_window_size_is_respected() -> None:
    html = (FIXTURES / "sjz_break_room_2026_07_event_ticketed.html").read_text(encoding="utf-8")
    # Jul 25 is 18 days from the pinned today; a 10-day window excludes it.
    assert (
        sjz_break_room.parse_event_page(
            html, "https://sanjosejazz.org/events/x/", today=TODAY, window_days=10
        )
        is None
    )


def test_weekday_mismatch_dropped() -> None:
    # A stale page whose month/day recurs in-window but on the wrong weekday
    # (2026-07-10 is a Friday, not a Saturday) must not produce a show.
    html = (FIXTURES / "sjz_break_room_2026_07_event_jam.html").read_text(encoding="utf-8")
    html = html.replace("Fri, Jul 10", "Sat, Jul 10")
    assert (
        sjz_break_room.parse_event_page(
            html, "https://sanjosejazz.org/events/x/", today=TODAY
        )
        is None
    )


def test_optional_fields_default() -> None:
    show = _parse("jam")
    assert show is not None
    assert show.venue_slug == "sjz_break_room"
    assert show.support_raw == []
    assert show.event_type is None
    assert show.genre is None
