"""Tests for The Mellow SF (EventON) scraper.

``parse_occurrences`` is pure and driven from two saved payloads: the
``eventon_get_events`` occurrence list
(``fixtures/the_mellow_2026_08_occurrences.json``) and the WordPress REST event
index that carries the room taxonomy
(``fixtures/the_mellow_2026_08_events.json``). The Lakehouse Jazz occurrences
are verbatim live capture — two sets a night (7:00 and 8:30) across four
Fri/Sat dates, which is the recurring-series case. The Haight-room shows, the
retail pop-up, the untagged wellness entry, the closed-Mission row, and the
far-future occurrence are hand-added in the source's exact shape, because the
live calendar programs only the boathouse today.

The fetch side is exercised with an ``httpx.MockTransport`` so no network is
touched: the nonce/shortcode harvest off ``/calendar/``, the per-month walk of
the AJAX endpoint, and the refusal path when the endpoint rejects a request.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from foghorn.models import ScrapedShow
from foghorn.scrapers import the_mellow

FIXTURES = Path(__file__).parent.parent / "fixtures"
OCCURRENCES = FIXTURES / "the_mellow_2026_08_occurrences.json"
EVENTS = FIXTURES / "the_mellow_2026_08_events.json"
TODAY = dt.date(2026, 8, 11)

LAKEHOUSE = "Lakehouse Jazz"
DUMAINE = "Mellow Sessions: Rebecca DuMaine Trio"


def _occurrences() -> list[dict[str, Any]]:
    data: list[dict[str, Any]] = json.loads(OCCURRENCES.read_text(encoding="utf-8"))
    return data


def _event_index() -> dict[int, dict[str, Any]]:
    events: list[dict[str, Any]] = json.loads(EVENTS.read_text(encoding="utf-8"))
    return {int(event["id"]): event for event in events}


@pytest.fixture
def parsed() -> list[ScrapedShow]:
    return the_mellow.parse_occurrences(_occurrences(), _event_index(), today=TODAY)


def test_returns_expected_shows_sorted(parsed: list[ScrapedShow]) -> None:
    got = [(s.start_local.isoformat(), s.venue_slug, s.headliner_raw) for s in parsed]
    assert got == [
        ("2026-08-14T19:00:00", "blue_heron_boathouse", LAKEHOUSE),
        ("2026-08-14T20:30:00", "blue_heron_boathouse", LAKEHOUSE),
        ("2026-08-15T19:00:00", "blue_heron_boathouse", LAKEHOUSE),
        ("2026-08-15T20:30:00", "blue_heron_boathouse", LAKEHOUSE),
        ("2026-08-20T19:30:00", "the_mellow_haight", DUMAINE),
        ("2026-08-21T19:00:00", "blue_heron_boathouse", LAKEHOUSE),
        ("2026-08-21T20:30:00", "blue_heron_boathouse", LAKEHOUSE),
        ("2026-08-22T19:00:00", "blue_heron_boathouse", LAKEHOUSE),
        ("2026-08-22T20:30:00", "blue_heron_boathouse", LAKEHOUSE),
        ("2026-08-27T19:30:00", "the_mellow_haight", "Mellow Sessions: Open Bandstand"),
    ]


def test_rooms_do_not_bleed_into_each_other(parsed: list[ScrapedShow]) -> None:
    # The whole reason these are two venue rows: a boathouse show filed under
    # the Haight shop would land in the wrong neighborhood filter.
    boathouse = {s.headliner_raw for s in parsed if s.venue_slug == "blue_heron_boathouse"}
    haight = {s.headliner_raw for s in parsed if s.venue_slug == "the_mellow_haight"}
    assert boathouse == {LAKEHOUSE}
    assert haight == {DUMAINE, "Mellow Sessions: Open Bandstand"}
    assert boathouse.isdisjoint(haight)


def test_weekly_series_expands_to_one_row_per_date(parsed: list[ScrapedShow]) -> None:
    # Lakehouse Jazz is a weekly Fri/Sat series with a 7:00 and an 8:30 set.
    # The source models each set as its own repeating event; both must expand
    # per date rather than collapsing to one row for the series.
    lakehouse = [s for s in parsed if s.headliner_raw == LAKEHOUSE]
    dates = sorted({s.start_local.date().isoformat() for s in lakehouse})
    assert dates == ["2026-08-14", "2026-08-15", "2026-08-21", "2026-08-22"]
    assert len(lakehouse) == 8  # 4 dates x 2 sets
    assert sorted({s.start_local.time().isoformat() for s in lakehouse}) == [
        "19:00:00",
        "20:30:00",
    ]


def test_two_sets_on_one_night_stay_distinct(parsed: list[ScrapedShow]) -> None:
    # The natural key is (venue, date, time, headliner) — same title, same
    # night, different start, so the two sets must not be deduped together.
    aug14 = [
        s
        for s in parsed
        if s.headliner_raw == LAKEHOUSE and s.start_local.date() == dt.date(2026, 8, 14)
    ]
    assert [s.start_local.isoformat() for s in aug14] == [
        "2026-08-14T19:00:00",
        "2026-08-14T20:30:00",
    ]
    assert [s.end_local.isoformat() if s.end_local else None for s in aug14] == [
        "2026-08-14T20:00:00",
        "2026-08-14T21:30:00",
    ]


def test_closed_mission_room_is_dropped(parsed: list[ScrapedShow]) -> None:
    assert all("Mission Nights" not in s.headliner_raw for s in parsed)


def test_non_music_programming_is_dropped(parsed: list[ScrapedShow]) -> None:
    titles = {s.headliner_raw for s in parsed}
    # event_type-pop-up on the taxonomy.
    assert "Pop Up = Jenn Ban" not in titles
    # No event_type term at all — caught by the title backstop.
    assert "Mindful Flow" not in titles


def test_forward_window_only(parsed: list[ScrapedShow]) -> None:
    horizon = TODAY + dt.timedelta(days=the_mellow.SCRAPE_WINDOW_DAYS)
    assert all(TODAY <= s.start_local.date() <= horizon for s in parsed)
    assert all(s.start_local.date().year == 2026 for s in parsed)


def test_ticket_url_price_and_provenance(parsed: list[ScrapedShow]) -> None:
    lakehouse = next(s for s in parsed if s.headliner_raw == LAKEHOUSE)
    assert lakehouse.ticket_url is not None
    assert "eventbrite.com" in lakehouse.ticket_url
    assert lakehouse.price_text == "$35"
    assert lakehouse.source_url.startswith("https://themellowsf.com/events/")

    dumaine = next(s for s in parsed if s.headliner_raw == DUMAINE)
    assert dumaine.price_text == "$25"
    assert dumaine.source_url == (
        "https://themellowsf.com/events/mellow-sessions-rebecca-dumaine/"
    )


def test_missing_ticket_url_and_price_are_none(parsed: list[ScrapedShow]) -> None:
    bandstand = next(s for s in parsed if s.headliner_raw == "Mellow Sessions: Open Bandstand")
    assert bandstand.ticket_url is None
    assert bandstand.price_text is None
    assert bandstand.end_local is None  # evcal_erow of "0" is not an end time


def test_unknown_room_fails_loudly() -> None:
    # Silently folding an unrecognized room into one of the two known ones
    # would misroute shows; the ticket asks for a loud failure instead.
    index = _event_index()
    index[108400] = dict(index[108400], class_list=["event_location-the-mellow-oakland"])
    with pytest.raises(the_mellow.MellowSourceError, match="unrecognized event_location"):
        the_mellow.parse_occurrences(_occurrences(), index, today=TODAY)


def test_missing_location_taxonomy_fails_loudly() -> None:
    index = _event_index()
    index[108400] = dict(index[108400], class_list=["event_type-concerts"])
    with pytest.raises(the_mellow.MellowSourceError, match="no event_location term"):
        the_mellow.parse_occurrences(_occurrences(), index, today=TODAY)


def test_occurrence_without_matching_event_fails_loudly() -> None:
    index = _event_index()
    del index[99344]
    with pytest.raises(the_mellow.MellowSourceError, match="no matching REST object"):
        the_mellow.parse_occurrences(_occurrences(), index, today=TODAY)


# --------------------------------------------------------------------------
# fetch side
# --------------------------------------------------------------------------

# Trimmed to the two things the harvest needs: the params blob carrying the
# nonce, and the HTML-escaped shortcode config on the calendar footer.
_SHORTCODE = (
    "{&quot;event_count&quot;:&quot;15&quot;,&quot;show_repeats&quot;:&quot;no&quot;,"
    "&quot;hide_past&quot;:&quot;yes&quot;,&quot;_cver&quot;:&quot;5.0.11&quot;}"
)
CALENDAR_PAGE = f"""
<html><body>
<script>var evo_general_params = {{"ajaxurl":"https://themellowsf.com/wp-admin/admin-ajax.php",
"evo_ajax_url":"/?evo-ajax=%%endpoint%%","n":"6022d00af5","nonce":"e198d4b5a2",
"evo_v":"5.0.11"}};</script>
<div class='evo_cal_data' data-sc="{_SHORTCODE}"></div>
</body></html>
"""


def test_parse_calendar_config_reads_nonce_and_shortcode() -> None:
    nonce, shortcode = the_mellow.parse_calendar_config(CALENDAR_PAGE)
    assert nonce == "6022d00af5"
    assert shortcode["event_count"] == "15"
    assert shortcode["_cver"] == "5.0.11"


@pytest.mark.parametrize(
    "page, expected",
    [
        ("<html><body>no params here</body></html>", "evo_general_params not found"),
        (
            CALENDAR_PAGE.replace('"n":"6022d00af5",', ""),
            "no AJAX nonce",
        ),
        (
            CALENDAR_PAGE.replace("evo_cal_data", "evo_cal_gone"),
            "evo_cal_data shortcode config not found",
        ),
    ],
)
def test_parse_calendar_config_rejects_a_changed_page(page: str, expected: str) -> None:
    with pytest.raises(the_mellow.MellowSourceError, match=expected):
        the_mellow.parse_calendar_config(page)


def test_fetch_occurrences_drives_the_window_off_the_focus_range() -> None:
    seen: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params.get("evo-ajax") == "eventon_get_events"
        seen.append(dict(httpx.QueryParams(request.content.decode())))
        return httpx.Response(200, json={"status": "GOOD", "json": [{"event_id": 1}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    occurrences = the_mellow.fetch_occurrences(
        client,
        "abc123",
        {"event_count": "15", "show_repeats": "no", "focus_start_date_range": "1785567600"},
        TODAY,
        window_days=70,
    )

    assert len(occurrences) == 1
    assert len(seen) == 1, "the whole window comes back in one request"
    form = seen[0]
    assert form["nonce"] == "abc123"
    # 2026-08-11 00:00 PDT .. 2026-10-20 23:59:59 PDT.
    tz = the_mellow.VENUE_TZ
    start = dt.datetime.fromtimestamp(int(form["shortcode[focus_start_date_range]"]), tz)
    end = dt.datetime.fromtimestamp(int(form["shortcode[focus_end_date_range]"]), tz)
    assert start.date() == TODAY
    assert end.date() == TODAY + dt.timedelta(days=70)
    # Repeats must be expanded — the site's own config ships "no", which would
    # collapse a weekly series to one row.
    assert form["shortcode[show_repeats]"] == "yes"
    assert form["shortcode[show_limit]"] == "no"


def test_fetch_occurrences_raises_when_the_endpoint_refuses() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "bad"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(the_mellow.MellowSourceError, match="refused"):
        the_mellow.fetch_occurrences(client, "abc123", {}, TODAY, window_days=1)


def test_fetch_occurrences_raises_on_a_non_json_body() -> None:
    # Blanking the focus range makes the live endpoint answer with HTML.
    client = httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, text="<html>nope</html>"))
    )
    with pytest.raises(the_mellow.MellowSourceError, match="non-JSON body"):
        the_mellow.fetch_occurrences(client, "abc123", {}, TODAY, window_days=1)


def test_fetch_event_index_paginates() -> None:
    pages = {
        "1": [{"id": n, "class_list": []} for n in range(100)],
        "2": [{"id": 100, "class_list": []}],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=pages[request.url.params["page"]])

    client = httpx.Client(transport=httpx.MockTransport(handler))
    index = the_mellow.fetch_event_index(client)
    assert len(index) == 101
    assert 100 in index


def test_fetch_event_index_raises_on_an_empty_route() -> None:
    client = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=[])))
    with pytest.raises(the_mellow.MellowSourceError, match="returned no events"):
        the_mellow.fetch_event_index(client)
