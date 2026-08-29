"""MCP tool-layer tests.

The server is a thin httpx wrapper over the FastAPI app, so these drive the
tool layer with the HTTP calls mocked — no uvicorn, no SQLite. What's worth
asserting is exactly what the wrapper owns: parameter passthrough (especially
the multi-value facets and the `from` keyword alias), the defaults it invents
(limit=50), the auth header, and the structured-error branches.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest
from mcp.server.fastmcp.exceptions import ToolError

from foghorn.mcp import server as mcp_server


class _MockTransport:
    """Canned responses keyed by (method, path).

    An entry is either a JSON body (implies 200) or a ``(status, body)``
    tuple; ``body=None`` produces an empty response, which is how the 204
    delete paths behave.
    """

    def __init__(self, responses: dict[tuple[str, str], Any]) -> None:
        self.responses = responses
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        key = (request.method, request.url.path)
        if key not in self.responses:
            return httpx.Response(404, json={"detail": f"unmocked {key}"})
        entry = self.responses[key]
        if isinstance(entry, tuple) and len(entry) == 2 and isinstance(entry[0], int):
            status_code, body = entry
            if body is None:
                return httpx.Response(status_code)
            return httpx.Response(status_code, json=body)
        return httpx.Response(200, json=entry)

    @property
    def last(self) -> httpx.Request:
        return self.requests[-1]

    def query(self) -> dict[str, list[str]]:
        return parse_qs(self.last.url.query.decode())


@pytest.fixture
def transport(monkeypatch: pytest.MonkeyPatch) -> _MockTransport:
    mock = _MockTransport({})
    real_client = httpx.Client

    def _client_factory(*args: Any, **kwargs: Any) -> httpx.Client:
        kwargs["transport"] = httpx.MockTransport(mock)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(mcp_server.httpx, "Client", _client_factory)
    # Never inherit a real token from the developer's environment.
    monkeypatch.delenv("FOGHORN_MCP_SESSION", raising=False)
    monkeypatch.delenv("FOGHORN_API_URL", raising=False)
    return mock


def _call_tool(name: str, args: dict[str, Any]) -> Any:
    server = mcp_server.build_server()
    contents, _structured = asyncio.run(server.call_tool(name, args))
    return json.loads(contents[0].text)  # type: ignore[union-attr]


TOOL_NAMES = {
    "list_shows",
    "list_venues",
    "get_watchlist",
    "list_watched_venues",
    "get_watchlist_digest",
    "add_watchlist_performer",
    "remove_watchlist_performer",
    "watch_venue",
    "unwatch_venue",
    "add_event",
    "remove_event",
    "set_event_type",
    "clear_event_type",
}


def test_build_server_registers_the_full_tool_set() -> None:
    tools = asyncio.run(mcp_server.build_server().list_tools())
    assert {tool.name for tool in tools} == TOOL_NAMES


def test_no_resources_are_registered() -> None:
    """Tools only for v1 — foghorn's surface is almost entirely
    parameterized, so there's nothing a parameter-less resource would add."""
    assert asyncio.run(mcp_server.build_server().list_resources()) == []


def test_every_write_tool_description_asks_for_confirmation() -> None:
    writes = {
        "add_watchlist_performer",
        "remove_watchlist_performer",
        "watch_venue",
        "unwatch_venue",
        "add_event",
        "remove_event",
        "set_event_type",
        "clear_event_type",
    }
    tools = asyncio.run(mcp_server.build_server().list_tools())
    for tool in tools:
        if tool.name in writes:
            assert "confirm with the user" in (tool.description or "").lower()


# --------------------------------------------------------------------- reads


def test_list_shows_defaults_to_limit_50_and_sends_nothing_else(
    transport: _MockTransport,
) -> None:
    transport.responses[("GET", "/api/shows")] = [{"id": 1}]
    body = _call_tool("list_shows", {})
    assert body == [{"id": 1}]
    assert transport.query() == {"limit": ["50"]}
    assert str(transport.last.url).startswith(mcp_server.DEFAULT_BASE_URL)


def test_list_shows_passes_every_facet_through(transport: _MockTransport) -> None:
    transport.responses[("GET", "/api/shows")] = []
    _call_tool(
        "list_shows",
        {
            "venues": ["bird_and_beckett", "keys_jazz_bistro"],
            "from_": "2026-09-01",
            "to": "2026-09-30",
            "time_of_day": "late",
            "performer_query": "dillon vado",
            "region": ["SF", "East Bay"],
            "neighborhood": "Mission",
            "genre": ["jazz", "experimental"],
            "origin": "local",
            "type": ["jam", "comedy"],
            "watchlist": True,
            "venue_watchlist": True,
            "long_tail": True,
            "limit": 10,
        },
    )
    assert transport.query() == {
        "venues": ["bird_and_beckett,keys_jazz_bistro"],
        # `from` is a Python keyword: the tool takes `from_`, the wire gets
        # the alias the API actually reads.
        "from": ["2026-09-01"],
        "to": ["2026-09-30"],
        "time_of_day": ["late"],
        "performer_query": ["dillon vado"],
        "region": ["SF,East Bay"],
        "neighborhood": ["Mission"],
        "genre": ["jazz,experimental"],
        "origin": ["local"],
        "type": ["jam,comedy"],
        "watchlist": ["true"],
        "venue_watchlist": ["true"],
        "long_tail": ["true"],
        "limit": ["10"],
    }


def test_list_shows_accepts_to_all(transport: _MockTransport) -> None:
    transport.responses[("GET", "/api/shows")] = []
    _call_tool("list_shows", {"to": "all"})
    assert transport.query()["to"] == ["all"]


def test_list_shows_omits_unset_flags(transport: _MockTransport) -> None:
    """An unset boolean must not travel as 'false' — the API reads these as
    the literal string 'true', so anything else is noise on the wire."""
    transport.responses[("GET", "/api/shows")] = []
    _call_tool("list_shows", {"watchlist": False, "long_tail": False})
    assert "watchlist" not in transport.query()
    assert "long_tail" not in transport.query()


def test_list_venues(transport: _MockTransport) -> None:
    transport.responses[("GET", "/api/venues")] = [
        {"slug": "bird_and_beckett", "name": "Bird & Beckett", "source": "seed"}
    ]
    assert _call_tool("list_venues", {})[0]["slug"] == "bird_and_beckett"


def test_get_watchlist(transport: _MockTransport) -> None:
    transport.responses[("GET", "/api/watchlist")] = [
        {"canonical_name": "dillon vado", "display_name": "Dillon Vado"}
    ]
    assert _call_tool("get_watchlist", {})[0]["canonical_name"] == "dillon vado"


def test_list_watched_venues(transport: _MockTransport) -> None:
    transport.responses[("GET", "/api/venues/watchlist")] = [
        {"venue_slug": "the_chapel", "name": "The Chapel"}
    ]
    assert _call_tool("list_watched_venues", {})[0]["venue_slug"] == "the_chapel"


def test_watchlist_digest_defaults_and_overrides(transport: _MockTransport) -> None:
    transport.responses[("GET", "/api/watchlist/digest")] = {
        "generated_at": "2026-08-29T00:00:00+00:00",
        "matches": [],
    }
    _call_tool("get_watchlist_digest", {})
    assert transport.query() == {"days": ["14"], "limit": ["20"]}

    _call_tool("get_watchlist_digest", {"days": 30, "limit": 5, "include_venues": True})
    assert transport.query() == {
        "days": ["30"],
        "limit": ["5"],
        "include_venues": ["true"],
    }


# -------------------------------------------------------------------- writes


def test_add_watchlist_performer(transport: _MockTransport) -> None:
    transport.responses[("POST", "/api/watchlist")] = {
        "canonical_name": "dillon vado",
        "display_name": "Dillon Vado",
        "created": True,
        "already_covered_by": None,
    }
    body = _call_tool(
        "add_watchlist_performer", {"display_name": "Dillon Vado", "notes": "drums"}
    )
    assert body["created"] is True
    assert json.loads(transport.last.content) == {
        "display_name": "Dillon Vado",
        "notes": "drums",
    }


def test_add_watchlist_performer_422_is_structured(transport: _MockTransport) -> None:
    transport.responses[("POST", "/api/watchlist")] = (
        422,
        {"detail": "display_name must contain a name"},
    )
    body = _call_tool("add_watchlist_performer", {"display_name": "!!!"})
    assert body == {"error": "display_name must contain a name", "status": 422}


def test_remove_watchlist_performer(transport: _MockTransport) -> None:
    transport.responses[("DELETE", "/api/watchlist/dillon vado")] = (204, None)
    body = _call_tool("remove_watchlist_performer", {"canonical_name": "dillon vado"})
    assert body == {"removed": True, "canonical_name": "dillon vado"}


def test_remove_watchlist_performer_404_is_structured(
    transport: _MockTransport,
) -> None:
    transport.responses[("DELETE", "/api/watchlist/nobody")] = (
        404,
        {"detail": "not on watchlist"},
    )
    body = _call_tool("remove_watchlist_performer", {"canonical_name": "nobody"})
    assert body == {"error": "not on watchlist", "status": 404}


def test_watch_and_unwatch_venue(transport: _MockTransport) -> None:
    transport.responses[("POST", "/api/venues/watchlist")] = (
        201,
        {"venue_slug": "the_chapel", "name": "The Chapel"},
    )
    body = _call_tool("watch_venue", {"venue_slug": "the_chapel"})
    assert body["venue_slug"] == "the_chapel"
    assert json.loads(transport.last.content) == {"venue_slug": "the_chapel"}

    transport.responses[("DELETE", "/api/venues/watchlist/the_chapel")] = (204, None)
    assert _call_tool("unwatch_venue", {"venue_slug": "the_chapel"}) == {
        "removed": True,
        "venue_slug": "the_chapel",
    }


def test_watch_venue_unknown_slug_is_structured(transport: _MockTransport) -> None:
    transport.responses[("POST", "/api/venues/watchlist")] = (
        404,
        {"detail": "unknown venue slug"},
    )
    body = _call_tool("watch_venue", {"venue_slug": "nope"})
    assert body == {"error": "unknown venue slug", "status": 404}


def test_add_event_with_existing_venue_slug(transport: _MockTransport) -> None:
    transport.responses[("POST", "/api/events")] = (
        201,
        {
            "id": 42,
            "venue_slug": "bird_and_beckett",
            "headliner": "Thursday Hang",
            "start_local_date": "2026-09-03",
            "start_local_time": "20:00",
        },
    )
    body = _call_tool(
        "add_event",
        {
            "venue_slug": "bird_and_beckett",
            "headliner": "Thursday Hang",
            "date": "2026-09-03",
            "time": "20:00",
            "event_type": "jam",
        },
    )
    assert body["id"] == 42
    assert json.loads(transport.last.content) == {
        "venue_slug": "bird_and_beckett",
        "headliner": "Thursday Hang",
        "date": "2026-09-03",
        "time": "20:00",
        "event_type": "jam",
    }


def test_add_event_with_a_new_venue_object(transport: _MockTransport) -> None:
    transport.responses[("POST", "/api/events")] = (201, {"id": 43})
    _call_tool(
        "add_event",
        {
            "venue": {"name": "Someone's Living Room", "region": "SF"},
            "headliner": "House Trio",
            "date": "2026-09-04",
            "time": "19:30",
            "support": ["Opener"],
        },
    )
    assert json.loads(transport.last.content) == {
        # exclude_none keeps the optional venue fields off the wire so the
        # API's own defaults apply.
        "venue": {"name": "Someone's Living Room", "region": "SF"},
        "headliner": "House Trio",
        "support": ["Opener"],
        "date": "2026-09-04",
        "time": "19:30",
        "event_type": "show",
    }


def test_add_event_422_is_structured(transport: _MockTransport) -> None:
    transport.responses[("POST", "/api/events")] = (
        422,
        {"detail": "provide exactly one of venue_slug or venue"},
    )
    body = _call_tool(
        "add_event", {"headliner": "X", "date": "2026-09-04", "time": "19:30"}
    )
    assert body == {
        "error": "provide exactly one of venue_slug or venue",
        "status": 422,
    }


def test_remove_event(transport: _MockTransport) -> None:
    transport.responses[("DELETE", "/api/events/42")] = (204, None)
    assert _call_tool("remove_event", {"show_id": 42}) == {
        "removed": True,
        "show_id": 42,
    }


def test_remove_event_refuses_scraped_rows_structurally(
    transport: _MockTransport,
) -> None:
    transport.responses[("DELETE", "/api/events/7")] = (
        403,
        {"detail": "only manually-entered events can be deleted"},
    )
    body = _call_tool("remove_event", {"show_id": 7})
    # 403 is the admin-gate status too, so the wrapper's sign-in hint wins —
    # the caller still gets something actionable, and the status is carried.
    assert body["status"] == 403


def test_set_event_type(transport: _MockTransport) -> None:
    transport.responses[("PUT", "/api/shows/9/event_type")] = {
        "show_id": 9,
        "event_type": "jam",
        "applies_to_billing": "tuesday session",
    }
    body = _call_tool("set_event_type", {"show_id": 9, "event_type": "jam"})
    assert body["applies_to_billing"] == "tuesday session"
    assert json.loads(transport.last.content) == {"event_type": "jam"}


def test_clear_event_type(transport: _MockTransport) -> None:
    transport.responses[("DELETE", "/api/shows/9/event_type")] = (204, None)
    assert _call_tool("clear_event_type", {"show_id": 9}) == {
        "cleared": True,
        "show_id": 9,
    }


def test_set_event_type_unknown_show_is_structured(transport: _MockTransport) -> None:
    transport.responses[("PUT", "/api/shows/999/event_type")] = (
        404,
        {"detail": "unknown show"},
    )
    body = _call_tool("set_event_type", {"show_id": 999, "event_type": "jam"})
    assert body == {"error": "unknown show", "status": 404}


# ----------------------------------------------------------- auth and errors


def test_no_cookie_is_sent_without_a_configured_session(
    transport: _MockTransport,
) -> None:
    transport.responses[("GET", "/api/shows")] = []
    _call_tool("list_shows", {})
    assert "cookie" not in transport.last.headers


def test_session_token_rides_as_a_cookie(
    transport: _MockTransport, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FOGHORN_MCP_SESSION", "tok123")
    transport.responses[("GET", "/api/watchlist")] = []
    _call_tool("get_watchlist", {})
    assert transport.last.headers["cookie"] == "foghorn_session=tok123"


def test_base_url_is_overridable(
    transport: _MockTransport, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FOGHORN_API_URL", "http://elsewhere:9999/")
    transport.responses[("GET", "/api/venues")] = []
    _call_tool("list_venues", {})
    assert str(transport.last.url) == "http://elsewhere:9999/api/venues"


def test_401_returns_the_actionable_sign_in_error(transport: _MockTransport) -> None:
    """The failure mode against a multi-user backend with no session: not a
    stack trace, and it names both ways out."""
    transport.responses[("GET", "/api/watchlist")] = (
        401,
        {"detail": "sign-in required"},
    )
    body = _call_tool("get_watchlist", {})
    assert body["status"] == 401
    assert "FOGHORN_MCP_SESSION" in body["error"]
    assert "FOGHORN_SINGLE_USER=1" in body["error"]


def test_403_names_the_admin_gate(transport: _MockTransport) -> None:
    transport.responses[("POST", "/api/events")] = (403, {"detail": "admin only"})
    body = _call_tool(
        "add_event",
        {
            "venue_slug": "bird_and_beckett",
            "headliner": "X",
            "date": "2026-09-04",
            "time": "19:30",
        },
    )
    assert body["status"] == 403
    assert "admin" in body["error"]


def test_browse_still_works_while_personal_tools_are_locked(
    transport: _MockTransport,
) -> None:
    """`/api/shows` and `/api/venues` are public, so an unauthenticated
    session degrades to browse rather than failing wholesale."""
    transport.responses[("GET", "/api/shows")] = [{"id": 1}]
    transport.responses[("GET", "/api/watchlist")] = (
        401,
        {"detail": "sign-in required"},
    )
    assert _call_tool("list_shows", {}) == [{"id": 1}]
    assert "error" in _call_tool("get_watchlist", {})


def test_unreachable_backend_is_reported_not_raised(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_client = httpx.Client

    def _client_factory(*args: Any, **kwargs: Any) -> httpx.Client:
        def _boom(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        kwargs["transport"] = httpx.MockTransport(_boom)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(mcp_server.httpx, "Client", _client_factory)
    monkeypatch.delenv("FOGHORN_API_URL", raising=False)
    body = _call_tool("list_shows", {})
    assert "cannot reach the foghorn API" in body["error"]
    assert mcp_server.DEFAULT_BASE_URL in body["error"]


def test_5xx_still_raises(transport: _MockTransport) -> None:
    """A server-side bug is not something the caller can act on — let it
    surface loudly rather than dressing it up as a structured result.
    FastMCP wraps the raise as a ToolError on the way out."""
    transport.responses[("GET", "/api/shows")] = (500, {"detail": "boom"})
    with pytest.raises(ToolError) as excinfo:
        _call_tool("list_shows", {})
    assert isinstance(excinfo.value.__cause__, httpx.HTTPStatusError)
