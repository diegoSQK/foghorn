"""Multi-select facets: OR within a facet, AND across facets.

A show has exactly one region and one resolved genre, so selecting two values
in one facet can only sensibly mean "either" — a literal intersection would
match nothing. Facets still narrow each other.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from foghorn.api import app
from foghorn.ingest.pipeline import ingest_scraped_shows
from foghorn.models import ScrapedShow, Venue
from foghorn.repo import db
from foghorn.repo import venues as venues_repo

DAY = "2026-06-05"


def _venue(
    conn: sqlite3.Connection, slug: str, region: str, hood: str, genre: str
) -> Venue:
    return venues_repo.upsert(
        conn,
        Venue(
            slug=slug,
            name=slug.replace("_", " ").title(),
            neighborhood=hood,
            region=region,  # type: ignore[arg-type]
            tz="America/Los_Angeles",
            calendar_url="https://example.test/c",
            genre=genre,
        ),
    )


def _show(slug: str, headliner: str, hour: int, jam: bool = False) -> ScrapedShow:
    return ScrapedShow(
        venue_slug=slug,
        headliner_raw=headliner,
        start_local=dt.datetime(2026, 6, 5, hour, 0),
        source_url="https://example.test/s",
        event_type="jam" if jam else None,
    )


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("FOGHORN_DB_PATH", str(tmp_path / "facets.db"))
    conn = db.connect()
    rooms = {
        "sf_jazz_room": _venue(conn, "sf_jazz_room", "SF", "Mission", "jazz"),
        "eb_rock_room": _venue(conn, "eb_rock_room", "East Bay", "Uptown", "rock"),
        "nb_folk_room": _venue(conn, "nb_folk_room", "North Bay", "Fairfax", "folk"),
    }
    ingest_scraped_shows(conn, rooms["sf_jazz_room"], [_show("sf_jazz_room", "SF Jazz Act", 20)])
    ingest_scraped_shows(
        conn,
        rooms["eb_rock_room"],
        [_show("eb_rock_room", "EB Rock Act", 20), _show("eb_rock_room", "EB Jam Act", 21, jam=True)],
    )
    ingest_scraped_shows(conn, rooms["nb_folk_room"], [_show("nb_folk_room", "NB Folk Act", 20)])
    conn.commit()
    conn.close()
    with TestClient(app) as test_client:
        yield test_client


def _names(client: TestClient, query: str) -> set[str]:
    resp = client.get(f"/api/shows?from={DAY}&to={DAY}&{query}")
    assert resp.status_code == 200, resp.text
    return {s["headliner"]["display"] for s in resp.json()}


def test_single_value_behaves_as_before(client: TestClient) -> None:
    # Old single-value URLs and bookmarks must keep working unchanged.
    assert _names(client, "region=SF") == {"SF Jazz Act"}
    assert _names(client, "genre=rock") == {"EB Rock Act", "EB Jam Act"}


def test_multiple_values_in_one_facet_or_together(client: TestClient) -> None:
    assert _names(client, "region=SF,East Bay") == {
        "SF Jazz Act",
        "EB Rock Act",
        "EB Jam Act",
    }
    assert _names(client, "genre=jazz,folk") == {"SF Jazz Act", "NB Folk Act"}


def test_facets_still_and_together(client: TestClient) -> None:
    # region OR-set intersected with genre OR-set.
    assert _names(client, "region=SF,East Bay&genre=rock") == {
        "EB Rock Act",
        "EB Jam Act",
    }
    # An impossible combination yields nothing rather than erroring.
    assert _names(client, "region=SF&genre=folk") == set()


def test_neighborhood_multi_select(client: TestClient) -> None:
    assert _names(client, "neighborhood=Mission,Uptown") == {
        "SF Jazz Act",
        "EB Rock Act",
        "EB Jam Act",
    }
    # Still case-insensitive, per value.
    assert _names(client, "neighborhood=mission,UPTOWN") == {
        "SF Jazz Act",
        "EB Rock Act",
        "EB Jam Act",
    }


def test_event_type_multi_select(client: TestClient) -> None:
    assert _names(client, "type=jam") == {"EB Jam Act"}
    # Both selected == the unfiltered set, not an empty intersection.
    assert _names(client, "type=show,jam") == _names(client, "")


def test_unknown_values_are_dropped_not_400(client: TestClient) -> None:
    # A stale bookmark degrades to a broader result set rather than an error.
    assert _names(client, "region=SF,Atlantis") == {"SF Jazz Act"}
    assert _names(client, "type=show,nonsense") == {
        "SF Jazz Act",
        "EB Rock Act",
        "NB Folk Act",
    }
    # All values unknown == facet not constrained.
    assert _names(client, "region=Atlantis") == _names(client, "")


def test_whitespace_and_duplicates_are_tolerated(client: TestClient) -> None:
    assert _names(client, "region=SF , East Bay ,SF") == {
        "SF Jazz Act",
        "EB Rock Act",
        "EB Jam Act",
    }


def test_empty_and_blank_values_mean_unconstrained(client: TestClient) -> None:
    everything = _names(client, "")
    assert _names(client, "region=") == everything
    assert _names(client, "genre=,,") == everything
