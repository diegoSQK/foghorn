"""Tests for the auth surface (multi-user, August 2026): invite-link claim /
login, sessions, admin user management, per-user data isolation, the
single-tenant → multi-user schema migration, and single-user mode."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from foghorn.api import app
from foghorn.api.auth import SESSION_COOKIE
from foghorn.models import User
from foghorn.repo import db
from foghorn.repo import users as users_repo


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("FOGHORN_DB_PATH", str(tmp_path / "auth.db"))
    with TestClient(app) as test_client:
        yield test_client


def _invite(display_name: str = "Ada") -> str:
    """Create an invite directly in the DB; return the token."""
    conn = db.connect()
    try:
        return users_repo.create_invite(conn, display_name).invite_token
    finally:
        conn.close()


def test_claim_signs_in_and_sets_cookie(client: TestClient) -> None:
    token = _invite()
    info = client.get(f"/api/auth/invite/{token}").json()
    assert info == {"display_name": "Ada", "claimed": False}

    me = client.post("/api/auth/claim", json={"token": token})
    assert me.status_code == 200
    assert me.json()["display_name"] == "Ada"
    assert SESSION_COOKIE in client.cookies

    # The session works, and the invite now reads claimed.
    assert client.get("/api/auth/me").json()["display_name"] == "Ada"
    assert client.get(f"/api/auth/invite/{token}").json()["claimed"] is True


def test_claim_applies_rename_and_email(client: TestClient) -> None:
    token = _invite("Placeholder Name")
    me = client.post(
        "/api/auth/claim",
        json={"token": token, "display_name": "Grace", "email": "grace@example.com"},
    ).json()
    assert me["display_name"] == "Grace"
    assert me["email"] == "grace@example.com"


def test_invite_link_is_reusable_as_login(client: TestClient) -> None:
    token = _invite()
    client.post("/api/auth/claim", json={"token": token})
    first_session = client.cookies[SESSION_COOKIE]
    client.cookies.clear()  # "new device"
    client.post("/api/auth/claim", json={"token": token})
    assert client.cookies[SESSION_COOKIE] != first_session
    assert client.get("/api/auth/me").json()["display_name"] == "Ada"


def test_unknown_token_404s(client: TestClient) -> None:
    assert client.get("/api/auth/invite/nope").status_code == 404
    assert client.post("/api/auth/claim", json={"token": "nope"}).status_code == 404


def test_me_requires_session(client: TestClient) -> None:
    assert client.get("/api/auth/me").status_code == 401


def test_logout_ends_session(client: TestClient) -> None:
    client.post("/api/auth/claim", json={"token": _invite()})
    assert client.get("/api/auth/me").status_code == 200
    assert client.post("/api/auth/logout").status_code == 204
    client.cookies.clear()  # the delete-cookie response cleared it browser-side
    assert client.get("/api/auth/me").status_code == 401


def test_anonymous_watchlist_endpoints_401(client: TestClient) -> None:
    assert client.get("/api/watchlist").status_code == 401
    assert client.post("/api/watchlist", json={"display_name": "X"}).status_code == 401
    assert client.get("/api/venues/watchlist").status_code == 401
    assert client.get("/api/shows", params={"watchlist": "true"}).status_code == 401
    assert (
        client.get("/api/shows", params={"venue_watchlist": "true"}).status_code == 401
    )
    # Plain browse stays public.
    assert client.get("/api/shows").status_code == 200


def test_watchlists_are_isolated_per_user(client: TestClient) -> None:
    ada, grace = _invite("Ada"), _invite("Grace")
    client.post("/api/auth/claim", json={"token": ada})
    client.post("/api/watchlist", json={"display_name": "Kamasi Washington"})

    client.cookies.clear()
    client.post("/api/auth/claim", json={"token": grace})
    assert client.get("/api/watchlist").json() == []
    client.post("/api/watchlist", json={"display_name": "Joshua Redman"})

    client.cookies.clear()
    client.post("/api/auth/claim", json={"token": ada})
    names = [e["display_name"] for e in client.get("/api/watchlist").json()]
    assert names == ["Kamasi Washington"]


def test_admin_surface_requires_admin(client: TestClient, sign_in) -> None:
    assert client.get("/api/auth/users").status_code == 401
    sign_in(client)  # non-admin
    assert client.get("/api/auth/users").status_code == 403
    assert client.get("/api/inbox").status_code == 403
    assert (
        client.post("/api/auth/users", json={"display_name": "Eve"}).status_code == 403
    )


def test_admin_creates_regenerates_and_disables(client: TestClient, sign_in) -> None:
    admin = sign_in(client, admin=True)
    created = client.post("/api/auth/users", json={"display_name": "Eve"}).json()
    assert created["invite_path"].startswith("/join/")
    assert created["claimed_at"] is None

    regenerated = client.post(f"/api/auth/users/{created['id']}/regenerate").json()
    assert regenerated["invite_path"] != created["invite_path"]

    # Old link dead, new link works.
    old_token = created["invite_path"].removeprefix("/join/")
    new_token = regenerated["invite_path"].removeprefix("/join/")
    admin_cookie = client.cookies[SESSION_COOKIE]
    client.cookies.clear()
    assert client.post("/api/auth/claim", json={"token": old_token}).status_code == 404
    assert client.post("/api/auth/claim", json={"token": new_token}).status_code == 200
    eve_cookie = client.cookies[SESSION_COOKIE]

    # Disabling kills Eve's open session and her link; self-disable is blocked.
    client.cookies.set(SESSION_COOKIE, admin_cookie)
    disabled = client.put(
        f"/api/auth/users/{created['id']}/disabled", json={"disabled": True}
    ).json()
    assert disabled["disabled"] is True
    assert (
        client.put(
            f"/api/auth/users/{admin.id}/disabled", json={"disabled": True}
        ).status_code
        == 422
    )
    client.cookies.set(SESSION_COOKIE, eve_cookie)
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/claim", json={"token": new_token}).status_code == 404


# ---- Single-user mode (FOGHORN_SINGLE_USER=1) ------------------------------
#
# The Tailscale fleet deployment has no way to sign itself in (the iOS PWA
# gets its own storage container and can't open an invite link), so the flag
# resolves cookie-less requests as the bootstrap admin. Each test sets the
# env via monkeypatch so it never leaks to the rest of the suite.


def _bootstrap_admin(display_name: str = "Admin") -> User:
    conn = db.connect()
    try:
        created = users_repo.create_invite(conn, display_name, is_admin=True)
        assert created.id is not None
        return users_repo.claim(conn, created.id)
    finally:
        conn.close()


def test_single_user_off_by_default(client: TestClient) -> None:
    """The default posture, asserted explicitly so a future default flip
    fails loudly here rather than silently opening the VPS deployment."""
    _bootstrap_admin()
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/watchlist").status_code == 401
    assert client.get("/api/inbox").status_code == 401
    assert client.get("/api/shows").status_code == 200  # browsing stays public


def test_single_user_resolves_anonymous_to_bootstrap_admin(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin = _bootstrap_admin()
    monkeypatch.setenv("FOGHORN_SINGLE_USER", "1")

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json() == {
        "id": admin.id,
        "display_name": "Admin",
        "email": None,
        "is_admin": True,
        "single_user": True,
    }

    # Personal data resolves to that admin's rows, and mutations land there.
    assert client.get("/api/watchlist").json() == []
    added = client.post("/api/watchlist", json={"display_name": "Mary Halvorson"})
    assert added.status_code == 200
    assert [e["display_name"] for e in client.get("/api/watchlist").json()] == [
        "Mary Halvorson"
    ]
    assert client.get("/api/venues/watchlist").status_code == 200

    # Admin-only surfaces open up too.
    assert client.get("/api/inbox").status_code == 200
    assert client.get("/api/auth/users").status_code == 200


def test_single_user_picks_the_lowest_id_admin(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same account the multi-user migration assigned legacy rows to —
    not whichever admin was created most recently."""
    first = _bootstrap_admin("First Admin")
    _bootstrap_admin("Second Admin")
    monkeypatch.setenv("FOGHORN_SINGLE_USER", "1")
    assert client.get("/api/auth/me").json()["id"] == first.id


def test_single_user_yields_to_a_real_session(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, sign_in
) -> None:
    """A cookie always wins: a signed-in non-admin stays themselves rather
    than being upgraded to the bootstrap admin."""
    _bootstrap_admin()
    monkeypatch.setenv("FOGHORN_SINGLE_USER", "1")
    sign_in(client, display_name="Ada")  # non-admin

    me = client.get("/api/auth/me").json()
    assert me["display_name"] == "Ada"
    assert me["is_admin"] is False
    assert client.get("/api/auth/users").status_code == 403


def test_single_user_without_an_admin_stays_anonymous(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Degrade safely on an admin-less DB: no crash, no implicit user made."""
    monkeypatch.setenv("FOGHORN_SINGLE_USER", "1")
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/watchlist").status_code == 401

    conn = db.connect()
    try:
        assert users_repo.list_all(conn) == []
    finally:
        conn.close()


def test_single_user_startup_warns_and_names_the_admin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Unauthenticated admin should never be silent."""
    monkeypatch.setenv("FOGHORN_DB_PATH", str(tmp_path / "single.db"))
    admin = _bootstrap_admin("Diego")
    monkeypatch.setenv("FOGHORN_SINGLE_USER", "1")
    with caplog.at_level("WARNING"), TestClient(app):
        pass
    warnings = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
    assert any("FOGHORN_SINGLE_USER=1" in m and "Diego" in m for m in warnings)
    assert admin.id is not None


def test_no_startup_warning_when_flag_is_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("FOGHORN_DB_PATH", str(tmp_path / "multi.db"))
    _bootstrap_admin("Diego")
    with caplog.at_level("WARNING"), TestClient(app):
        pass
    assert not any("FOGHORN_SINGLE_USER" in r.getMessage() for r in caplog.records)


def test_migration_rekeys_existing_watchlists(tmp_path: Path) -> None:
    """A pre-multi-user DB (no user_id column) is rebuilt in place: rows land
    on a bootstrap admin created by the migration."""
    legacy = tmp_path / "legacy.db"
    raw = sqlite3.connect(legacy)
    raw.executescript(
        """
        CREATE TABLE watchlist (
            canonical_name TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            added_at TEXT NOT NULL,
            notes TEXT
        );
        CREATE TABLE watched_venues (
            venue_slug TEXT PRIMARY KEY,
            added_at TEXT NOT NULL,
            notes TEXT
        );
        INSERT INTO watchlist VALUES
            ('kamasi washington', 'Kamasi Washington', '2026-01-01T00:00:00+00:00', NULL);
        INSERT INTO watched_venues VALUES
            ('kilowatt', '2026-01-01T00:00:00+00:00', NULL);
        """
    )
    raw.commit()
    raw.close()

    conn = db.connect(legacy)  # runs init_schema → migration
    try:
        admins = [u for u in users_repo.list_all(conn) if u.is_admin]
        assert len(admins) == 1
        owner = admins[0]
        rows = conn.execute(
            "SELECT user_id, canonical_name FROM watchlist"
        ).fetchall()
        assert [(r["user_id"], r["canonical_name"]) for r in rows] == [
            (owner.id, "kamasi washington")
        ]
        pins = conn.execute("SELECT user_id, venue_slug FROM watched_venues").fetchall()
        assert [(r["user_id"], r["venue_slug"]) for r in pins] == [
            (owner.id, "kilowatt")
        ]
        # Idempotent: reconnecting doesn't duplicate or re-rebuild.
        conn.close()
        conn = db.connect(legacy)
        assert len([u for u in users_repo.list_all(conn) if u.is_admin]) == 1
    finally:
        conn.close()


def test_migration_on_empty_tables_creates_no_admin(tmp_path: Path) -> None:
    legacy = tmp_path / "empty_legacy.db"
    raw = sqlite3.connect(legacy)
    raw.executescript(
        """
        CREATE TABLE watchlist (
            canonical_name TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            added_at TEXT NOT NULL,
            notes TEXT
        );
        """
    )
    raw.commit()
    raw.close()
    conn = db.connect(legacy)
    try:
        assert users_repo.list_all(conn) == []
        assert {
            row[1] for row in conn.execute("PRAGMA table_info(watchlist)")
        } >= {"user_id", "canonical_name"}
    finally:
        conn.close()
