"""Tests for the SFJAZZ (ace-api) scraper.

``parse_events`` is pure and driven from a trimmed snapshot of the live
``/ace-api/events/`` response (``fixtures/sfjazz_2026_08.json``), picked to hit
every branch: both SFJAZZ Center rooms, the feed's lowercase ``"Joe Henderson
lab"`` spelling, off-site bookings at Paramount / Davies / an unseeded room, a
streamed "SFJAZZ At Home" date, classes and workshops, an SFJAM community jam
tagged only ``Education``, a family matinee tagged ``Education`` alongside
``Family Events``, an ``eventDate`` with no tz offset, a sold-out show, an event
with no artists, an unmapped location, and a date past the window.

The fetch side is not exercised against the network: ``fetch_events`` is checked
for its failure translation only, since the live call is a single plain GET.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import urllib.error
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from foghorn.models import ScrapedShow
from foghorn.scrapers import sfjazz

FIXTURE = Path(__file__).parent.parent / "fixtures" / "sfjazz_2026_08.json"
TODAY = dt.date(2026, 8, 11)


def _events() -> list[dict[str, Any]]:
    data: list[dict[str, Any]] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return data


@pytest.fixture
def parsed() -> list[ScrapedShow]:
    return sfjazz.parse_events(_events(), today=TODAY)


def test_returns_expected_shows_sorted(parsed: list[ScrapedShow]) -> None:
    got = [(s.start_local.isoformat(), s.venue_slug, s.headliner_raw) for s in parsed]
    assert got == [
        ("2026-08-13T19:30:00", "sfjazz", "Take 6"),
        ("2026-08-14T19:30:00", "sfjazz", "Take 6"),
        ("2026-08-29T20:00:00", "paramount_theatre_oakland", "Brad Mehldau: Ride Into The Sun"),
        ("2026-09-10T19:00:00", "sfjazz", "Paul Cornish Trio"),
        ("2026-09-10T20:30:00", "sfjazz", "Paul Cornish Trio"),
        (
            "2026-09-14T19:00:00",
            "sfjazz",
            "SFJAM: Free Community Jam Session: 100 Years of Coltrane",
        ),
        ("2026-09-16T13:15:00", "sfjazz", "Brian Simpson featuring Grace Kelly"),
        ("2026-09-18T19:00:00", "sfjazz", "Camille Kerani"),
        ("2026-09-19T10:00:00", "sfjazz", "WeBop at SFJAZZ: Stompers"),
        ("2026-10-19T20:00:00", "davies_symphony_hall", "Julian Lage Quartet"),
        ("2026-10-30T20:00:00", "grace_cathedral", "Dr. Jekyll & Mr. Hyde"),
    ]


def test_both_center_rooms_fold_into_one_venue(parsed: list[ScrapedShow]) -> None:
    # Miner Auditorium and the Joe Henderson Lab are rooms in the same
    # building, so they share a row (the SoundBox-under-Davies precedent) —
    # unlike The Mellow's two rooms, which sit in different neighborhoods.
    center = {s.headliner_raw for s in parsed if s.venue_slug == "sfjazz"}
    assert "Take 6" in center  # Miner Auditorium
    assert "Paul Cornish Trio" in center  # Joe Henderson Lab


def test_offsite_bookings_route_to_the_host_venue(parsed: list[ScrapedShow]) -> None:
    # SFJAZZ is a presenter, not just a venue. Without routing, Brad Mehldau's
    # Paramount date would file under Hayes Valley instead of Uptown Oakland.
    by_venue = {s.venue_slug for s in parsed}
    assert {"paramount_theatre_oakland", "davies_symphony_hall"} <= by_venue
    mehldau = next(s for s in parsed if "Mehldau" in s.headliner_raw)
    assert mehldau.venue_slug == "paramount_theatre_oakland"


def test_lowercase_lab_spelling_is_not_treated_as_a_new_room() -> None:
    # The feed ships both "Joe Henderson Lab" and "Joe Henderson lab"; a
    # case-sensitive map would send 7 events a year to the unmapped warning.
    assert sfjazz.venue_slug_for("Joe Henderson lab") == "sfjazz"
    assert sfjazz.venue_slug_for("JOE HENDERSON LAB") == "sfjazz"


def test_streaming_events_are_dropped(parsed: list[ScrapedShow]) -> None:
    # "SFJAZZ At Home" — real programming, but not a local show to attend.
    assert not any("Mary Stallings" in s.headliner_raw for s in parsed)
    assert sfjazz.venue_slug_for("SFJAZZ At Home") is None


def test_classes_and_workshops_are_dropped(parsed: list[ScrapedShow]) -> None:
    titles = {s.headliner_raw for s in parsed}
    assert "Studio Production Intensive" not in titles
    assert not any("ABLETON" in t.upper() for t in titles)
    assert not any("Discover Jazz" in t for t in titles)


def test_sfjam_community_jam_is_kept_and_tagged() -> None:
    """The bare-Education tag is the class programme *except* for SFJAM.

    Every bare-``Education`` event in a year of this feed is an SFJAM free
    community jam. Dropping the tag wholesale would have lost nine dates of the
    exact participatory event foghorn's jam type exists for.
    """
    shows = sfjazz.parse_events(_events(), today=TODAY)
    jam = next(s for s in shows if s.headliner_raw.startswith("SFJAM"))
    assert jam.event_type == "jam"
    assert jam.venue_slug == "sfjazz"
    # A normal concert is not a jam.
    assert next(s for s in shows if s.headliner_raw == "Take 6").event_type is None


def test_family_matinee_survives_its_education_tag(parsed: list[ScrapedShow]) -> None:
    # Tagged ["Family Events", "Education"] — a real show, not a class.
    assert any("WeBop" in s.headliner_raw for s in parsed)


def test_untyped_events_are_kept(parsed: list[ScrapedShow]) -> None:
    # Some concerts carry no eventTypes at all; erring toward inclusion keeps
    # them rather than treating an empty list as "not a show".
    assert any("Brian Simpson" in s.headliner_raw for s in parsed)


def test_artists_become_the_support_bill(parsed: list[ScrapedShow]) -> None:
    # The feed lists every named player, which is what lets the watchlist
    # follow a sideman across the bands they sit in. The act's own name is not
    # repeated as its own support row.
    take6 = next(s for s in parsed if s.headliner_raw == "Take 6")
    assert "Alvin Chea" in take6.support_raw
    assert "Take 6" not in take6.support_raw


def test_event_date_without_tz_offset_is_read_as_local(parsed: list[ScrapedShow]) -> None:
    # 26 of 282 events over a year omit the -07:00 offset; both forms are
    # already venue-local, so the parse must not shift them.
    simpson = next(s for s in parsed if "Brian Simpson" in s.headliner_raw)
    assert simpson.start_local == dt.datetime(2026, 9, 16, 13, 15)
    assert simpson.start_local.tzinfo is None


def test_sold_out_show_keeps_provenance_but_drops_the_ticket_link(
    parsed: list[ScrapedShow],
) -> None:
    sold_out = [s for s in parsed if s.ticket_url is None]
    assert sold_out, "fixture should contain a sold-out date"
    assert all(s.source_url.startswith("https://www.sfjazz.org/") for s in sold_out)


def test_urls_are_absolutised(parsed: list[ScrapedShow]) -> None:
    assert all(s.source_url.startswith("https://www.sfjazz.org/") for s in parsed)
    assert all(
        s.ticket_url.startswith("https://www.sfjazz.org/")
        for s in parsed
        if s.ticket_url is not None
    )
    # The API publishes no price anywhere.
    assert all(s.price_text is None for s in parsed)


def test_forward_window_only(parsed: list[ScrapedShow]) -> None:
    horizon = TODAY + dt.timedelta(days=sfjazz.SCRAPE_WINDOW_DAYS)
    assert all(TODAY <= s.start_local.date() <= horizon for s in parsed)
    assert not any("Chucho" in s.headliner_raw for s in parsed)


def test_unmapped_location_is_dropped_with_a_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # SFJAZZ books the occasional one-off room. Losing that show beats raising
    # and losing the other ~180 in the window, but it must not be silent.
    with caplog.at_level(logging.WARNING, logger="foghorn.scrapers.sfjazz"):
        shows = sfjazz.parse_events(_events(), today=TODAY)
    assert not any("Test Act" in s.headliner_raw for s in shows)
    record = next(r for r in caplog.records if r.message == "sfjazz.unmapped_locations")
    assert record.locations == ["Fox Theater, Redwood City"]  # type: ignore[attr-defined]


def test_known_offsite_locations_do_not_warn(caplog: pytest.LogCaptureFixture) -> None:
    # Locations we've decided about must not cry wolf every night.
    events = [e for e in _events() if e.get("location") != "Fox Theater, Redwood City"]
    with caplog.at_level(logging.WARNING, logger="foghorn.scrapers.sfjazz"):
        sfjazz.parse_events(events, today=TODAY)
    assert not [r for r in caplog.records if r.message == "sfjazz.unmapped_locations"]


# --------------------------------------------------------------------------
# fetch-side failure translation
# --------------------------------------------------------------------------


def _http_error(code: int, headers: dict[str, str]) -> urllib.error.HTTPError:
    import email.message

    msg = email.message.Message()
    for key, value in headers.items():
        msg[key] = value
    return urllib.error.HTTPError("https://x", code, "err", msg, None)  # type: ignore[arg-type]


def test_a_returning_cloudflare_challenge_fails_loudly() -> None:
    """The whole scraper rests on this client not being fingerprinted.

    If Cloudflare reclassifies it, the venue must show as *errored* on the
    scrape-health surface — not quietly report an empty calendar, which reads
    identically to "SFJAZZ has no shows".
    """
    err = _http_error(403, {"cf-mitigated": "challenge"})
    with patch("urllib.request.urlopen", side_effect=err):
        with pytest.raises(sfjazz.SFJazzSourceError, match="Cloudflare challenge"):
            sfjazz.fetch_events(TODAY)


def test_request_headers_are_exactly_the_measured_set() -> None:
    """Guards an empirically-derived, counter-intuitive header set.

    Against the live endpoint, reproducibly: UA + Accept -> 200; adding a
    Referer -> 403 challenge; omitting Accept -> 403 challenge. A well-meaning
    "make it look more like a browser" edit here silently breaks the scraper,
    so the exact headers are pinned.
    """
    captured: dict[str, str] = {}

    class _Response:
        def read(self) -> bytes:
            return b"[]"

        def __enter__(self) -> _Response:
            return self

        def __exit__(self, *exc: object) -> None:
            return None

    def _fake_urlopen(request: Any, timeout: float | None = None) -> _Response:
        captured.update(request.headers)
        return _Response()

    with patch("urllib.request.urlopen", _fake_urlopen):
        sfjazz.fetch_events(TODAY)

    # urllib title-cases header keys.
    assert set(captured) == {"User-agent", "Accept"}
    assert captured["Accept"] == "application/json"
    assert "Referer" not in captured


def test_other_http_errors_are_wrapped() -> None:
    with patch("urllib.request.urlopen", side_effect=_http_error(500, {})):
        with pytest.raises(sfjazz.SFJazzSourceError, match="HTTP 500"):
            sfjazz.fetch_events(TODAY)


def test_non_list_payload_is_rejected() -> None:
    class _Response:
        def read(self) -> bytes:
            return b'{"error": "nope"}'

        def __enter__(self) -> _Response:
            return self

        def __exit__(self, *exc: object) -> None:
            return None

    with patch("urllib.request.urlopen", return_value=_Response()):
        with pytest.raises(sfjazz.SFJazzSourceError, match="expected a list"):
            sfjazz.fetch_events(TODAY)
