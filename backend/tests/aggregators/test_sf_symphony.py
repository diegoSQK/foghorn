"""Tests for the SF Symphony group feed's pure parse layer, driven by a
trimmed capture of the real ``prod_sfs_calendar`` Algolia hits (2026-07-19)
plus synthesized malformed rows."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from foghorn.aggregators.sf_symphony import (
    GROUP_NAME,
    OFFSITE_VENUE,
    parse_hits,
)

_FIXTURE = Path(__file__).parent.parent / "fixtures" / "sf_symphony_algolia_hits.json"
_TODAY = dt.date(2026, 7, 19)


def _hits() -> list[dict]:
    return json.loads(_FIXTURE.read_text())


def test_parse_hits_full_pass() -> None:
    events = parse_hits(_hits(), _TODAY)
    # Of the 7 fixture hits: excluded, malformed-date, empty-title, and
    # beyond-window rows all drop; the 2031 gala proves window (not parse)
    # dropped it. The venue-less KenticoItem lands in the offsite bucket.
    assert [
        (e.headliner_raw, e.start_local.isoformat(), e.venue_name_raw)
        for e in events
    ] == [
        ("Matilda", "2026-07-25T19:30:00", "Davies Symphony Hall"),
        (
            "Free Community Performance: Talking Books & Braille Center, Main Branch",
            "2026-07-28T13:00:00",
            OFFSITE_VENUE,
        ),
        (
            "St. Vincent with the San Francisco Symphony",
            "2026-07-30T19:30:00",
            "Davies Symphony Hall",
        ),
    ]


def test_group_rides_every_bill_as_support() -> None:
    assert all(e.support_raw == [GROUP_NAME] for e in parse_hits(_hits(), _TODAY))


def test_venue_normalization_and_placeholders() -> None:
    def hit(venue: object) -> dict:
        return {
            "title": "X",
            "performanceDate": "2026-08-01T19:30:00",
            "venue": venue,
            "kenticoUrl": "/x",
        }

    events = parse_hits(
        [
            hit("SoundBox Space"),  # room inside Davies -> folded in
            hit("Youth Orchestra"),  # org-in-venue-field quirk -> Davies
            hit("Display Name"),  # unfilled placeholder -> offsite bucket
            hit("Gunn Theater at the Legion of Honor"),  # passthrough
        ],
        _TODAY,
    )
    assert [e.venue_name_raw for e in events] == [
        "Davies Symphony Hall",
        "Davies Symphony Hall",
        OFFSITE_VENUE,
        "Gunn Theater at the Legion of Honor",
    ]


def test_em_markup_stripped_and_entities_unescaped() -> None:
    events = parse_hits(_hits(), _TODAY)
    assert events[0].headliner_raw == "Matilda"  # was "<em>Matilda</em>"
    assert "&amp;" not in events[1].headliner_raw
    assert "&" in events[1].headliner_raw


def test_exclude_from_calendar_respected() -> None:
    names = [e.headliner_raw for e in parse_hits(_hits(), _TODAY)]
    assert "All San Francisco Concert" not in names


def test_kentico_url_becomes_ticket_and_source_url() -> None:
    matilda = parse_hits(_hits(), _TODAY)[0]
    assert matilda.ticket_url is not None
    assert matilda.ticket_url.startswith("https://www.sfsymphony.org/")
    assert matilda.source_url == matilda.ticket_url


def test_window_is_inclusive_and_bounded() -> None:
    # A 6-day window ends 07-25: Matilda (07-25) in, the 07-28 + 07-30 rows out.
    events = parse_hits(_hits(), _TODAY, window_days=6)
    assert [e.headliner_raw for e in events] == ["Matilda"]
    # The 2031 gala stays out even at the real window.
    assert all(
        e.headliner_raw != "Beyond The Window Gala"
        for e in parse_hits(_hits(), _TODAY)
    )
