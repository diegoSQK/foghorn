"""``event_type="comedy"`` — the non-music category.

Music venues book stand-up between gigs. Ticketmaster classifies it under an
"Arts & Theatre" segment, which the batch scrapers previously dropped; a room
being busy on a Friday is worth knowing even when the reason isn't a band, so
it's now ingested, labelled and filterable instead.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
from typing import Any

import pytest

from foghorn.ingest.pipeline import infer_event_type, ingest_scraped_shows
from foghorn.models import ScrapedShow, ShowFilters, Venue
from foghorn.repo import shows as shows_repo
from foghorn.repo import venues as venues_repo
from foghorn.scrapers._ticketmaster import parse_events

TODAY = dt.date(2026, 7, 1)


def _event(name: str, segment: str | None, genre: str | None = None) -> dict[str, Any]:
    cls: dict[str, Any] = {}
    if segment is not None:
        cls["segment"] = {"name": segment}
    if genre is not None:
        cls["genre"] = {"name": genre}
    return {
        "name": name,
        "classifications": [cls] if cls else [],
        "dates": {"start": {"localDate": "2026-07-02", "localTime": "20:00:00"}},
    }


def _payload(*events: dict[str, Any]) -> dict[str, Any]:
    return {"_embedded": {"events": list(events)}}


# --------------------------------------------------------------------------
# classification
# --------------------------------------------------------------------------


def test_arts_and_theatre_becomes_comedy_instead_of_being_dropped() -> None:
    shows = parse_events(
        _payload(_event("CHELSEA HANDLER", "Arts & Theatre", "Comedy")),
        "the_masonic",
        TODAY,
    )
    assert [s.headliner_raw for s in shows] == ["CHELSEA HANDLER"]
    assert shows[0].event_type == "comedy"


def test_unclassified_comedians_still_land_as_comedy() -> None:
    # Jeff Dunham and John Mulaney carry the segment but no genre; keying on
    # the segment rather than the genre is what keeps them.
    shows = parse_events(
        _payload(_event("John Mulaney", "Arts & Theatre")), "mountain_winery", TODAY
    )
    assert shows[0].event_type == "comedy"


def test_music_and_unclassified_events_are_untouched() -> None:
    shows = parse_events(
        _payload(
            _event("Some Band", "Music", "Rock"),
            _event("Unclassified Gig", "Undefined"),
            _event("No Classification At All", None),
        ),
        "x",
        TODAY,
    )
    assert {s.headliner_raw for s in shows} == {
        "Some Band",
        "Unclassified Gig",
        "No Classification At All",
    }
    # None = no opinion; the pipeline's show/jam inference still applies.
    assert all(s.event_type is None for s in shows)


# --------------------------------------------------------------------------
# inference must never invent it
# --------------------------------------------------------------------------


def test_comedy_is_never_guessed_from_a_title() -> None:
    """A band called "Comedy Band Camp" is likelier than a good heuristic."""
    scraped = ScrapedShow(
        venue_slug="x",
        headliner_raw="JOSH JOHNSON'S COMEDY BAND CAMP",
        start_local=dt.datetime(2026, 7, 2, 20, 0),
        source_url="https://example.test/e",
    )
    assert infer_event_type(scraped) == "show"


def test_an_explicit_tag_survives_inference() -> None:
    scraped = ScrapedShow(
        venue_slug="x",
        headliner_raw="Some Comedian",
        start_local=dt.datetime(2026, 7, 2, 20, 0),
        source_url="https://example.test/e",
        event_type="comedy",
    )
    assert infer_event_type(scraped) == "comedy"


def test_jam_inference_still_works() -> None:
    scraped = ScrapedShow(
        venue_slug="x",
        headliner_raw="Tuesday Jazz Jam Session",
        start_local=dt.datetime(2026, 7, 2, 20, 0),
        source_url="https://example.test/e",
    )
    assert infer_event_type(scraped) == "jam"


# --------------------------------------------------------------------------
# persistence + filtering
# --------------------------------------------------------------------------


@pytest.fixture
def venue(conn: sqlite3.Connection) -> Venue:
    return venues_repo.upsert(
        conn,
        Venue(
            slug="comedy_room",
            name="Comedy Room",
            region="SF",
            tz="America/Los_Angeles",
            calendar_url="https://example.test/c",
            genre="eclectic",
        ),
    )


def _scraped(name: str, hour: int, event_type: str | None) -> ScrapedShow:
    return ScrapedShow(
        venue_slug="comedy_room",
        headliner_raw=name,
        start_local=dt.datetime(2026, 7, 2, hour, 0),
        source_url="https://example.test/e",
        event_type=event_type,  # type: ignore[arg-type]
    )


def test_comedy_round_trips_and_filters(
    conn: sqlite3.Connection, venue: Venue
) -> None:
    ingest_scraped_shows(
        conn,
        venue,
        [
            _scraped("A Band", 19, None),
            _scraped("A Comedian", 20, "comedy"),
            _scraped("Tuesday Jazz Jam Session", 21, None),
        ],
    )

    def names(**kw: Any) -> set[str]:
        return {
            p.display_name
            for s in shows_repo.list(conn, ShowFilters(**kw))
            for p in s.performers
            if p.role == "headliner"
        }

    # Unfiltered shows everything, comedy included.
    assert names() == {"A Band", "A Comedian", "Tuesday Jazz Jam Session"}
    assert names(event_type=["comedy"]) == {"A Comedian"}
    # ...and it's excludable, which is the point of a category over a drop.
    assert names(event_type=["show", "jam"]) == {"A Band", "Tuesday Jazz Jam Session"}
