"""War Memorial licensee feed, end to end (#128).

The ticket's central worry was the nightly reaper: registering a Davies source
that prunes would delete the SF Symphony aggregator's Davies rows, the same
failure mode `sfjazz.scrape_center()` exists to avoid, pointed the other way.
Landing this as an **aggregator** rather than a venue scraper dissolves it —
the aggregator tier ingests per event and never prunes — and these tests pin
that, so a future move into `REGISTERED_SCRAPERS` fails loudly.
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from pathlib import Path

from foghorn.aggregators import sf_war_memorial as wm
from foghorn.aggregators.ingest import ingest_aggregated_events
from foghorn.aggregators.models import AggregatedEvent
from foghorn.ingest.pipeline import canonicalize
from foghorn.models import ShowFilters, User
from foghorn.repo import shows as shows_repo
from foghorn.repo import venues as venues_repo
from foghorn.repo import watchlist as watchlist_repo
from foghorn.repo.performer_match import matches_token_bag
from foghorn.repo.seed_venues import seed

FIXTURE = (
    Path(__file__).parent.parent / "fixtures" / "sf_war_memorial_calendar.json"
)


def _events() -> list[AggregatedEvent]:
    return wm.parse_events(json.loads(FIXTURE.read_text(encoding="utf-8")))


def _rows(conn: sqlite3.Connection, slug: str) -> list:
    return shows_repo.list(conn, ShowFilters(venue_slugs=[slug]))


def test_events_route_to_their_seeded_halls(conn: sqlite3.Connection) -> None:
    seed(conn)
    result = ingest_aggregated_events(conn, _events(), wm.SOURCE_ID)
    assert result.errors == []

    for slug in (
        "davies_symphony_hall",
        "herbst_theatre",
        "war_memorial_opera_house",
        "wilsey_center_atrium",
    ):
        venue = venues_repo.get_by_slug(conn, slug)
        assert venue is not None, f"{slug} should be seeded"
        assert _rows(conn, slug), f"{slug} got no rows"


def test_opera_house_is_seeded(conn: sqlite3.Connection) -> None:
    """#128 assumed the Opera House was already a foghorn venue. It wasn't —
    so SF Opera's whole season and every Opera House rental had nowhere to
    land."""
    seed(conn)
    venue = venues_repo.get_by_slug(conn, "war_memorial_opera_house")
    assert venue is not None
    assert venue.region == "SF"
    assert venue.source == "seed"


def test_no_venue_still_points_at_the_dead_domain(conn: sqlite3.Connection) -> None:
    """sfwmpac.org stopped resolving (DNS failure, 2026-09-18)."""
    seed(conn)
    for venue in venues_repo.list_all(conn):
        assert "sfwmpac.org" not in (venue.website_url or "")
        assert "sfwmpac.org" not in (venue.calendar_url or "")


def test_the_reported_show_matches_its_watchlist_follow(
    conn: sqlite3.Connection, user: User
) -> None:
    """The acceptance case: a Julian Lage date SFJAZZ rented Davies for,
    invisible to both SFJAZZ's scraper and the Symphony feed."""
    assert user.id is not None
    seed(conn)
    ingest_aggregated_events(conn, _events(), wm.SOURCE_ID)
    watchlist_repo.add(conn, user.id, "Julian Lage", None)

    lage = [
        show
        for show in _rows(conn, "davies_symphony_hall")
        if matches_token_bag(canonicalize("Julian Lage"), show.headliner_canonical)
    ]
    assert len(lage) == 1
    assert lage[0].start_local_date == "2026-10-19"
    assert lage[0].start_local_time == "20:00"


def test_existing_aggregator_rows_survive_the_first_run(
    conn: sqlite3.Connection,
) -> None:
    """The reaper guard the ticket asked for. An existing Symphony row at
    Davies must still be there after this source first runs — that's the
    whole reason this is an aggregator and not a venue scraper."""
    seed(conn)
    davies = venues_repo.get_by_slug(conn, "davies_symphony_hall")
    assert davies is not None
    ingest_aggregated_events(
        conn,
        [
            AggregatedEvent(
                venue_name_raw="Davies Symphony Hall",
                headliner_raw="Elim Chan conducts Adams and Mendelssohn",
                support_raw=["San Francisco Symphony"],
                start_local=dt.datetime(2026, 10, 29, 19, 30),
                source_url="https://www.sfsymphony.org/x",
            )
        ],
        "sf_symphony",
    )
    before = {show.id for show in _rows(conn, "davies_symphony_hall")}
    assert before

    ingest_aggregated_events(conn, _events(), wm.SOURCE_ID)

    after = {show.id for show in _rows(conn, "davies_symphony_hall")}
    assert before <= after, "the War Memorial run deleted pre-existing rows"


def test_source_is_registered_as_an_aggregator_not_a_scraper() -> None:
    """Moving this into REGISTERED_SCRAPERS would re-arm the prune hazard,
    because the scheduler runs venue scrapers with prune=True."""
    from foghorn.aggregators import AGGREGATOR_SOURCES
    from foghorn.scrapers import REGISTERED_SCRAPERS

    assert wm.SOURCE_ID in AGGREGATOR_SOURCES
    for slug in (
        "davies_symphony_hall",
        "herbst_theatre",
        "war_memorial_opera_house",
        "wilsey_center_atrium",
    ):
        assert slug not in REGISTERED_SCRAPERS


def test_reingest_is_idempotent(conn: sqlite3.Connection) -> None:
    seed(conn)
    ingest_aggregated_events(conn, _events(), wm.SOURCE_ID)
    first = {show.id for show in _rows(conn, "herbst_theatre")}
    ingest_aggregated_events(conn, _events(), wm.SOURCE_ID)
    second = {show.id for show in _rows(conn, "herbst_theatre")}
    assert first == second


def test_defers_to_another_aggregators_better_billing(
    conn: sqlite3.Connection,
) -> None:
    """A building's booking record names events with internal labels —
    "TCHAIKOVSKY RACHMANINOV" where the presenter's own feed says "Tchaikovsky
    Symphony No. 4 / Rachmaninov Piano Concerto No. 2". The default guard
    ignores aggregator rows, so without opting in this feed re-listed such
    nights twice (measured: 2 duplicates at Herbst against the live DB)."""
    seed(conn)
    ingest_aggregated_events(
        conn,
        [
            AggregatedEvent(
                venue_name_raw="Herbst Theatre",
                headliner_raw="Tchaikovsky Symphony No. 4, Rachmaninov Piano Concerto No. 2",
                support_raw=[],
                start_local=dt.datetime(2027, 4, 24, 19, 30),
                source_url="https://example.test/presenter",
            )
        ],
        "sf_philharmonic",
    )
    before = len(_rows(conn, "herbst_theatre"))

    ingest_aggregated_events(
        conn,
        [
            AggregatedEvent(
                venue_name_raw="Herbst Theatre",
                headliner_raw="TCHAIKOVSKY RACHMANINOV",
                support_raw=[],
                start_local=dt.datetime(2027, 4, 24, 19, 30),
                source_url=wm.CALENDAR_URL,
            )
        ],
        wm.SOURCE_ID,
    )
    assert len(_rows(conn, "herbst_theatre")) == before


def test_other_aggregators_still_ignore_each_other(
    conn: sqlite3.Connection,
) -> None:
    """The opt-in must not change the default. Two presenter feeds listing the
    same hall on the same night are usually two real events, and suppressing
    one would lose a show."""
    seed(conn)
    common = dict(
        venue_name_raw="Herbst Theatre",
        support_raw=[],
        start_local=dt.datetime(2027, 4, 24, 19, 30),
        source_url="https://example.test/",
    )
    ingest_aggregated_events(
        conn, [AggregatedEvent(headliner_raw="Some Program", **common)], "sf_symphony"
    )
    before = len(_rows(conn, "herbst_theatre"))
    ingest_aggregated_events(
        conn,
        [AggregatedEvent(headliner_raw="Some Program Extended", **common)],
        "sf_philharmonic",
    )
    assert len(_rows(conn, "herbst_theatre")) == before + 1


def test_a_venue_scraped_row_wins_over_this_feed(conn: sqlite3.Connection) -> None:
    """If one of these halls ever gets its own scraper, the duplicate guard
    should defer to it rather than double-listing the night."""
    seed(conn)
    herbst = venues_repo.get_by_slug(conn, "herbst_theatre")
    assert herbst is not None
    event = next(
        e for e in _events() if e.venue_name_raw == "Herbst Theatre"
    )
    from foghorn.ingest.pipeline import ingest_scraped_shows
    from foghorn.models import ScrapedShow

    ingest_scraped_shows(
        conn,
        herbst,
        [
            ScrapedShow(
                venue_slug="herbst_theatre",
                headliner_raw=event.headliner_raw,
                support_raw=[],
                start_local=event.start_local,
                source_url="https://example.test/",
            )
        ],
    )
    before = len(_rows(conn, "herbst_theatre"))
    ingest_aggregated_events(conn, [event], wm.SOURCE_ID)
    assert len(_rows(conn, "herbst_theatre")) == before
