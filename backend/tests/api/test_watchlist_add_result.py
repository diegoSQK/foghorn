"""POST /api/watchlist reports what actually happened.

The endpoint has always been idempotent, which left callers unable to tell
"followed" from "you already follow them" — both returned 200 with the entry.
``created`` and ``already_covered_by`` make the outcome legible.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from foghorn.api import app


@pytest.fixture
def client(  # type: ignore[no-untyped-def]
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sign_in
) -> Iterator[TestClient]:
    monkeypatch.setenv("FOGHORN_DB_PATH", str(tmp_path / "wl.db"))
    with TestClient(app) as test_client:
        sign_in(test_client)
        yield test_client


def _add(client: TestClient, name: str) -> dict:
    resp = client.post("/api/watchlist", json={"display_name": name})
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_first_add_reports_created(client: TestClient) -> None:
    body = _add(client, "Christian McBride")
    assert body["created"] is True
    assert body["already_covered_by"] is None
    assert body["display_name"] == "Christian McBride"


def test_exact_duplicate_reports_not_created(client: TestClient) -> None:
    _add(client, "Christian McBride")
    body = _add(client, "Christian McBride")
    assert body["created"] is False
    # The original display name is preserved, not overwritten.
    assert body["display_name"] == "Christian McBride"


def test_duplicate_detection_is_canonical_not_literal(client: TestClient) -> None:
    # Different casing, punctuation and accents canonicalize to the same key,
    # so these are the *same* follow — the message has to say so.
    _add(client, "Cécile McLorin Salvant")
    for variant in ["cecile mclorin salvant", "CÉCILE MCLORIN SALVANT"]:
        assert _add(client, variant)["created"] is False


def test_reports_when_a_broader_entry_already_covers_it(client: TestClient) -> None:
    """The case the "+" buttons create.

    Matching is token-subset, so "Christian McBride" already matches the bill
    "Christian McBride's Ursa Major". Adding that longer billing is a new
    canonical key but matches strictly less — pointless, and the main way a
    list quietly grows.
    """
    _add(client, "Christian McBride")
    body = _add(client, "Christian McBride's Ursa Major")
    assert body["created"] is True  # genuinely a new key...
    assert body["already_covered_by"] == "Christian McBride"  # ...but redundant


def test_broadest_existing_entry_is_the_one_reported(client: TestClient) -> None:
    _add(client, "McBride")
    _add(client, "Christian McBride")
    body = _add(client, "Christian McBride Trio")
    assert body["already_covered_by"] == "McBride"


def test_a_narrower_existing_entry_does_not_count_as_coverage(
    client: TestClient,
) -> None:
    # "Christian McBride Trio" does NOT match every bill "Christian McBride"
    # would, so the broader add is a real widening, not a redundant one.
    _add(client, "Christian McBride Trio")
    body = _add(client, "Christian McBride")
    assert body["created"] is True
    assert body["already_covered_by"] is None


def test_unrelated_entries_are_not_reported_as_coverage(client: TestClient) -> None:
    _add(client, "Mary Halvorson")
    body = _add(client, "Christian McBride")
    assert body["already_covered_by"] is None


def test_blank_name_still_422s(client: TestClient) -> None:
    assert client.post("/api/watchlist", json={"display_name": "   "}).status_code == 422
    assert client.post("/api/watchlist", json={"display_name": "!!!"}).status_code == 422


def test_entry_is_still_added_when_covered(client: TestClient) -> None:
    # Reporting only — a redundant add is not silently refused, because the
    # user may be about to drop the broader entry.
    _add(client, "McBride")
    _add(client, "Christian McBride Trio")
    names = {e["display_name"] for e in client.get("/api/watchlist").json()}
    assert names == {"McBride", "Christian McBride Trio"}
