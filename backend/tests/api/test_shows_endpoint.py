"""Tests for ``GET /api/shows``.

Points the app at a tmp DB via ``FOGHORN_DB_PATH`` (read at connect time),
seeds + ingests a small deterministic set across two venues, then drives the
endpoint with ``TestClient``. Assertions use explicit ``from``/``to`` so they
don't depend on the wall clock.
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


def _show(
    venue_slug: str,
    headliner: str,
    start: dt.datetime,
    support: list[str] | None = None,
) -> ScrapedShow:
    return ScrapedShow(
        venue_slug=venue_slug,
        headliner_raw=headliner,
        support_raw=support or [],
        start_local=start,
        source_url="https://example.com/show",
    )


def _names(rows: list[dict]) -> list[str]:
    return [r["headliner"]["display"] for r in rows]


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("FOGHORN_DB_PATH", str(tmp_path / "api.db"))
    conn = db.connect()
    seed(conn)
    bb = venues_repo.get_by_slug(conn, "bird_and_beckett")
    keys = venues_repo.get_by_slug(conn, "keys_jazz_bistro")
    assert bb is not None and keys is not None
    ingest_scraped_shows(
        conn,
        bb,
        [
            _show("bird_and_beckett", "David Parker Sextet", dt.datetime(2026, 6, 5, 19, 30)),
            _show("bird_and_beckett", "Late Trio", dt.datetime(2026, 6, 5, 21, 30), ["An Opener"]),
            _show("bird_and_beckett", "Night Owls", dt.datetime(2026, 6, 5, 22, 30)),
            _show("bird_and_beckett", "Later Act", dt.datetime(2026, 6, 20, 20, 0)),
            # Far beyond any June window AND >30 days past 2026-06-01 — only
            # reachable when 'to=all' lifts the cap (see test_to_all_*).
            _show("bird_and_beckett", "Autumn Act", dt.datetime(2026, 9, 15, 20, 0)),
        ],
    )
    ingest_scraped_shows(
        conn,
        keys,
        [_show("keys_jazz_bistro", "Keys Quartet", dt.datetime(2026, 6, 7, 20, 0))],
    )
    conn.close()
    with TestClient(app) as test_client:
        yield test_client


def _june(client: TestClient, **params: str) -> list[dict]:
    return client.get(
        "/api/shows", params={"from": "2026-06-01", "to": "2026-06-30", **params}
    ).json()


def test_window_orders_by_start(client: TestClient) -> None:
    assert _names(_june(client)) == [
        "David Parker Sextet",  # 06-05 19:30
        "Late Trio",  # 06-05 21:30
        "Night Owls",  # 06-05 22:30
        "Keys Quartet",  # 06-07 20:00
        "Later Act",  # 06-20 20:00
    ]


def test_response_shape(client: TestClient) -> None:
    rows = client.get(
        "/api/shows", params={"from": "2026-06-05", "to": "2026-06-05"}
    ).json()
    late = next(r for r in rows if r["headliner"]["display"] == "Late Trio")
    assert late["venue"]["slug"] == "bird_and_beckett"
    assert late["venue"]["region"] == "SF"
    assert late["headliner"]["canonical"] == "late trio"
    assert [s["display"] for s in late["support"]] == ["An Opener"]
    assert late["start_local_time"] == "21:30"


def test_from_filter_excludes_earlier(client: TestClient) -> None:
    rows = client.get(
        "/api/shows", params={"from": "2026-06-06", "to": "2026-06-30"}
    ).json()
    assert _names(rows) == ["Keys Quartet", "Later Act"]


def test_venues_single(client: TestClient) -> None:
    assert _names(_june(client, venues="keys_jazz_bistro")) == ["Keys Quartet"]


def test_venues_multiple(client: TestClient) -> None:
    rows = _june(client, venues="bird_and_beckett,keys_jazz_bistro")
    assert len(rows) == 5
    assert {r["venue"]["slug"] for r in rows} == {"bird_and_beckett", "keys_jazz_bistro"}


def test_venues_unknown_is_empty(client: TestClient) -> None:
    assert _june(client, venues="not_a_venue") == []


def test_venues_mixed_valid_and_invalid(client: TestClient) -> None:
    # Unknown slugs simply don't match; valid ones still filter.
    rows = _june(client, venues="bird_and_beckett,not_a_venue")
    assert {r["venue"]["slug"] for r in rows} == {"bird_and_beckett"}
    assert len(rows) == 4


def test_legacy_singular_venue_param(client: TestClient) -> None:
    assert _names(_june(client, venue="keys_jazz_bistro")) == ["Keys Quartet"]


def test_time_of_day_early(client: TestClient) -> None:
    # start_local_time < 21:00 — excludes Late Trio (21:30) and Night Owls (22:30).
    assert _names(_june(client, time_of_day="early")) == [
        "David Parker Sextet",
        "Keys Quartet",
        "Later Act",
    ]


def test_time_of_day_late(client: TestClient) -> None:
    # start_local_time >= 21:00 — Late Trio (21:30) + Night Owls (22:30).
    assert _names(_june(client, time_of_day="late")) == ["Late Trio", "Night Owls"]


def test_early_and_late_partition_all_shows(client: TestClient) -> None:
    # No gap: every show is either early or late (Late is now 9pm+).
    early = _names(_june(client, time_of_day="early"))
    late = _names(_june(client, time_of_day="late"))
    assert len(early) + len(late) == len(_june(client))


def test_filters_stack(client: TestClient) -> None:
    rows = _june(client, venues="bird_and_beckett", time_of_day="early")
    assert _names(rows) == ["David Parker Sextet", "Later Act"]


def test_unknown_time_of_day_is_ignored(client: TestClient) -> None:
    # Bogus time_of_day doesn't 400 or filter everything out.
    assert len(_june(client, time_of_day="brunch")) == 5


def test_default_window_returns_200(client: TestClient) -> None:
    resp = client.get("/api/shows")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_limit_returns_chronological_prefix(client: TestClient) -> None:
    rows = client.get(
        "/api/shows", params={"from": "2026-06-01", "to": "all", "limit": "3"}
    ).json()
    assert _names(rows) == ["David Parker Sextet", "Late Trio", "Night Owls"]
    # limit larger than the result set is a no-op, and limit=0 is rejected.
    assert len(client.get(
        "/api/shows", params={"from": "2026-06-01", "to": "all", "limit": "99"}
    ).json()) == 6
    assert client.get(
        "/api/shows", params={"from": "2026-06-01", "limit": "0"}
    ).status_code == 422


def test_to_all_lifts_upper_bound(client: TestClient) -> None:
    # 'to=all' returns everything from `from` onward: Autumn Act (09-15) is
    # both outside every June window and >30 days past `from`, so it only
    # appears when the cap is genuinely lifted (not just widened).
    rows = client.get(
        "/api/shows", params={"from": "2026-06-01", "to": "all"}
    ).json()
    assert _names(rows) == [
        "David Parker Sextet",
        "Late Trio",
        "Night Owls",
        "Keys Quartet",
        "Later Act",
        "Autumn Act",
    ]
    # Still bounded below: a later `from` drops the June cluster.
    later = client.get(
        "/api/shows", params={"from": "2026-06-08", "to": "all"}
    ).json()
    assert _names(later) == ["Later Act", "Autumn Act"]
