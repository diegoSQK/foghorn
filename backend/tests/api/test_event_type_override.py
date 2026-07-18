"""Tests for manual event-type corrections (PUT/DELETE
``/api/shows/{id}/event_type``) and their venue+billing override rules.

The rule semantics are the point: a correction survives re-ingest (the
nightly upsert rewrites ``shows.event_type``, so a row edit would be
clobbered) and applies to *every* show with the same billing at the venue —
which is how a recurring session ("Standards Hang") stays a jam when next
month's instance arrives with a fresh row.
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
from foghorn.repo.seed_venues import seed

VENUE = "little_hill_lounge"
BILLING = "Mark Clifford's Standards Hang"


def _scraped(day: int, headliner: str = BILLING) -> ScrapedShow:
    return ScrapedShow(
        venue_slug=VENUE,
        headliner_raw=headliner,
        start_local=dt.datetime(2026, 7, day, 20, 30),
        source_url="https://example.com/show",
    )


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("FOGHORN_DB_PATH", str(tmp_path / "api.db"))
    conn = db.connect()
    seed(conn)
    venue = venues_repo.get_by_slug(conn, VENUE)
    assert venue is not None
    # Two instances of the recurring session + one unrelated show.
    ingest_scraped_shows(conn, venue, [_scraped(7), _scraped(28)])
    ingest_scraped_shows(conn, venue, [_scraped(15, "Make No Bones")])
    conn.close()
    with TestClient(app) as test_client:
        yield test_client


def _shows(client: TestClient, **params: str) -> list[dict[str, object]]:
    response = client.get(
        "/api/shows", params={"from": "2026-07-01", "to": "2026-07-31", **params}
    )
    assert response.status_code == 200
    result: list[dict[str, object]] = response.json()
    return result


def test_put_marks_all_instances_of_the_billing(client: TestClient) -> None:
    shows = _shows(client)
    assert [s["event_type"] for s in shows] == ["show", "show", "show"]
    target = next(s for s in shows if s["start_local_date"] == "2026-07-07")

    response = client.put(
        f"/api/shows/{target['id']}/event_type", json={"event_type": "jam"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["event_type"] == "jam"
    assert body["applies_to_billing"] == "mark clifford s standards hang"

    by_date = {s["start_local_date"]: s["event_type"] for s in _shows(client)}
    # Both instances of the session flip; the unrelated show doesn't.
    assert by_date == {
        "2026-07-07": "jam",
        "2026-07-15": "show",
        "2026-07-28": "jam",
    }


def test_type_filter_respects_override(client: TestClient) -> None:
    target = _shows(client)[0]
    client.put(f"/api/shows/{target['id']}/event_type", json={"event_type": "jam"})
    jams = _shows(client, type="jam")
    assert {s["start_local_date"] for s in jams} == {"2026-07-07", "2026-07-28"}
    regulars = _shows(client, type="show")
    assert {s["start_local_date"] for s in regulars} == {"2026-07-15"}


def test_override_survives_reingest(client: TestClient) -> None:
    target = _shows(client)[0]
    client.put(f"/api/shows/{target['id']}/event_type", json={"event_type": "jam"})

    # The nightly re-scrape upserts the same natural key with the inferred
    # (non-jam) type — the rule must still win.
    conn = db.connect()
    venue = venues_repo.get_by_slug(conn, VENUE)
    assert venue is not None
    ingest_scraped_shows(conn, venue, [_scraped(7), _scraped(28)])
    conn.close()

    by_date = {s["start_local_date"]: s["event_type"] for s in _shows(client)}
    assert by_date["2026-07-07"] == "jam"
    assert by_date["2026-07-28"] == "jam"


def test_delete_reverts_to_inferred(client: TestClient) -> None:
    target = _shows(client)[0]
    client.put(f"/api/shows/{target['id']}/event_type", json={"event_type": "jam"})
    response = client.delete(f"/api/shows/{target['id']}/event_type")
    assert response.status_code == 204
    assert [s["event_type"] for s in _shows(client)] == ["show", "show", "show"]


def test_unknown_show_404s(client: TestClient) -> None:
    assert (
        client.put(
            "/api/shows/999999/event_type", json={"event_type": "jam"}
        ).status_code
        == 404
    )
    assert client.delete("/api/shows/999999/event_type").status_code == 404


def test_invalid_type_422s(client: TestClient) -> None:
    target = _shows(client)[0]
    response = client.put(
        f"/api/shows/{target['id']}/event_type", json={"event_type": "rave"}
    )
    assert response.status_code == 422
