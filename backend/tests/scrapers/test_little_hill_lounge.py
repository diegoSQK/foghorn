"""Tests for the Little Hill Lounge (flyer OCR) scraper.

``parse_flyer`` is pure and driven from the real Vision OCR output of the
July 2026 flyer (``fixtures/little_hill_2026_07_ocr.json`` — 69
observations incl. the logo misreads and header/footer noise). Covered:
row pairing across the two columns (including descriptions whose OCR order
precedes their date line), multi-line continuation bills, comma-bill
splitting with "w/" prefixes and an unbalanced-parenthetical typo,
time-range starts, non-music skips (karaoke/bingo/movie/"OPEN FOR"), the
no-time row skipped rather than fabricated, and window enforcement. The
OCR step itself is macOS-only and exercised implicitly by live runs; here
``ocr_image`` is only asserted to fail cleanly off-macOS.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pytest

from foghorn.scrapers import little_hill_lounge
from foghorn.scrapers.little_hill_lounge import OcrLine

FIXTURE = (
    Path(__file__).parent.parent / "fixtures" / "little_hill_2026_07_ocr.json"
)


def _lines() -> list[OcrLine]:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return [OcrLine(r["text"], r["x"], r["y"], r["w"], r["h"]) for r in raw]


def _parse(today: dt.date) -> list:
    return little_hill_lounge.parse_flyer(_lines(), 2026, 7, today)


def test_full_month_counts_and_skips() -> None:
    shows = _parse(dt.date(2026, 7, 1))
    # 30 flyer rows → 24 shows: OPEN FOR 7/4, bingo 7/11, karaoke 7/18,
    # movie 7/20, and the time-less 7/28 row all drop.
    assert len(shows) == 24
    dates = {show.start_local.date().day for show in shows}
    assert {4, 11, 18, 20, 28}.isdisjoint(dates)
    assert all(show.venue_slug == "little_hill_lounge" for show in shows)


def test_continuation_line_joins_bill() -> None:
    shows = _parse(dt.date(2026, 7, 17))
    fri = next(s for s in shows if s.start_local.date() == dt.date(2026, 7, 17))
    # "…Furnace Woods, Normal" + next line "Bird, 8pm" → "Normal Bird".
    assert fri.headliner_raw == "Rainbow City Park"
    assert fri.support_raw == ["blossomfoam", "Furnace Woods", "Normal Bird"]
    assert fri.start_local == dt.datetime(2026, 7, 17, 20, 0)


def test_desc_line_ocr_ordered_before_its_date_pairs_correctly() -> None:
    # The 7/8 description precedes its date line in OCR order; center-y
    # pairing must still land it on 7/8 (with its own continuation), not 7/7.
    shows = _parse(dt.date(2026, 7, 1))
    wed = next(s for s in shows if s.start_local.date() == dt.date(2026, 7, 8))
    assert wed.headliner_raw.startswith("Faction Punk Flamingo Release Party")
    assert wed.headliner_raw.endswith('DJ "Balzac" Johnny')
    assert wed.start_local.time() == dt.time(19, 0)
    tue = next(s for s in shows if s.start_local.date() == dt.date(2026, 7, 7))
    assert tue.headliner_raw == "Jazz on Tuesdays: Eli's New Band"


def test_time_range_takes_start_with_borrowed_meridiem() -> None:
    shows = _parse(dt.date(2026, 7, 1))
    by_day = {s.start_local.date().day: s for s in shows}
    assert by_day[1].start_local.time() == dt.time(19, 0)  # "7-11pm"
    assert by_day[5].start_local.time() == dt.time(18, 0)  # "6-11pm"
    assert by_day[31].start_local.time() == dt.time(19, 0)  # "7pm - 12am"


def test_unbalanced_parenthetical_trimmed_balanced_kept() -> None:
    shows = _parse(dt.date(2026, 7, 24))
    sun = next(s for s in shows if s.start_local.date().day == 26)
    assert sun.headliner_raw == "Disciples of Markos"  # "(Greek," typo trimmed
    fri = next(s for s in shows if s.start_local.date().day == 24)
    assert fri.support_raw == ["Dum1 (record release)", "Spectre", "DJ Shama Lama"]


def test_window_and_past_rows_excluded() -> None:
    shows = _parse(dt.date(2026, 7, 17))
    assert min(s.start_local.date() for s in shows) >= dt.date(2026, 7, 17)
    assert len(shows) == 11


@pytest.mark.skipif(sys.platform == "darwin", reason="darwin has Vision")
def test_ocr_unavailable_off_macos() -> None:
    with pytest.raises(RuntimeError, match="Apple Vision"):
        little_hill_lounge.ocr_image(b"not-an-image")
