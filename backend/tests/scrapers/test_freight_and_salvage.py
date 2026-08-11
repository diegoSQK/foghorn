"""Tests for the Freight & Salvage (Tessitura TNEW) scraper.

``parse_productions`` is pure and driven from a trimmed snapshot of the live
``/api/products/productionseasons`` response
(``fixtures/freight_and_salvage_2026_08.json``), picked to exercise the cases
that actually occur in this feed: a plain single-night concert, a ``<br>`` +
``<font>`` subtitle, an ``&amp;`` entity, a two-night run, a three-date
residency, an entry filed under the concert product type that isn't a concert
(the library story time), the class programme (``productTypeId`` 2, "Fall I:"
naming), a "Tickets Not On Sale" performance, and a production past the forward
window. ``fetch_productions`` is exercised with an ``httpx.MockTransport`` so no
network is touched.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from foghorn.models import ScrapedShow
from foghorn.scrapers import freight_and_salvage

FIXTURE = Path(__file__).parent.parent / "fixtures" / "freight_and_salvage_2026_08.json"
TODAY = dt.date(2026, 8, 11)

MCFERRIN = "Bobby McFerrin and MOTION: Circlesongs"


def _productions() -> list[dict[str, Any]]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    productions: list[dict[str, Any]] = payload["productions"]
    return productions


@pytest.fixture
def parsed() -> list[ScrapedShow]:
    return freight_and_salvage.parse_productions(_productions(), today=TODAY)


def test_returns_expected_shows_sorted(parsed: list[ScrapedShow]) -> None:
    got = [(s.start_local.isoformat(), s.headliner_raw) for s in parsed]
    assert got == [
        ("2026-08-17T12:00:00", MCFERRIN),
        ("2026-08-21T20:00:00", "Zola Jesus"),
        ("2026-08-22T20:00:00", "Jeff Parker ETA IVtet"),
        ("2026-08-24T12:00:00", MCFERRIN),
        ("2026-08-31T12:00:00", MCFERRIN),
        ("2026-09-03T20:00:00", "Linda Tillery & The East Bay Allstars"),
        ("2026-09-04T20:00:00", "Bettye LaVette"),
        ("2026-09-05T20:00:00", "Bettye LaVette"),
        ("2026-09-14T19:30:00", "Community Mondays: Open Mic with Jamey Williams"),
        (
            "2026-09-28T19:30:00",
            "Community Mondays: Country Bluegrass Jam with Richard Brandenburg",
        ),
        (
            "2026-10-26T19:30:00",
            "Community Mondays: Fil Am Futurism with Karl Evangelista and Grex",
        ),
        ("2026-12-27T19:00:00", "Vienna Teng"),
        ("2026-12-28T20:00:00", "Vienna Teng"),
    ]


def test_local_times_come_from_the_iso_field(parsed: list[ScrapedShow]) -> None:
    # iso8601DateString is local-with-offset ("...T20:00:00.0000000-07:00") and
    # carries 7 fractional digits, which datetime.fromisoformat won't take
    # unaided. The naive local time must survive that intact — a tz-conversion
    # slip here would silently shift every show by 7 hours.
    parker = next(s for s in parsed if s.headliner_raw == "Jeff Parker ETA IVtet")
    assert parker.start_local == dt.datetime(2026, 8, 22, 20, 0)
    assert parker.start_local.tzinfo is None


def test_multi_night_run_and_residency_expand_per_date(parsed: list[ScrapedShow]) -> None:
    lavette = [s for s in parsed if s.headliner_raw == "Bettye LaVette"]
    assert [s.start_local.date().isoformat() for s in lavette] == ["2026-09-04", "2026-09-05"]
    mcferrin = [s for s in parsed if s.headliner_raw == MCFERRIN]
    assert [s.start_local.date().isoformat() for s in mcferrin] == [
        "2026-08-17",
        "2026-08-24",
        "2026-08-31",
    ]


def test_html_and_entities_are_stripped_from_titles(parsed: list[ScrapedShow]) -> None:
    titles = {s.headliner_raw for s in parsed}
    # "Zola Jesus<br />\n<font ...>Solo Voice + ..." — only the billed act.
    assert "Zola Jesus" in titles
    # "Linda Tillery &amp; The East Bay Allstars<br><font ...>" — entity kept
    # as a real ampersand, subtitle dropped.
    assert "Linda Tillery & The East Bay Allstars" in titles
    # " Bettye LaVette<br>..." — leading whitespace stripped.
    assert "Bettye LaVette" in titles
    assert not any("<" in t or "&amp;" in t for t in titles)


def test_term_class_programme_is_dropped(parsed: list[ScrapedShow]) -> None:
    # Filed under a "Fall I: <instructor>" production — the cleanest class
    # marker in the feed, and the reason productionTitle is consulted at all.
    assert not any("Tamsen Fynn" in s.headliner_raw for s in parsed)


def test_standalone_skill_level_classes_are_dropped(parsed: list[ScrapedShow]) -> None:
    # Outside the term programme, so only the skill-level title framing catches
    # these ("Beginning Harmonica with Aki Kumar").
    assert not any("Harmonica" in s.headliner_raw for s in parsed)


def test_community_mondays_is_kept_and_filtered_on_title(
    parsed: list[ScrapedShow],
) -> None:
    """The series sits on a non-concert product type but is real programming.

    Gating on productTypeId alone dropped 39 in-window entries on the live
    feed, including the weekly bluegrass jam and a booked Karl Evangelista
    gig — hence the series carve-out plus a title filter over it.
    """
    community = [s for s in parsed if s.headliner_raw.startswith("Community Mondays")]
    assert {s.headliner_raw.split(": ", 1)[1] for s in community} == {
        "Open Mic with Jamey Williams",
        "Country Bluegrass Jam with Richard Brandenburg",
        "Fil Am Futurism with Karl Evangelista and Grex",
    }
    # ...but its non-music nights still drop.
    assert not any("Comedy" in s.headliner_raw for s in parsed)
    assert not any("Listening Party" in s.headliner_raw for s in parsed)


def test_participatory_nights_are_tagged_as_jams(parsed: list[ScrapedShow]) -> None:
    # The ingest's own inference catches "open mic" but not "Country Bluegrass
    # Jam" (no genre word it knows, no session/night framing), so the scraper
    # tags explicitly — an explicit event_type always wins over inference.
    by_title = {s.headliner_raw: s.event_type for s in parsed}
    assert by_title["Community Mondays: Country Bluegrass Jam with Richard Brandenburg"] == "jam"
    assert by_title["Community Mondays: Open Mic with Jamey Williams"] == "jam"
    # A booked gig in the same series is not a jam.
    assert by_title["Community Mondays: Fil Am Futurism with Karl Evangelista and Grex"] is None
    assert by_title["Jeff Parker ETA IVtet"] is None


def test_non_concert_under_the_concert_product_type_is_dropped(
    parsed: list[ScrapedShow],
) -> None:
    # The library story time is productTypeId 3, so the id alone would keep it.
    assert not any("Story Time" in s.headliner_raw for s in parsed)


def test_forward_window_only(parsed: list[ScrapedShow]) -> None:
    horizon = TODAY + dt.timedelta(days=freight_and_salvage.SCRAPE_WINDOW_DAYS)
    assert all(TODAY <= s.start_local.date() <= horizon for s in parsed)
    assert not any("Debashish" in s.headliner_raw for s in parsed)


def test_ticket_url_and_provenance(parsed: list[ScrapedShow]) -> None:
    parker = next(s for s in parsed if s.headliner_raw == "Jeff Parker ETA IVtet")
    assert parker.source_url == (
        "https://secure.thefreight.org/15883/15884-jeff-parker-eta-ivtet-260822"
    )
    assert parker.ticket_url == parker.source_url
    # The feed publishes no price anywhere.
    assert all(s.price_text is None for s in parsed)


def test_not_yet_on_sale_keeps_the_show_but_drops_the_ticket_link(
    parsed: list[ScrapedShow],
) -> None:
    # "Tickets Not On Sale" is a real announced date; the link just wouldn't
    # sell anything yet, so provenance stays and ticket_url goes.
    teng = sorted(
        (s for s in parsed if s.headliner_raw == "Vienna Teng"), key=lambda s: s.start_local
    )
    on_sale, not_on_sale = teng
    assert on_sale.ticket_url is not None
    assert not_on_sale.ticket_url is None
    assert not_on_sale.source_url.startswith("https://secure.thefreight.org/")


def test_invisible_performances_are_skipped() -> None:
    productions = _productions()
    for production in productions:
        for performance in production["performances"]:
            performance["isPerformanceVisible"] = False
    assert freight_and_salvage.parse_productions(productions, today=TODAY) == []


# --------------------------------------------------------------------------
# fetch side
# --------------------------------------------------------------------------


def test_fetch_productions_posts_the_window_and_unwraps() -> None:
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert str(request.url) == freight_and_salvage.API_URL
        seen.append(json.loads(request.content.decode()))
        return httpx.Response(200, json={"productions": [{"productionSeasonId": "1"}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    productions = freight_and_salvage.fetch_productions(client, TODAY, window_days=180)

    assert productions == [{"productionSeasonId": "1"}]
    assert seen == [{"startDate": "2026-08-11T00:00", "endDate": "2027-02-07T23:59"}]


def test_fetch_productions_raises_on_a_non_json_body() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, text="<html>nope</html>"))
    )
    with pytest.raises(freight_and_salvage.FreightSourceError, match="non-JSON body"):
        freight_and_salvage.fetch_productions(client, TODAY)


def test_fetch_productions_raises_when_the_shape_changes() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"items": []}))
    )
    with pytest.raises(freight_and_salvage.FreightSourceError, match="no 'productions' key"):
        freight_and_salvage.fetch_productions(client, TODAY)


def test_fetch_productions_tolerates_an_empty_window() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"productions": None}))
    )
    assert freight_and_salvage.fetch_productions(client, TODAY) == []
