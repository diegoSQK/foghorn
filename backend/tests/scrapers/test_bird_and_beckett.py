"""Tests for the Bird & Beckett scraper.

Fixture-driven and deterministic: ``parse_ics`` takes an injected ``today`` so
the recurrence window doesn't depend on the clock, and an injected ``details``
index so it never touches the network. The ``.ics`` fixture
(``fixtures/bird_and_beckett_sample.ics``) is a curated subset exercising the
edge cases — TZID vs UTC times, a non-music event, an all-day entry, a weekly
recurring residency, an accented name, and an out-of-window event.

The Tribe fixtures (``bird_and_beckett_tribe_page{1,2}.json``) are real
captured responses trimmed to the fields the scraper reads, with dates shifted
onto the ``.ics`` fixture's June 2026 window so the ``(date, time)`` join is
actually exercisable. They deliberately carry the awkward cases: an empty
``cost``, HTML-entity-escaped titles, an event with no permalink, and two
events colliding on one slot.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from pathlib import Path

import httpx
import pytest

from foghorn.models import ScrapedShow
from foghorn.scrapers import bird_and_beckett

FIXTURES = Path(__file__).parent.parent / "fixtures"
FIXTURE = FIXTURES / "bird_and_beckett_sample.ics"
TRIBE_PAGES = [
    json.loads((FIXTURES / f"bird_and_beckett_tribe_page{n}.json").read_text())
    for n in (1, 2)
]
TODAY = dt.date(2026, 6, 1)


@pytest.fixture
def parsed() -> list[ScrapedShow]:
    return bird_and_beckett.parse_ics(FIXTURE.read_text(encoding="utf-8"), today=TODAY)


@pytest.fixture
def index() -> dict[tuple[dt.date, dt.time], bird_and_beckett.EventDetails]:
    events = [event for page in TRIBE_PAGES for event in page["events"]]
    return bird_and_beckett.build_detail_index(events)


@pytest.fixture
def joined(
    index: dict[tuple[dt.date, dt.time], bird_and_beckett.EventDetails],
) -> list[ScrapedShow]:
    return bird_and_beckett.parse_ics(
        FIXTURE.read_text(encoding="utf-8"), today=TODAY, details=index
    )


def _by_name(shows: list[ScrapedShow], fragment: str) -> ScrapedShow:
    return next(s for s in shows if fragment in s.headliner_raw)


def test_returns_expected_shows_sorted(parsed: list[ScrapedShow]) -> None:
    got = [(s.start_local.isoformat(), s.headliner_raw) for s in parsed]
    assert got == [
        ("2026-06-05T19:30:00", "David Parker Sextet"),  # one-time TZID
        ("2026-06-06T20:00:00", "Klaxon Mutant All-Stars"),  # UTC -> PT
        ("2026-06-07T17:00:00", "Sunday Happy Hour - The Vince Lateano Trio"),
        ("2026-06-10T20:00:00", "Café Tacvba"),  # accent preserved in display
        ("2026-06-14T17:00:00", "Sunday Happy Hour - The Vince Lateano Trio"),
        ("2026-06-21T17:00:00", "Sunday Happy Hour - The Vince Lateano Trio"),
        ("2026-06-28T17:00:00", "Sunday Happy Hour - The Vince Lateano Trio"),
    ]


def test_excludes_non_music(parsed: list[ScrapedShow]) -> None:
    assert not any("Poets!" in s.headliner_raw for s in parsed)


def test_excludes_all_day(parsed: list[ScrapedShow]) -> None:
    assert not any("Glen Park Festival" in s.headliner_raw for s in parsed)


def test_excludes_out_of_window(parsed: list[ScrapedShow]) -> None:
    assert not any(s.headliner_raw == "Future Act" for s in parsed)


def test_recurring_series_expanded(parsed: list[ScrapedShow]) -> None:
    lateano = [s for s in parsed if "Lateano" in s.headliner_raw]
    assert len(lateano) == 4  # weekly COUNT=4


def test_utc_event_converted_to_local(parsed: list[ScrapedShow]) -> None:
    klaxon = next(s for s in parsed if s.headliner_raw == "Klaxon Mutant All-Stars")
    # DTSTART:20260607T030000Z == 8pm PDT on June 6; start_local is naive PT.
    assert klaxon.start_local == dt.datetime(2026, 6, 6, 20, 0)


def test_window_size_is_respected() -> None:
    # A 5-day window from today should only catch the June 5 one-time event.
    shows = bird_and_beckett.parse_ics(
        FIXTURE.read_text(encoding="utf-8"), today=TODAY, window_days=5
    )
    assert [s.headliner_raw for s in shows] == ["David Parker Sextet"]


def test_optional_fields_are_none(parsed: list[ScrapedShow]) -> None:
    """With no Tribe index — the pre-#122 behavior, and the Tribe-outage
    path — every show keeps the generic fallback link and a null price."""
    show = parsed[0]
    assert show.support_raw == []
    assert show.doors_local is None
    assert show.ticket_url is None
    assert show.price_text is None
    assert show.source_url == bird_and_beckett.SOURCE_URL
    assert show.venue_slug == "bird_and_beckett"


# --------------------------------------------------------------- the join


def test_join_hit_sets_per_event_url_and_price(joined: list[ScrapedShow]) -> None:
    show = _by_name(joined, "David Parker Sextet")
    assert show.source_url == "https://birdbeckett.com/event/david-parker_2026-06-05/"
    assert show.price_text == "$20 (Students $10)"


def test_join_hit_with_empty_cost_leaves_price_none(joined: list[ScrapedShow]) -> None:
    """An empty Tribe ``cost`` is absence, not a price of "" — the link still
    upgrades."""
    show = _by_name(joined, "Klaxon Mutant All-Stars")
    assert show.source_url == "https://birdbeckett.com/event/klaxon-mutant_2026-06-06/"
    assert show.price_text is None


def test_join_matches_date_first_slug_shape(joined: list[ScrapedShow]) -> None:
    """Tribe slugs are not derivable from the title — this one puts the date
    first. The join is on (date, time), so the shape doesn't matter."""
    show = _by_name(joined, "Sunday Happy Hour")
    assert show.source_url == (
        "https://birdbeckett.com/event/2026-06-07_sunday-happy-hour/"
    )
    assert show.price_text == "Happy Hour Sliding Scale"


def test_join_miss_falls_back(joined: list[ScrapedShow]) -> None:
    """The June 21 recurrence has no Tribe counterpart."""
    show = next(
        s for s in joined if s.start_local == dt.datetime(2026, 6, 21, 17, 0)
    )
    assert show.source_url == bird_and_beckett.SOURCE_URL
    assert show.price_text is None


def test_empty_index_returns_full_show_set(
    parsed: list[ScrapedShow], joined: list[ScrapedShow]
) -> None:
    """A Tribe outage must never reduce the show count — the .ics is
    authoritative for existence, Tribe only decorates."""
    empty = bird_and_beckett.parse_ics(
        FIXTURE.read_text(encoding="utf-8"), today=TODAY, details={}
    )
    assert len(empty) == len(parsed) == len(joined)
    assert all(s.source_url == bird_and_beckett.SOURCE_URL for s in empty)


def test_billing_strings_are_untouched_by_the_join(
    parsed: list[ScrapedShow], joined: list[ScrapedShow]
) -> None:
    """The whole reason we join instead of switching: the .ics billing names
    the sidemen, and joining must not overwrite it with Tribe's act name."""
    assert [s.headliner_raw for s in joined] == [s.headliner_raw for s in parsed]
    assert [s.start_local for s in joined] == [s.start_local for s in parsed]


# ------------------------------------------------------------- index build


def test_colliding_slot_is_dropped_not_guessed(
    index: dict[tuple[dt.date, dt.time], bird_and_beckett.EventDetails],
    joined: list[ScrapedShow],
) -> None:
    """Two Tribe events claim 2026-06-10 20:00. Picking one arbitrarily would
    link half the calendar to the wrong page, so the slot falls back."""
    assert (dt.date(2026, 6, 10), dt.time(20, 0)) not in index
    show = _by_name(joined, "Tacvba")
    assert show.source_url == bird_and_beckett.SOURCE_URL


def test_collision_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    events = [event for page in TRIBE_PAGES for event in page["events"]]
    with caplog.at_level(logging.WARNING, logger=bird_and_beckett.__name__):
        bird_and_beckett.build_detail_index(events)
    assert "share 2026-06-10 20:00" in caplog.text


def test_event_without_permalink_is_skipped(
    index: dict[tuple[dt.date, dt.time], bird_and_beckett.EventDetails],
) -> None:
    """An empty ``url`` gives us nothing to link to — better the fallback than
    a link to nowhere."""
    assert (dt.date(2026, 6, 14), dt.time(17, 0)) not in index


def test_unparseable_start_date_is_skipped(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger=bird_and_beckett.__name__):
        index = bird_and_beckett.build_detail_index(
            [{"url": "https://x/", "start_date": "not-a-date"}, {"url": "https://y/"}]
        )
    assert index == {}
    assert "unparseable" in caplog.text


# -------------------------------------------------------------- fetch/page


def test_fetch_event_details_walks_pagination() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        page = dict(httpx.QueryParams(request.url.query)).get("page", "1")
        return httpx.Response(200, json=TRIBE_PAGES[int(page) - 1])

    client = httpx.Client(transport=httpx.MockTransport(handler))
    events = bird_and_beckett.fetch_event_details(TODAY, client=client)
    assert [event["id"] for event in events] == [38988, 38991, 38994, 39001, 39002, 39007]


def test_fetch_event_details_stops_on_404_past_last_page() -> None:
    """Tribe 404s past the final page rather than returning an empty list."""
    def handler(request: httpx.Request) -> httpx.Response:
        page = dict(httpx.QueryParams(request.url.query)).get("page", "1")
        if page == "2":
            return httpx.Response(404, json={"message": "page not found"})
        return httpx.Response(200, json=TRIBE_PAGES[0])

    client = httpx.Client(transport=httpx.MockTransport(handler))
    events = bird_and_beckett.fetch_event_details(TODAY, client=client)
    assert [event["id"] for event in events] == [38988, 38991, 38994]


def test_scrape_survives_a_tribe_outage(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The acceptance criterion that matters most: a Tribe failure degrades to
    an empty index rather than propagating. Failing closed here would silently
    shrink a load-bearing venue's calendar.

    ``scrape()`` reads the real clock, so rather than freezing it (which
    entangles the test with recurrence expansion), this asserts the contract
    ``scrape()`` actually owns — the ``.ics`` is still parsed, with ``{}``
    passed through. ``test_empty_index_returns_full_show_set`` covers the
    other half: an empty index yields the full show set with /events/ links.
    """
    captured: dict[str, object] = {}

    def _fake_parse(ics_text: str, today: dt.date, **kwargs: object) -> list[ScrapedShow]:
        captured["details"] = kwargs.get("details")
        captured["ics"] = ics_text
        return []

    def _boom(*args: object, **kwargs: object) -> list[dict[str, object]]:
        raise httpx.ConnectTimeout("tribe is down")

    monkeypatch.setattr(bird_and_beckett, "fetch_ics", lambda *a, **k: "ICS-TEXT")
    monkeypatch.setattr(bird_and_beckett, "fetch_event_details", _boom)
    monkeypatch.setattr(bird_and_beckett, "parse_ics", _fake_parse)

    with caplog.at_level(logging.WARNING, logger=bird_and_beckett.__name__):
        bird_and_beckett.scrape()

    assert captured["details"] == {}
    assert captured["ics"] == "ICS-TEXT"  # the .ics fetch still happened
    assert "Tribe metadata fetch failed" in caplog.text


def test_fetch_event_details_requests_the_window() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(dict(httpx.QueryParams(request.url.query)))
        return httpx.Response(200, json={"events": TRIBE_PAGES[0]["events"]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    bird_and_beckett.fetch_event_details(TODAY, window_days=90, client=client)
    assert seen["start_date"] == "2026-06-01"
    assert seen["end_date"] == "2026-08-30"
