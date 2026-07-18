"""Tests for the Poor House Bistro (OCR month-grid) scraper, driven from
the real 2x Vision output of the July 2026 calendar: computed-grid dates
vs. read anchors, CLOSED cells, two-slot Sunday cells, the Wednesday
residency typed as a jam, and the anchor sanity check refusing a shifted
grid."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from foghorn.ocr import OcrLine
from foghorn.scrapers import poor_house_bistro

FIXTURE = (
    Path(__file__).parent.parent / "fixtures" / "poor_house_bistro_2026_07_ocr.json"
)


def _lines() -> list[OcrLine]:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return [OcrLine(r["text"], r["x"], r["y"], r["w"], r["h"]) for r in raw]


def test_full_month_parse() -> None:
    shows = poor_house_bistro.parse_flyer(_lines(), 2026, 7, dt.date(2026, 7, 1))
    assert len(shows) >= 20  # 30 flyer slots minus CLOSED/garbled cells
    days = {s.start_local.date().day for s in shows}
    assert {6, 7, 13, 14, 20, 21, 27, 28}.isdisjoint(days)  # CLOSED Mon/Tue


def test_wednesday_residency_is_jam() -> None:
    shows = poor_house_bistro.parse_flyer(_lines(), 2026, 7, dt.date(2026, 7, 1))
    wednesdays = [s for s in shows if s.start_local.date().weekday() == 2]
    assert wednesdays and all(s.event_type == "jam" for s in wednesdays)
    assert all("JAZZ JAM" in s.headliner_raw for s in wednesdays)


def test_sunday_cells_split_into_two_slots() -> None:
    shows = poor_house_bistro.parse_flyer(_lines(), 2026, 7, dt.date(2026, 7, 1))
    july5 = [s for s in shows if s.start_local.date() == dt.date(2026, 7, 5)]
    assert [(s.start_local.time(), s.headliner_raw) for s in july5] == [
        (dt.time(12, 0), "ROMA JAZZ PROJECT"),
        (dt.time(16, 0), "BLUES ROCKERS"),
    ]


def test_anchor_sanity_check_refuses_shifted_grid() -> None:
    # Claiming the flyer is June (different first weekday) makes the
    # computed grid disagree with every read anchor — parse must refuse.
    assert poor_house_bistro.parse_flyer(_lines(), 2026, 6, dt.date(2026, 6, 1)) == []
