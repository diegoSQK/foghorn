"""Tests for the shows repository: natural-key upsert + filtered listing."""

from __future__ import annotations

import sqlite3

from foghorn.ingest.pipeline import canonicalize
from foghorn.models import Performer, Show, ShowFilters, ShowPerformer, Venue
from foghorn.repo import performers as performers_repo
from foghorn.repo import shows as shows_repo
from foghorn.repo import venues as venues_repo


def _venue(
    conn: sqlite3.Connection,
    slug: str,
    region: str,
    neighborhood: str | None = None,
) -> Venue:
    return venues_repo.upsert(
        conn,
        Venue(
            slug=slug,
            name=slug.upper(),
            region=region,  # type: ignore[arg-type]  # tests pass valid Region values
            neighborhood=neighborhood,
            tz="America/Los_Angeles",
            calendar_url="https://example.com/cal",
        ),
    )


def _insert_show(
    conn: sqlite3.Connection,
    venue: Venue,
    *,
    date: str,
    time: str = "20:00",
    headliner: str = "Joshua Redman",
    support: list[str] | None = None,
    scraped_at: str = "2026-05-01T00:00:00+00:00",
    ticket_url: str | None = None,
) -> Show:
    assert venue.id is not None
    headliner_performer = performers_repo.upsert(
        conn,
        Performer(display_name=headliner, canonical_name=canonicalize(headliner)),
    )
    bill = [
        ShowPerformer(
            performer_id=headliner_performer.id,
            display_name=headliner_performer.display_name,
            canonical_name=headliner_performer.canonical_name,
            role="headliner",
            position=0,
        )
    ]
    for position, name in enumerate(support or [], start=1):
        support_performer = performers_repo.upsert(
            conn, Performer(display_name=name, canonical_name=canonicalize(name))
        )
        bill.append(
            ShowPerformer(
                performer_id=support_performer.id,
                display_name=support_performer.display_name,
                canonical_name=support_performer.canonical_name,
                role="support",
                position=position,
            )
        )
    show = Show(
        venue_id=venue.id,
        # For repo-level ordering tests, a date+time-derived UTC string is
        # enough; real tz math is exercised in the ingest tests.
        start_utc=f"{date}T{time}:00+00:00",
        start_local_date=date,
        start_local_time=time,
        headliner_canonical=canonicalize(headliner),
        ticket_url=ticket_url,
        source_url="https://example.com/show",
        scraped_at=scraped_at,
    )
    return shows_repo.upsert(conn, show, bill)


def test_upsert_idempotent_on_natural_key(conn: sqlite3.Connection) -> None:
    venue = _venue(conn, "sfjazz", "SF")
    first = _insert_show(
        conn, venue, date="2026-06-01", scraped_at="2026-05-01T00:00:00+00:00"
    )
    second = _insert_show(
        conn,
        venue,
        date="2026-06-01",
        scraped_at="2026-05-02T00:00:00+00:00",
        ticket_url="https://tix.example.com/x",
    )

    assert first.id == second.id  # same natural key -> same row
    all_shows = shows_repo.list(conn, ShowFilters())
    assert len(all_shows) == 1
    assert all_shows[0].scraped_at == "2026-05-02T00:00:00+00:00"  # refreshed
    assert all_shows[0].ticket_url == "https://tix.example.com/x"  # refreshed


def test_upsert_distinct_time_is_a_separate_show(conn: sqlite3.Connection) -> None:
    venue = _venue(conn, "sfjazz", "SF")
    _insert_show(conn, venue, date="2026-06-01", time="20:00")
    _insert_show(conn, venue, date="2026-06-01", time="22:00")  # late set, same act
    assert len(shows_repo.list(conn, ShowFilters())) == 2


def test_upsert_replaces_the_bill(conn: sqlite3.Connection) -> None:
    venue = _venue(conn, "sfjazz", "SF")
    _insert_show(conn, venue, date="2026-06-01", support=["The Bad Plus", "Dropped Act"])
    refreshed = _insert_show(conn, venue, date="2026-06-01", support=["The Bad Plus"])
    support_names = [p.display_name for p in refreshed.performers if p.role == "support"]
    assert support_names == ["The Bad Plus"]  # dropped act is gone, no stale links


def test_list_orders_by_start_utc(conn: sqlite3.Connection) -> None:
    venue = _venue(conn, "sfjazz", "SF")
    _insert_show(conn, venue, date="2026-06-10", headliner="Later Act")
    _insert_show(conn, venue, date="2026-06-01", headliner="Earlier Act")
    dates = [s.start_local_date for s in shows_repo.list(conn, ShowFilters())]
    assert dates == ["2026-06-01", "2026-06-10"]


def test_list_filters(conn: sqlite3.Connection) -> None:
    sfjazz = _venue(conn, "sfjazz", "SF")
    yoshis = _venue(conn, "yoshis", "East Bay")
    _insert_show(conn, sfjazz, date="2026-06-01", headliner="Joshua Redman")
    _insert_show(conn, sfjazz, date="2026-06-20", headliner="Kamasi Washington")
    _insert_show(conn, yoshis, date="2026-06-05", headliner="Brad Mehldau")

    # venue_slugs
    sf_only = shows_repo.list(conn, ShowFilters(venue_slugs=["sfjazz"]))
    assert {s.headliner_canonical for s in sf_only} == {
        "joshua redman",
        "kamasi washington",
    }

    # region
    east_bay = shows_repo.list(conn, ShowFilters(region="East Bay"))
    assert [s.headliner_canonical for s in east_bay] == ["brad mehldau"]

    # date window (inclusive, on start_local_date)
    windowed = shows_repo.list(
        conn, ShowFilters(from_date="2026-06-02", to_date="2026-06-10")
    )
    assert [s.headliner_canonical for s in windowed] == ["brad mehldau"]

    # performer token match (canonical)
    redman = shows_repo.list(
        conn, ShowFilters(performer_query_canonical="redman")
    )
    assert [s.headliner_canonical for s in redman] == ["joshua redman"]


def test_list_substring_matches_support_acts(conn: sqlite3.Connection) -> None:
    venue = _venue(conn, "sfjazz", "SF")
    _insert_show(
        conn, venue, date="2026-06-01", headliner="Headliner", support=["Esperanza Spalding"]
    )
    matched = shows_repo.list(
        conn, ShowFilters(performer_query_canonical="esperanza")
    )
    assert len(matched) == 1


def test_list_filters_by_neighborhood(conn: sqlite3.Connection) -> None:
    north_beach = _venue(conn, "keys_jazz_bistro", "SF", neighborhood="North Beach")
    glen_park = _venue(conn, "bird_and_beckett", "SF", neighborhood="Glen Park")
    _insert_show(conn, north_beach, date="2026-06-01", headliner="Keys Act")
    _insert_show(conn, glen_park, date="2026-06-02", headliner="Bird Act")

    exact = shows_repo.list(conn, ShowFilters(neighborhood="North Beach"))
    assert [s.headliner_canonical for s in exact] == ["keys act"]

    # Case-insensitive exact match (COLLATE NOCASE).
    lowered = shows_repo.list(conn, ShowFilters(neighborhood="north beach"))
    assert [s.headliner_canonical for s in lowered] == ["keys act"]

    # Region + neighborhood stack as an AND.
    combined = shows_repo.list(
        conn, ShowFilters(region="SF", neighborhood="Glen Park")
    )
    assert [s.headliner_canonical for s in combined] == ["bird act"]
