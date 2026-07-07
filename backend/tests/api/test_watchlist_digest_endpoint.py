"""Tests for ``GET /api/watchlist/digest`` (Phase 4.2).

The digest uses the real ``date.today()`` (no from/to params), so the fixture
ingests shows at offsets from today — clock-independent, unlike the param-driven
endpoint tests.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from foghorn.api import app
from foghorn.ingest.pipeline import ingest_scraped_shows
from foghorn.models import ScrapedShow
from foghorn.repo import db
from foghorn.repo import venues as venues_repo
from foghorn.repo import watched_venues as watched_venues_repo
from foghorn.repo import watchlist as watchlist_repo
from foghorn.repo.seed_venues import seed

TODAY = dt.date.today()


def _show(
    headliner: str,
    day_offset: int,
    support: list[str] | None = None,
    venue_slug: str = "bird_and_beckett",
) -> ScrapedShow:
    start = dt.datetime.combine(TODAY + dt.timedelta(days=day_offset), dt.time(20, 0))
    return ScrapedShow(
        venue_slug=venue_slug,
        headliner_raw=headliner,
        support_raw=support or [],
        start_local=start,
        source_url="https://example.com/show",
    )


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("FOGHORN_DB_PATH", str(tmp_path / "digest.db"))
    conn = db.connect()
    seed(conn)
    bb = venues_repo.get_by_slug(conn, "bird_and_beckett")
    assert bb is not None
    ingest_scraped_shows(
        conn,
        bb,
        [
            _show("Joshua Redman Quartet", 1),
            _show("Kamasi Washington", 2),
            _show("Some Other Band", 3),  # no watchlist match
            _show("Joshua Redman", 4, support=["Kamasi Washington"]),  # matches two
            _show("Far Future Act", 200),  # beyond the default 14-day window
        ],
    )
    for name in ["Joshua Redman", "Kamasi Washington", "Far Future Act"]:
        watchlist_repo.add(conn, name)
    conn.close()
    with TestClient(app) as test_client:
        yield test_client


def _names(matches: list[dict]) -> list[str]:
    return [m["headliner"]["display"] for m in matches]


def test_default_digest_filters_and_orders(client: TestClient) -> None:
    body = client.get("/api/watchlist/digest").json()
    assert "generated_at" in body
    # Ordered by start_utc; "Some Other Band" (no match) and "Far Future Act"
    # (beyond 14d) excluded.
    assert _names(body["matches"]) == [
        "Joshua Redman Quartet",
        "Kamasi Washington",
        "Joshua Redman",
    ]


def test_watchlist_matches_field(client: TestClient) -> None:
    matches = client.get("/api/watchlist/digest").json()["matches"]
    by_name = {m["headliner"]["display"]: m["watchlist_matches"] for m in matches}
    assert by_name["Joshua Redman Quartet"] == ["Joshua Redman"]
    assert by_name["Kamasi Washington"] == ["Kamasi Washington"]
    # The +4 show matches two watched names (headliner + support).
    assert sorted(by_name["Joshua Redman"]) == ["Joshua Redman", "Kamasi Washington"]


def test_days_widens_window(client: TestClient) -> None:
    assert "Far Future Act" not in _names(
        client.get("/api/watchlist/digest").json()["matches"]
    )
    wide = client.get("/api/watchlist/digest", params={"days": 365}).json()
    assert "Far Future Act" in _names(wide["matches"])


def test_limit_caps_results(client: TestClient) -> None:
    body = client.get("/api/watchlist/digest", params={"limit": 1}).json()
    assert len(body["matches"]) == 1
    assert body["matches"][0]["headliner"]["display"] == "Joshua Redman Quartet"


@pytest.fixture
def venue_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """Fixture for ``include_venues``: a performer watchlist *and* a watched
    venue (kilowatt), with a show that matches only a performer (+1), one only
    the venue (+2), and one both ways (+3, the dedup case)."""
    monkeypatch.setenv("FOGHORN_DB_PATH", str(tmp_path / "venue_digest.db"))
    conn = db.connect()
    seed(conn)
    bb = venues_repo.get_by_slug(conn, "bird_and_beckett")
    kilowatt = venues_repo.get_by_slug(conn, "kilowatt")
    assert bb is not None and kilowatt is not None
    ingest_scraped_shows(conn, bb, [_show("Joshua Redman Quartet", 1)])
    ingest_scraped_shows(
        conn,
        kilowatt,
        [
            _show("Venue Only Band", 2, venue_slug="kilowatt"),
            _show("Kamasi Washington", 3, venue_slug="kilowatt"),
        ],
    )
    watchlist_repo.add(conn, "Joshua Redman")
    watchlist_repo.add(conn, "Kamasi Washington")
    watched_venues_repo.add(conn, "kilowatt")
    conn.close()
    with TestClient(app) as test_client:
        yield test_client


def test_include_venues_off_is_old_behavior(venue_client: TestClient) -> None:
    # Param off (default): performer matches only — the watched venue's
    # unmatched show doesn't ride along, and no row is venue-flagged.
    body = venue_client.get("/api/watchlist/digest").json()
    assert _names(body["matches"]) == ["Joshua Redman Quartet", "Kamasi Washington"]
    assert all(m["watched_venue"] is False for m in body["matches"])


def test_include_venues_merges_flags_and_dedupes(venue_client: TestClient) -> None:
    body = venue_client.get(
        "/api/watchlist/digest", params={"include_venues": "true"}
    ).json()
    # Chronological union; the both-ways show appears exactly once.
    assert _names(body["matches"]) == [
        "Joshua Redman Quartet",
        "Venue Only Band",
        "Kamasi Washington",
    ]
    by_name = {m["headliner"]["display"]: m for m in body["matches"]}
    # Performer-only row: matched names, no venue flag.
    assert by_name["Joshua Redman Quartet"]["watchlist_matches"] == ["Joshua Redman"]
    assert by_name["Joshua Redman Quartet"]["watched_venue"] is False
    # Venue-only row: empty matches, flagged.
    assert by_name["Venue Only Band"]["watchlist_matches"] == []
    assert by_name["Venue Only Band"]["watched_venue"] is True
    # Both ways: flagged *and* matched.
    assert by_name["Kamasi Washington"]["watchlist_matches"] == ["Kamasi Washington"]
    assert by_name["Kamasi Washington"]["watched_venue"] is True


def test_include_venues_with_empty_performer_watchlist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Venue shows still surface when nothing is on the performer watchlist.
    monkeypatch.setenv("FOGHORN_DB_PATH", str(tmp_path / "venues_only.db"))
    conn = db.connect()
    seed(conn)
    kilowatt = venues_repo.get_by_slug(conn, "kilowatt")
    assert kilowatt is not None
    ingest_scraped_shows(
        conn, kilowatt, [_show("Venue Only Band", 1, venue_slug="kilowatt")]
    )
    watched_venues_repo.add(conn, "kilowatt")
    conn.close()
    with TestClient(app) as test_client:
        assert test_client.get("/api/watchlist/digest").json()["matches"] == []
        body = test_client.get(
            "/api/watchlist/digest", params={"include_venues": "true"}
        ).json()
    assert _names(body["matches"]) == ["Venue Only Band"]
    assert body["matches"][0]["watchlist_matches"] == []
    assert body["matches"][0]["watched_venue"] is True


def test_empty_watchlist_returns_empty_matches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FOGHORN_DB_PATH", str(tmp_path / "empty.db"))
    with TestClient(app) as test_client:
        body = test_client.get("/api/watchlist/digest").json()
    assert body["matches"] == []
    assert "generated_at" in body


def test_no_upcoming_matches_returns_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FOGHORN_DB_PATH", str(tmp_path / "nomatch.db"))
    conn = db.connect()
    seed(conn)
    watchlist_repo.add(conn, "Nobody In The Calendar")
    conn.close()
    with TestClient(app) as test_client:
        assert test_client.get("/api/watchlist/digest").json()["matches"] == []
