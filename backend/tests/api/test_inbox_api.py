"""API tests for the mailing-list review queue (Phase 8 stage 1):
paste-ingest → inbox listing (with the duplicate warning) → approve/reject,
plus the sender-map CRUD."""

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

# Far-future fixed dates so yearless parsing ("the next occurrence") and the
# /api/shows window are stable no matter when the suite runs.
SHOW_DATE = "2030-07-24"
WINDOW = {"from": "2030-07-01", "to": "2030-07-31"}

EMAIL = {
    "from_addr": "Dillon Vado <list@dillonvado.com>",
    "subject": "Two July shows",
    "text": f"Friends! {SHOW_DATE} at Keys Jazz Bistro, doors 7. More soon.",
}


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sign_in) -> Iterator[TestClient]:
    monkeypatch.setenv("FOGHORN_DB_PATH", str(tmp_path / "api.db"))
    conn = db.connect()
    seed(conn)
    # A venue-scraped booking of the same artist (fuller billing string) on
    # the same night — the natural key won't collapse these, the token-match
    # warning must catch it.
    venue = venues_repo.get_by_slug(conn, "keys_jazz_bistro")
    assert venue is not None
    ingest_scraped_shows(
        conn,
        venue,
        [
            ScrapedShow(
                venue_slug="keys_jazz_bistro",
                headliner_raw="Dillon Vado Trio",
                start_local=dt.datetime(2030, 7, 24, 19, 30),
                source_url="https://example.com/keys/dillon-vado",
            )
        ],
    )
    conn.close()
    with TestClient(app) as test_client:
        sign_in(test_client, admin=True)
        test_client.post(
            "/api/inbox/senders",
            json={"email": "list@dillonvado.com", "artist_display": "Dillon Vado"},
        )
        yield test_client



def test_ingest_parses_and_queues(client: TestClient) -> None:
    resp = client.post("/api/inbox/ingest", json=EMAIL)
    assert resp.status_code == 201
    draft = resp.json()
    assert draft["artist_display"] == "Dillon Vado"
    assert draft["venue_slug"] == "keys_jazz_bistro"
    assert draft["date_guess"] == SHOW_DATE
    assert draft["time_guess"] == "19:00"  # doors 7 → 7pm
    assert draft["status"] == "pending"
    listed = client.get("/api/inbox").json()
    assert [row["id"] for row in listed] == [draft["id"]]


def test_inbox_warns_on_token_matched_duplicate(client: TestClient) -> None:
    client.post("/api/inbox/ingest", json=EMAIL)
    (row,) = client.get("/api/inbox").json()
    (duplicate,) = row["possible_duplicates"]
    assert duplicate["headliner"] == "Dillon Vado Trio"
    assert duplicate["start_local_date"] == SHOW_DATE
    assert duplicate["source"] == "scrape"


def test_unparseable_email_queues_raw_with_artist_prefilled(
    client: TestClient,
) -> None:
    resp = client.post(
        "/api/inbox/ingest",
        json={
            "from_addr": "list@dillonvado.com",
            "subject": "news",
            "text": "big announcement coming soon…",
        },
    )
    assert resp.status_code == 201
    draft = resp.json()
    assert draft["artist_display"] == "Dillon Vado"
    assert draft["venue_slug"] is None
    assert draft["date_guess"] is None
    assert draft["possible_duplicates"] == []
    assert draft["raw_text"] == "big announcement coming soon…"


def test_approve_creates_manual_show_and_clears_queue(client: TestClient) -> None:
    pending_id = client.post("/api/inbox/ingest", json=EMAIL).json()["id"]
    # Reviewer fixes the time (doors 7 → downbeat 7:30) and adds a link.
    resp = client.post(
        f"/api/inbox/{pending_id}/approve",
        json={"time": "19:30", "ticket_url": "https://example.com/tix"},
    )
    assert resp.status_code == 201
    created = resp.json()
    assert created["venue_slug"] == "keys_jazz_bistro"
    assert created["headliner"] == "Dillon Vado"
    rows = client.get("/api/shows", params=WINDOW).json()
    mine = next(r for r in rows if r["headliner"]["display"] == "Dillon Vado")
    assert mine["source"] == "manual"
    assert mine["start_local_time"] == "19:30"
    assert mine["ticket_url"] == "https://example.com/tix"
    # Provenance points at the queue row (pasted email — no Message-ID).
    assert mine["source_url"] == f"manual://email/pending-{pending_id}"
    assert client.get("/api/inbox").json() == []
    # A second approve is a conflict, not a duplicate event.
    assert client.post(f"/api/inbox/{pending_id}/approve", json={}).status_code == 409


def test_approve_with_new_venue_override(client: TestClient) -> None:
    pending_id = client.post(
        "/api/inbox/ingest",
        json={
            "from_addr": "list@dillonvado.com",
            "subject": "house show",
            "text": f"secret spot, {SHOW_DATE} 8pm",
        },
    ).json()["id"]
    resp = client.post(
        f"/api/inbox/{pending_id}/approve",
        json={"venue": {"name": "Adobe Books", "region": "SF"}, "event_type": "jam"},
    )
    assert resp.status_code == 201
    assert resp.json()["venue_slug"] == "adobe_books"
    rows = client.get("/api/shows", params=WINDOW).json()
    mine = next(r for r in rows if r["venue"]["slug"] == "adobe_books")
    assert mine["event_type"] == "jam"


def test_approve_422s_while_fields_still_missing(client: TestClient) -> None:
    pending_id = client.post(
        "/api/inbox/ingest",
        json={"from_addr": "who@unknown.example", "text": "no facts here"},
    ).json()["id"]
    resp = client.post(f"/api/inbox/{pending_id}/approve", json={})
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    for field in ("headliner", "venue", "date", "time"):
        assert field in detail
    # Still pending — nothing was created or consumed.
    assert len(client.get("/api/inbox").json()) == 1
    rows = client.get("/api/shows", params=WINDOW).json()
    assert all(r["source"] != "manual" for r in rows)


def test_reject_removes_from_queue_without_creating(client: TestClient) -> None:
    pending_id = client.post("/api/inbox/ingest", json=EMAIL).json()["id"]
    assert client.post(f"/api/inbox/{pending_id}/reject").status_code == 204
    assert client.get("/api/inbox").json() == []
    rows = client.get("/api/shows", params=WINDOW).json()
    assert all(r["headliner"]["display"] != "Dillon Vado" for r in rows)
    assert client.post("/api/inbox/9999/reject").status_code == 404


def test_sender_crud(client: TestClient) -> None:
    listed = client.get("/api/inbox/senders").json()
    assert listed == [
        {"email": "list@dillonvado.com", "artist_display": "Dillon Vado"}
    ]
    # POST upserts (case-insensitive on the address).
    resp = client.post(
        "/api/inbox/senders",
        json={"email": "List@DillonVado.com", "artist_display": "Dillon Vado Trio"},
    )
    assert resp.status_code == 201
    assert resp.json() == {
        "email": "list@dillonvado.com",
        "artist_display": "Dillon Vado Trio",
    }
    assert len(client.get("/api/inbox/senders").json()) == 1
    assert client.post(
        "/api/inbox/senders", json={"email": "not-an-address", "artist_display": "X"}
    ).status_code == 422
    assert client.delete("/api/inbox/senders/list@dillonvado.com").status_code == 204
    assert client.delete("/api/inbox/senders/list@dillonvado.com").status_code == 404
    assert client.get("/api/inbox/senders").json() == []
