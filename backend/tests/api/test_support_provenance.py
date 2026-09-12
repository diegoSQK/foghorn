"""`support` carries provenance so a bill line can show only what was billed.

#125 added derived performer links — the musicians parsed out of a collective
billing, and the full names their bare surnames resolved to. They make the
watchlist work. Rendered verbatim they turn one bill line into "with Ochs,
Larry Ochs, Johnston, Darren Johnston, Mezzacappa, Lisa Mezzacappa, Davis",
naming the same people two and three times.

So the API keeps them in the payload (the digest reads them to report *which*
followed name matched) and tags each with `source`; the UI renders only
`billed`. These tests pin both halves.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from foghorn.api import app
from foghorn.ingest.pipeline import canonicalize, ingest_scraped_shows
from foghorn.models import Performer, ScrapedShow
from foghorn.repo import db
from foghorn.repo import performers as performers_repo
from foghorn.repo import venues as venues_repo
from foghorn.repo.seed_venues import seed

BILLING = "Ochs/Johnston/Mezzacappa/Davis"


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("FOGHORN_DB_PATH", str(tmp_path / "api.db"))
    conn = db.connect()
    seed(conn)
    venue = venues_repo.get_by_slug(conn, "bird_and_beckett")
    assert venue is not None
    # Lisa is known from her other billings, so `mezzacappa` resolves.
    performers_repo.upsert(
        conn,
        Performer(
            display_name="Lisa Mezzacappa",
            canonical_name=canonicalize("Lisa Mezzacappa"),
        ),
    )
    ingest_scraped_shows(
        conn,
        venue,
        [
            ScrapedShow(
                venue_slug="bird_and_beckett",
                headliner_raw=BILLING,
                support_raw=["An Opener"],
                start_local=dt.datetime(2026, 6, 5, 19, 30),
                source_url="https://example.test/",
            )
        ],
    )
    conn.close()
    with TestClient(app) as test_client:
        yield test_client


def _show(client: TestClient) -> dict:
    rows = client.get(
        "/api/shows", params={"from": "2026-06-05", "to": "2026-06-05"}
    ).json()
    return next(row for row in rows if row["headliner"]["display"] == BILLING)


def test_billed_support_is_what_the_venue_printed(client: TestClient) -> None:
    show = _show(client)
    billed = [p["display"] for p in show["support"] if p["source"] == "billed"]
    assert billed == ["An Opener"]


def test_derived_links_are_present_but_tagged(client: TestClient) -> None:
    show = _show(client)
    derived = {p["display"]: p["source"] for p in show["support"]}
    assert derived["Ochs"] == "parsed"
    assert derived["Lisa Mezzacappa"] == "inferred"


def test_every_support_entry_carries_a_source(client: TestClient) -> None:
    """The UI filters on this field, so it must never be absent."""
    show = _show(client)
    assert all(p.get("source") for p in show["support"])
    assert {p["source"] for p in show["support"]} <= {
        "billed",
        "parsed",
        "inferred",
    }


def test_headliner_is_billed(client: TestClient) -> None:
    assert _show(client)["headliner"]["source"] == "billed"


def test_an_ordinary_show_is_all_billed(client: TestClient) -> None:
    """The 99% case: no derived links, so the bill line is unchanged from
    before #125."""
    rows = client.get(
        "/api/shows", params={"from": "2026-06-05", "to": "2026-06-05"}
    ).json()
    plain = [r for r in rows if r["headliner"]["display"] != BILLING]
    for row in plain:
        assert all(p["source"] == "billed" for p in row["support"])
