"""Tests for the Mills Littlefield (Trumba/25Live feed) scraper.

``parse_events`` is pure and driven from a trimmed live-feed fixture
(``fixtures/mills_littlefield_2026_07.json``) exercising the data-driven
filters: the music ``template`` keeps the Reinagle concert while a
Film/Movie row drops, a ``canceled`` music row drops, a music row in Lisser
Hall (not Littlefield) drops, the "— Mills Music Now" series suffix comes
off titles, and the description yields the Eventbrite ``ticket_url`` +
"Tickets:" ``price_text``. ``fetch_events`` is exercised with an
``httpx.MockTransport`` so no network is touched.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import httpx

from foghorn.scrapers import mills_littlefield

FIXTURE = (
    Path(__file__).parent.parent / "fixtures" / "mills_littlefield_2026_07.json"
)
TODAY = dt.date(2026, 7, 17)


def _events() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return rows


def test_only_littlefield_music_survives() -> None:
    shows = mills_littlefield.parse_events(_events(), TODAY)
    assert [show.headliner_raw for show in shows] == [
        "Alexander Reinagle: Composing a Nation"
    ]
    assert shows[0].venue_slug == "mills_college_littlefield_concert_hall"


def test_ticket_url_price_and_provenance() -> None:
    show = mills_littlefield.parse_events(_events(), TODAY)[0]
    assert show.start_local == dt.datetime(2026, 7, 20, 19, 30)
    assert show.ticket_url is not None and show.ticket_url.startswith(
        "https://www.eventbrite.com/e/"
    )
    assert show.price_text is not None and show.price_text.startswith("$")
    assert show.source_url.startswith(
        "https://performingarts.oakland.northeastern.edu"
    )


def test_series_suffix_strips() -> None:
    row = dict(_events()[0])
    row["title"] = "Iyad Sughayer, Dewing Piano Recital &#8212; Mills Music Now"
    shows = mills_littlefield.parse_events([row], TODAY)
    assert shows[0].headliner_raw == "Iyad Sughayer, Dewing Piano Recital"


def test_window_excludes_out_of_range() -> None:
    assert mills_littlefield.parse_events(_events(), TODAY, window_days=1) == []


def test_fetch_returns_list() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"eventID": "1"}])

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert mills_littlefield.fetch_events(client=client) == [{"eventID": "1"}]
