"""Pins the MCP tool schemas to the canonical vocabularies.

An MCP client validates arguments against the published tool schema, so a
vocabulary that drifts behind the codebase silently blocks calls for the
missing values — ficycle lost five cash-flow categories that way, accepted by
the HTTP API and rejected client-side by MCP.

`foghorn.mcp.server` imports its Literals from `foghorn.models` rather than
copying them, which removes most of that risk. These tests keep the *published
schema* honest, which is the part an import alone doesn't guarantee: retyping
a parameter as a bare `str` would drop the enum from the schema without
breaking anything the type checker looks at.
"""

from __future__ import annotations

import asyncio
from typing import Any, get_args

from foghorn.api import events as events_api
from foghorn.mcp import server as mcp_server
from foghorn.models import EventType, Origin, Region
from foghorn.repo.seed_venues import SEED_VENUES


def _tool_schema(tool_name: str) -> dict[str, Any]:
    tools = asyncio.run(mcp_server.build_server().list_tools())
    return {tool.name: tool for tool in tools}[tool_name].inputSchema


def _property_enum(tool_name: str, prop: str) -> set[str]:
    """Every enum value reachable from one tool parameter's schema.

    The parameter may be a bare enum, an `anyOf` union (the
    `Region | list[Region] | None` shape), an array whose items are the enum,
    or a `$ref` into `$defs` (how pydantic emits a nested model). Returns an
    empty set when the schema carries no enum constraint at all — the
    regression these tests exist to catch, since a parameter retyped as a
    bare `str` still type-checks and still works over HTTP.
    """
    schema = _tool_schema(tool_name)
    defs = schema.get("$defs", {})
    found: set[str] = set()
    seen_refs: set[str] = set()

    def _walk(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                _walk(item)
            return
        if not isinstance(node, dict):
            return
        ref = node.get("$ref")
        if isinstance(ref, str) and ref not in seen_refs:
            seen_refs.add(ref)
            _walk(defs.get(ref.rsplit("/", 1)[-1]))
        if "enum" in node:
            found.update(node["enum"])
        for key in ("anyOf", "oneOf", "allOf", "items"):
            if key in node:
                _walk(node[key])
        if "properties" in node:
            _walk(list(node["properties"].values()))

    _walk(schema["properties"][prop])
    return found


def test_list_shows_type_enum_matches_event_type() -> None:
    """`comedy` only arrived in #113. A fourth event type must fail here
    rather than becoming quietly unreachable over MCP."""
    assert _property_enum("list_shows", "type") == set(get_args(EventType))


def test_add_event_event_type_enum_matches_event_type() -> None:
    assert _property_enum("add_event", "event_type") == set(get_args(EventType))


def test_set_event_type_enum_matches_event_type() -> None:
    assert _property_enum("set_event_type", "event_type") == set(get_args(EventType))


def test_list_shows_origin_enum_matches_origin() -> None:
    assert _property_enum("list_shows", "origin") == set(get_args(Origin))


def test_list_shows_region_enum_matches_region() -> None:
    assert _property_enum("list_shows", "region") == set(get_args(Region))


def test_list_shows_time_of_day_enum_matches_the_api() -> None:
    assert _property_enum("list_shows", "time_of_day") == set(
        get_args(mcp_server.TimeOfDay)
    )
    assert set(get_args(mcp_server.TimeOfDay)) == {"early", "late"}


def test_seeded_regions_are_all_reachable_over_mcp() -> None:
    """The region facet is only useful if every region foghorn actually
    seeds is expressible — a new region added to the seed set without
    widening `models.Region` would fail here."""
    seeded = {venue.region for venue in SEED_VENUES if venue.region is not None}
    assert seeded <= _property_enum("list_shows", "region")


def test_new_venue_arg_matches_the_api_request_model() -> None:
    """`NewVenueArg` is re-declared rather than imported (importing anything
    under `foghorn.api` builds the whole FastAPI app). This is the price of
    that: the two field sets must stay identical."""
    assert set(mcp_server.NewVenueArg.model_fields) == set(
        events_api.NewVenue.model_fields
    )
    assert _property_enum("add_event", "venue") == set(get_args(Region))
