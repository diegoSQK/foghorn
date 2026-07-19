"""Tests for the SF Symphony scraper's pure parse layer, driven by a trimmed
capture of the real ``prod_sfs_calendar`` Algolia hits (2026-07-19) plus
synthesized malformed rows."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from foghorn.scrapers.sf_symphony import parse_hits

_FIXTURE = Path(__file__).parent.parent / "fixtures" / "sf_symphony_algolia_hits.json"
_TODAY = dt.date(2026, 7, 19)


def _hits() -> list[dict]:
    return json.loads(_FIXTURE.read_text())


def test_parse_hits_full_pass() -> None:
    shows = parse_hits(_hits(), _TODAY)
    # Of the 7 fixture hits: excluded, malformed-date, empty-title, and
    # beyond-window rows all drop; the 2031 gala proves window (not parse)
    # dropped it.
    assert [(s.headliner_raw, s.start_local.isoformat()) for s in shows] == [
        ("Matilda", "2026-07-25T19:30:00"),
        (
            "Free Community Performance: Talking Books & Braille Center, Main Branch",
            "2026-07-28T13:00:00",
        ),
        ("St. Vincent with the San Francisco Symphony", "2026-07-30T19:30:00"),
    ]


def test_em_markup_stripped_and_entities_unescaped() -> None:
    shows = parse_hits(_hits(), _TODAY)
    assert shows[0].headliner_raw == "Matilda"  # was "<em>Matilda</em>"
    assert "&amp;" not in shows[1].headliner_raw
    assert "&" in shows[1].headliner_raw


def test_exclude_from_calendar_respected() -> None:
    names = [s.headliner_raw for s in parse_hits(_hits(), _TODAY)]
    assert "All San Francisco Concert" not in names


def test_kentico_url_becomes_ticket_and_source_url() -> None:
    matilda = parse_hits(_hits(), _TODAY)[0]
    assert matilda.ticket_url is not None
    assert matilda.ticket_url.startswith("https://www.sfsymphony.org/")
    assert matilda.source_url == matilda.ticket_url


def test_window_is_inclusive_and_bounded() -> None:
    # A 6-day window ends 07-25: Matilda (07-25) in, the 07-28 + 07-30 rows out.
    shows = parse_hits(_hits(), _TODAY, window_days=6)
    assert [s.headliner_raw for s in shows] == ["Matilda"]
    # The 2031 gala stays out even at the real window.
    assert all(
        s.headliner_raw != "Beyond The Window Gala"
        for s in parse_hits(_hits(), _TODAY)
    )
