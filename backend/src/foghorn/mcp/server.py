"""FastMCP server that exposes foghorn's calendar conversationally.

A **thin httpx wrapper over the running FastAPI**, not a second path into the
repo layer — that keeps one authorization story (the API's) and means the MCP
surface can never drift from REST semantics. Run the backend first; the
default base URL is fleet's always-on ``foghorn-api`` on :8100.

Auth rides the deployment. Under ``FOGHORN_SINGLE_USER=1`` (how fleet runs)
the backend resolves cookie-less requests to the bootstrap admin, so the
personal endpoints *and* the admin-only writes work with zero configuration.
``FOGHORN_MCP_SESSION`` is the escape hatch for a multi-user backend: set it
to a ``foghorn_session`` token and every request carries that cookie. With
neither, browse still works (``/api/shows`` and ``/api/venues`` are public)
and the personal/admin tools return a structured, actionable sign-in error
rather than a stack trace.

Vocabularies (``region``, ``origin``, ``type``) are *imported* from
``foghorn.models`` rather than hand-copied — ficycle's scar tissue is a copied
category Literal that drifted five values behind and silently blocked MCP
writes for those values. ``tests/mcp/test_literal_drift.py`` pins the
published tool schemas to those canonical sources so adding a fourth event
type fails the gate here instead of quietly becoming unreachable over MCP.
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

import httpx
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from foghorn.models import EventType, Origin, Region

# fleet's foghorn-api. Deliberately not 8000 (that's ficycle-api's fleet port)
# and not 9100 (foghorn's own dev-run port) — 8100 is the always-on one.
DEFAULT_BASE_URL = "http://127.0.0.1:8100"

SESSION_COOKIE = "foghorn_session"

TimeOfDay = Literal["early", "late"]

_SIGN_IN_HINT = (
    "set FOGHORN_MCP_SESSION to a foghorn_session token, or run the backend "
    "with FOGHORN_SINGLE_USER=1"
)


class NewVenueArg(BaseModel):
    """A venue foghorn doesn't track yet. Mirrors ``api.events.NewVenue``.

    Deliberately re-declared instead of imported: importing anything under
    ``foghorn.api`` executes ``foghorn/api/__init__.py``, which builds the
    whole FastAPI app (routers, CORS, scheduler import) inside what is meant
    to be a thin stdio client. ``tests/mcp/test_literal_drift.py`` pins these
    fields to the real request model so the two can't drift apart.
    """

    name: str = Field(min_length=1, description="venue name, e.g. 'Bird & Beckett'")
    neighborhood: str | None = None
    region: Region | None = None
    address: str | None = None
    website_url: str | None = None
    genre: str | None = None


@dataclass(frozen=True)
class _Failure:
    """A handled 4xx. Carried rather than raised so each tool can decide
    whether to dump it verbatim or substitute a success envelope."""

    payload: dict[str, Any]


def _base_url() -> str:
    return os.environ.get("FOGHORN_API_URL", DEFAULT_BASE_URL).rstrip("/")


def _headers() -> dict[str, str]:
    """No credential by default — single-user mode resolves cookie-less
    requests to the bootstrap admin. A token in FOGHORN_MCP_SESSION rides
    along as the session cookie for multi-user backends."""
    token = os.environ.get("FOGHORN_MCP_SESSION")
    return {"Cookie": f"{SESSION_COOKIE}={token}"} if token else {}


def _detail(response: httpx.Response) -> Any:
    try:
        body = response.json()
    except ValueError:
        return response.text or response.reason_phrase
    return body.get("detail", body) if isinstance(body, dict) else body


def _request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
) -> Any | _Failure:
    """One outbound call. 4xx comes back as a ``_Failure`` so callers can
    branch without parsing exception text; 5xx still raises (server bug)."""
    url = f"{_base_url()}{path}"
    try:
        with httpx.Client(timeout=30.0, headers=_headers()) as client:
            response = client.request(method, url, params=params, json=payload)
    except httpx.RequestError as exc:
        return _Failure(
            {
                "error": (
                    f"cannot reach the foghorn API at {_base_url()} ({exc.__class__.__name__}) "
                    "— start the backend, or point FOGHORN_API_URL somewhere else"
                )
            }
        )
    if response.status_code == 401:
        return _Failure({"error": f"sign-in required: {_SIGN_IN_HINT}", "status": 401})
    if response.status_code == 403:
        return _Failure(
            {
                "error": (
                    f"admin only — the resolved user is not an admin: {_SIGN_IN_HINT} "
                    "(the token must belong to an admin)"
                ),
                "status": 403,
            }
        )
    if 400 <= response.status_code < 500:
        return _Failure({"error": _detail(response), "status": response.status_code})
    response.raise_for_status()
    if not response.content:
        return None
    return response.json()


def _get_json(path: str, params: dict[str, Any] | None = None) -> Any | _Failure:
    return _request("GET", path, params=params)


def _post_json(path: str, payload: dict[str, Any]) -> Any | _Failure:
    return _request("POST", path, payload=payload)


def _put_json(path: str, payload: dict[str, Any]) -> Any | _Failure:
    return _request("PUT", path, payload=payload)


def _delete_json(path: str) -> Any | _Failure:
    return _request("DELETE", path)


def _dump(value: Any) -> str:
    return json.dumps(value, indent=2, default=str)


def _csv(value: str | Sequence[str] | None) -> str | None:
    """Multi-value facets go over the wire comma-separated. Tools accept
    either a bare value ("SF") or a list (["SF", "East Bay"])."""
    if value is None:
        return None
    if isinstance(value, str):
        return value or None
    return ",".join(value) or None


def _flag(value: bool) -> str | None:
    """The API reads these as the literal string 'true'; omit when false so
    an unset flag never looks like an explicit opt-out."""
    return "true" if value else None


def _params(**kwargs: Any) -> dict[str, Any]:
    return {key: value for key, value in kwargs.items() if value is not None}


def build_server() -> FastMCP:
    mcp = FastMCP(
        name="foghorn",
        instructions=(
            "foghorn is a Bay Area live-music calendar: venue calendars scraped "
            "nightly, filtered by date, region, neighborhood, genre, performer "
            "origin, and event type, plus a personal performer watchlist and "
            "venue watchlist. "
            "Browsing (list_shows, list_venues) is public. The watchlist and "
            "venue-watchlist tools are per-user. Adding/removing events and "
            "setting event-type overrides are admin-only and write global data "
            "every user sees — confirm with the user before calling any write "
            "tool. "
            "Venue slugs are the currency of list_shows and add_event; call "
            "list_venues to discover them. Vocabularies: region is one of SF, "
            "East Bay, North Bay, Peninsula, South Bay, Santa Cruz; origin is "
            "local or touring; type is show, jam, or comedy; time_of_day is "
            "early or late. Multi-value facets OR within a facet and AND across "
            "facets. Genres and neighborhoods are open vocabularies — read them "
            "off list_venues rather than guessing."
        ),
    )

    # ---------------------------------------------------------------- reads

    @mcp.tool(
        name="list_shows",
        description=(
            "Upcoming shows, chronological, across every facet the web UI "
            "exposes. Defaults to today through today+30 days; pass to='all' "
            "to lift the upper bound. Multi-value facets (venues, region, "
            "neighborhood, genre, origin, type) accept a single value or a "
            "list — OR within a facet, AND across facets. Dates are ISO "
            "(YYYY-MM-DD) in the venue's local time. Rows carry the venue "
            "(with neighborhood/region), headliner and support (display + "
            "canonical names, each with local/touring origin), start/doors "
            "times, room for multi-room venues, ticket_url, price_text, and "
            "source_url provenance. watchlist / venue_watchlist need a "
            "signed-in user; long_tail includes aggregator-discovered venues "
            "that are hidden from the main UI by default. limit defaults to "
            "50 (a chronological prefix, not a relevance ranking)."
        ),
    )
    def list_shows(
        venues: str | list[str] | None = None,
        from_: str | None = None,
        to: str | None = None,
        time_of_day: TimeOfDay | None = None,
        performer_query: str | None = None,
        region: Region | list[Region] | None = None,
        neighborhood: str | list[str] | None = None,
        genre: str | list[str] | None = None,
        origin: Origin | list[Origin] | None = None,
        type: EventType | list[EventType] | None = None,
        watchlist: bool = False,
        venue_watchlist: bool = False,
        long_tail: bool = False,
        limit: int = 50,
    ) -> str:
        # `from` is a Python keyword, so the parameter carries the same
        # trailing-underscore spelling api/shows.py uses for its own alias.
        params = _params(
            venues=_csv(venues),
            **{"from": from_},
            to=to,
            time_of_day=time_of_day,
            performer_query=performer_query,
            region=_csv(region),
            neighborhood=_csv(neighborhood),
            genre=_csv(genre),
            origin=_csv(origin),
            type=_csv(type),
            watchlist=_flag(watchlist),
            venue_watchlist=_flag(venue_watchlist),
            long_tail=_flag(long_tail),
            limit=limit,
        )
        result = _get_json("/api/shows", params)
        return _dump(result.payload if isinstance(result, _Failure) else result)

    @mcp.tool(
        name="list_venues",
        description=(
            "Every venue foghorn tracks: slug, name, neighborhood, region, "
            "default genre lean, and source ('seed' = scraped, 'manual' = "
            "hand-entered, 'aggregator' = long-tail, hidden from the main UI "
            "unless long_tail is on). Slugs here are what list_shows(venues=) "
            "and add_event(venue_slug=) expect — call this first rather than "
            "guessing a slug. Public; no sign-in needed."
        ),
    )
    def list_venues() -> str:
        result = _get_json("/api/venues")
        return _dump(result.payload if isinstance(result, _Failure) else result)

    @mcp.tool(
        name="get_watchlist",
        description=(
            "The signed-in user's followed performers: canonical_name (the "
            "match key), display_name, added_at, notes. Matching is token-bag, "
            "so 'Joshua Redman' matches 'Joshua Redman Quartet'. Needs a "
            "signed-in user."
        ),
    )
    def get_watchlist() -> str:
        result = _get_json("/api/watchlist")
        return _dump(result.payload if isinstance(result, _Failure) else result)

    @mcp.tool(
        name="list_watched_venues",
        description=(
            "The signed-in user's followed venues: venue_slug, name, added_at, "
            "notes. Pair with list_shows(venue_watchlist=True) for their "
            "upcoming shows. Needs a signed-in user."
        ),
    )
    def list_watched_venues() -> str:
        result = _get_json("/api/venues/watchlist")
        return _dump(result.payload if isinstance(result, _Failure) else result)

    @mcp.tool(
        name="get_watchlist_digest",
        description=(
            "The next upcoming watchlist matches, chronological — the direct "
            "answer to 'what's coming up for people I follow'. Unlike "
            "list_shows(watchlist=True), each row carries watchlist_matches: "
            "which followed name(s) actually hit. With include_venues=True, "
            "shows at watched venues are merged in and flagged watched_venue "
            "(a row contributed only by its venue has an empty "
            "watchlist_matches). days is the look-ahead window (1-365, default "
            "14); limit caps matches (1-200, default 20). Needs a signed-in "
            "user."
        ),
    )
    def get_watchlist_digest(
        days: int = 14, limit: int = 20, include_venues: bool = False
    ) -> str:
        result = _get_json(
            "/api/watchlist/digest",
            _params(days=days, limit=limit, include_venues=_flag(include_venues)),
        )
        return _dump(result.payload if isinstance(result, _Failure) else result)

    # --------------------------------------------------------------- writes

    @mcp.tool(
        name="add_watchlist_performer",
        description=(
            "Follow a performer by name. WRITE — confirm with the user first. "
            "Idempotent on the canonical form: re-adding an existing canonical "
            "name keeps the original display_name and added_at and comes back "
            "with created=false. already_covered_by names a broader entry "
            "already on the list that matches everything this one would "
            "('Christian McBride' covers 'Christian McBride's Ursa Major') — "
            "the entry is still added, this only reports. A name that "
            "canonicalizes to nothing (punctuation only) comes back as "
            '{\"error\": detail}. Needs a signed-in user.'
        ),
    )
    def add_watchlist_performer(display_name: str, notes: str | None = None) -> str:
        result = _post_json(
            "/api/watchlist", _params(display_name=display_name, notes=notes)
        )
        return _dump(result.payload if isinstance(result, _Failure) else result)

    @mcp.tool(
        name="remove_watchlist_performer",
        description=(
            "Unfollow a performer by their canonical_name (the match key from "
            'get_watchlist, not the display name). WRITE — confirm with the '
            'user first. A name that isn\'t on the list comes back as '
            '{"error": "not on watchlist"}. Needs a signed-in user.'
        ),
    )
    def remove_watchlist_performer(canonical_name: str) -> str:
        result = _delete_json(f"/api/watchlist/{canonical_name}")
        if isinstance(result, _Failure):
            return _dump(result.payload)
        return _dump({"removed": True, "canonical_name": canonical_name})

    @mcp.tool(
        name="watch_venue",
        description=(
            "Follow a venue by slug (from list_venues). WRITE — confirm with "
            'the user first. An unknown slug comes back as {"error": "unknown '
            'venue slug"}. Needs a signed-in user.'
        ),
    )
    def watch_venue(venue_slug: str, notes: str | None = None) -> str:
        result = _post_json(
            "/api/venues/watchlist", _params(venue_slug=venue_slug, notes=notes)
        )
        return _dump(result.payload if isinstance(result, _Failure) else result)

    @mcp.tool(
        name="unwatch_venue",
        description=(
            "Unfollow a venue by slug. WRITE — confirm with the user first. A "
            'venue that isn\'t watched comes back as {"error": "venue not '
            'watched"}. Needs a signed-in user.'
        ),
    )
    def unwatch_venue(venue_slug: str) -> str:
        result = _delete_json(f"/api/venues/watchlist/{venue_slug}")
        if isinstance(result, _Failure):
            return _dump(result.payload)
        return _dump({"removed": True, "venue_slug": venue_slug})

    @mcp.tool(
        name="add_event",
        description=(
            "Hand-enter a show foghorn's scrapers don't cover (house concerts, "
            "Instagram-only calendars, a jam someone told you about). WRITE, "
            "ADMIN-ONLY, and global — every user sees the row. Confirm with "
            "the user first. Provide exactly one of venue_slug (an existing "
            "slug from list_venues) or venue (a NewVenueArg object for a room "
            "foghorn doesn't track yet, which is created as a manual venue); "
            "passing both or neither is a 422. date is ISO YYYY-MM-DD and "
            "time / doors_time are HH:MM, both in the venue's local time. The "
            "row rides the same normalization and natural-key dedup as scraped "
            "shows, so re-adding the same billing at the same venue and time "
            "is idempotent. Returns the stored id — keep it for remove_event. "
            'Rejections come back as {"error": detail}.'
        ),
    )
    def add_event(
        headliner: str,
        date: str,
        time: str,
        venue_slug: str | None = None,
        venue: NewVenueArg | None = None,
        support: list[str] | None = None,
        doors_time: str | None = None,
        ticket_url: str | None = None,
        price_text: str | None = None,
        event_type: EventType = "show",
        genre: str | None = None,
        source_url: str | None = None,
    ) -> str:
        payload = _params(
            venue_slug=venue_slug,
            venue=venue.model_dump(exclude_none=True) if venue is not None else None,
            headliner=headliner,
            support=support,
            date=date,
            time=time,
            doors_time=doors_time,
            ticket_url=ticket_url,
            price_text=price_text,
            event_type=event_type,
            genre=genre,
            source_url=source_url,
        )
        result = _post_json("/api/events", payload)
        return _dump(result.payload if isinstance(result, _Failure) else result)

    @mcp.tool(
        name="remove_event",
        description=(
            "Delete a hand-entered event by show id. WRITE, ADMIN-ONLY — "
            "confirm with the user first. Only manual rows can be deleted; a "
            "scraped show comes back as a 403-style error, because it would "
            "reappear on the next nightly refresh anyway."
        ),
    )
    def remove_event(show_id: int) -> str:
        result = _delete_json(f"/api/events/{show_id}")
        if isinstance(result, _Failure):
            return _dump(result.payload)
        return _dump({"removed": True, "show_id": show_id})

    @mcp.tool(
        name="set_event_type",
        description=(
            "Correct what kind of event a billing is ('this Tuesday thing is a "
            "jam, not a show'). WRITE, ADMIN-ONLY — confirm with the user "
            "first. BROADER THAN THE SHOW YOU NAME: this stores a "
            "venue+billing override rule, not a single-row edit, so it "
            "survives re-ingest and applies to every past and future instance "
            "of that recurring billing at that venue. An unknown show_id comes "
            'back as {"error": "unknown show"}.'
        ),
    )
    def set_event_type(show_id: int, event_type: EventType) -> str:
        result = _put_json(
            f"/api/shows/{show_id}/event_type", {"event_type": event_type}
        )
        return _dump(result.payload if isinstance(result, _Failure) else result)

    @mcp.tool(
        name="clear_event_type",
        description=(
            "Drop the manual event-type override for a billing, so ingest's "
            "inferred type applies again. WRITE, ADMIN-ONLY — confirm with the "
            "user first. Like set_event_type, this clears the venue+billing "
            "rule, affecting every instance of the recurring billing."
        ),
    )
    def clear_event_type(show_id: int) -> str:
        result = _delete_json(f"/api/shows/{show_id}/event_type")
        if isinstance(result, _Failure):
            return _dump(result.payload)
        return _dump({"cleared": True, "show_id": show_id})

    return mcp


def main() -> None:
    build_server().run()


if __name__ == "__main__":
    main()
