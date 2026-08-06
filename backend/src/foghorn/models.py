"""Shared domain + transport models for foghorn.

Everything that crosses a layer boundary is a Pydantic model defined here, so
the repo, ingest, scraper, and (later) API layers all agree on shapes without
importing each other. Persisted rows are exposed through these models — callers
never touch raw ``sqlite3.Row`` objects.

See ``AGENTS.md`` → "Conventions" for the rules these encode: the show natural
key, UTC-plus-local time storage, and the display-vs-canonical performer split.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Closed enumerations stored as TEXT. Kept as Literals so seeds and ingest are
# validated at construction time rather than silently writing typos to the DB.
Region = Literal["SF", "East Bay", "North Bay", "Peninsula", "South Bay", "Santa Cruz"]
Role = Literal["headliner", "support"]
# Performer origin (v1 of local/touring tagging). No scraped source publishes
# this — it's inferred (heuristic bootstrap) or hand-set; None = unknown.
# "regional" (touring-the-West-Coast-but-Bay-based) deferred until the two-way
# split proves too coarse.
Origin = Literal["local", "touring"]
OriginSource = Literal["heuristic", "manual"]
# Event type: a jam session is a different thing to plan around than a show
# (you might bring your horn). Scrapers/manual entry can set it explicitly;
# ingest infers it from unambiguous title patterns otherwise.
EventType = Literal["show", "jam"]


class Venue(BaseModel):
    """A music venue. ``id`` is ``None`` until persisted."""

    id: int | None = None
    slug: str
    name: str
    neighborhood: str | None = None
    region: Region | None = None
    address: str | None = None
    tz: str  # IANA, e.g. "America/Los_Angeles"
    website_url: str | None = None
    calendar_url: str
    # Venue-default genre (Phase 7.1): the coarse booking lean ("jazz", "rock",
    # "funk", "eclectic"). Kept TEXT-loose rather than a Literal so adding a
    # value is a seed edit, not a schema change; a per-show override is a later
    # phase (7.2).
    genre: str | None = None
    # "seed" = from seed_venues (scraped or planned); "manual" = created by
    # the user through POST /api/events; "aggregator" = auto-created by an
    # aggregator ingest (quarantined from the main UI behind the long-tail
    # toggle; pinning promotes — see repo/shows quarantine clause).
    source: Literal["seed", "manual", "aggregator"] = "seed"


class Performer(BaseModel):
    """A performer. ``canonical_name`` is the normalized search/match key;
    ``display_name`` is the venue's verbatim string and is never overwritten."""

    id: int | None = None
    display_name: str
    canonical_name: str
    # Local/touring tag. origin_source records who set it: the heuristic
    # bootstrap never overwrites a "manual" row.
    origin: Origin | None = None
    origin_source: OriginSource | None = None
    # Performer-level genre (Phase 7.4, deterministic stage). Sits between
    # the per-show override and the venue default in genre resolution.
    # genre_source mirrors origin_source ("heuristic" | "manual").
    genre: str | None = None
    genre_source: OriginSource | None = None


class ShowPerformer(BaseModel):
    """One performer's slot on a show's bill (the ``show_performers`` join row,
    denormalized with the performer's names for convenient read-back)."""

    performer_id: int | None = None
    display_name: str
    canonical_name: str
    role: Role
    position: int  # display order on the bill; headliner is 0
    origin: Origin | None = None  # denormalized from performers for read-back
    genre: str | None = None  # denormalized performer genre (Phase 7.4)


class Show(BaseModel):
    """A persisted show. Times are stored as both UTC (for ordering across
    venues / future multi-tz) and venue-local date+time (for natural-key dedup
    and display). ``performers`` is populated by the read paths, empty on the
    objects handed to ``shows.upsert``."""

    id: int | None = None
    venue_id: int
    start_utc: str  # ISO 8601, always normalized to +00:00
    start_local_date: str  # YYYY-MM-DD in the venue's tz
    start_local_time: str  # HH:MM in the venue's tz
    # Stated end (HH:MM), when the source publishes one; earlier than start
    # = past midnight.
    end_local_time: str | None = None
    doors_local_time: str | None = None  # HH:MM in the venue's tz
    headliner_canonical: str
    ticket_url: str | None = None
    price_text: str | None = None
    source_url: str
    scraped_at: str  # ISO 8601 UTC
    # "scrape" = written by the ingest pipeline from a venue scraper;
    # "manual" = user-entered via POST /api/events (deletable through the
    # API); "aggregator" = ingested from an aggregator source.
    source: Literal["scrape", "manual", "aggregator"] = "scrape"
    event_type: EventType = "show"
    # Per-show genre (Phase 7.2), normalized at ingest from sources that
    # publish per-event genre. Genre resolution is layered: this override
    # wins, else the venue's default genre. None = no per-show signal.
    genre_override: str | None = None
    performers: list[ShowPerformer] = Field(default_factory=list)


class ScrapedShow(BaseModel):
    """The scraper output contract. Frozen: a scraper produces these and hands
    them to the ingest pipeline, which is the only thing that touches the DB.

    ``start_local`` / ``doors_local`` are *naive* datetimes — the venue's tz is
    applied at ingest, not by the scraper."""

    model_config = ConfigDict(frozen=True)

    venue_slug: str
    headliner_raw: str
    support_raw: list[str] = Field(default_factory=list)
    start_local: datetime
    # Stated end, when the source publishes one (Tribe end_date, Viewcy
    # ends_at, flyer "7-11pm" ranges…). None = not stated; the day-grid UI
    # falls back to a nominal set length. An end clock-time earlier than the
    # start means past-midnight ("9:30pm - 2:00am").
    end_local: datetime | None = None
    doors_local: datetime | None = None
    ticket_url: str | None = None
    price_text: str | None = None
    source_url: str
    # None = not stated by the source; ingest then infers from unambiguous
    # title patterns ("jam session", "open jam", …). An explicit value wins.
    event_type: EventType | None = None
    # The source's verbatim per-event genre string, when it publishes one
    # (SeeTickets cards, Dice tags, …). Normalized to the coarse vocabulary at
    # ingest; junk values normalize to None (venue default applies).
    genre: str | None = None


class ShowFilters(BaseModel):
    """Query filters for ``shows.list``. All optional; omitted filters don't
    constrain. Date filters compare against ``start_local_date`` (the day the
    show happens in the venue's tz), inclusive on both ends."""

    venue_slugs: list[str] | None = None
    from_date: str | None = None  # YYYY-MM-DD, inclusive
    to_date: str | None = None  # YYYY-MM-DD, inclusive
    # Canonicalized free-text query; whole-token matched against any performer
    # (Phase 4.1 upgraded this from substring to token-bag matching).
    performer_query_canonical: str | None = None
    # Watchlist filter: each inner list is one entry's canonical tokens. A show
    # matches if any performer token-matches any bag. Empty list = no matches
    # (empty watchlist), None = filter not requested.
    watchlist_token_bags: list[list[str]] | None = None
    region: Region | None = None
    neighborhood: str | None = None  # case-insensitive exact match on venue
    # Case-insensitive exact match on the show's *resolved* genre:
    # COALESCE(show.genre_override, venue.genre).
    genre: str | None = None
    # A show matches if ANY performer on the bill carries this origin tag
    # (same any-performer semantics as the watchlist filter).
    origin: Origin | None = None
    event_type: EventType | None = None  # None = both shows and jams
    # Venue watchlist filter (Phase 9): shows at any of these venue slugs.
    # Empty list = no matches (empty watchlist); None = filter not requested.
    watched_venue_slugs: list[str] | None = None
    # Long-tail toggle (aggregator quarantine): False hides shows at
    # aggregator-created venues unless the venue is pinned (watched_venues),
    # explicitly selected, or the performer-watchlist filter is active —
    # the watchlist always sees through the quarantine.
    include_long_tail: bool = False
    # Whose pins count for the quarantine pin-promotion above. None (anonymous
    # request) = no pin exemption. Per-user since the multi-user re-key.
    user_id: int | None = None
    # "early" = start_local_time < 21:00; "late" = >= 21:00 (exact complements).
    time_of_day: Literal["early", "late"] | None = None
    # Cap the result count (chronological prefix). None = no cap. Used by the
    # frontend list view's load-more pagination; other filters are unaffected.
    limit: int | None = None


class IngestResult(BaseModel):
    """Per-venue outcome of an ingest run. ``errors`` holds one message per
    show that failed to ingest, so a partial failure doesn't abort the batch."""

    venue_slug: str
    created: int = 0
    updated: int = 0
    # Stale scraped rows deleted because the venue no longer lists them
    # (retitled / rescheduled / cancelled). Only non-zero when the caller
    # opts into pruning — see ``ingest_scraped_shows(prune=True)``.
    reaped: int = 0
    errors: list[str] = Field(default_factory=list)


class ScrapeRunVenue(BaseModel):
    """One venue's slice of a scrape run — what the scheduler/`make scrape`
    recorded for it (mirrors the ``scrape_run_venues`` row)."""

    venue_slug: str
    started_at: str  # ISO 8601 UTC
    finished_at: str  # ISO 8601 UTC
    created: int = 0
    updated: int = 0
    errors: list[str] = Field(default_factory=list)


class ScrapeRun(BaseModel):
    """A single refresh of all registered scrapers — scheduled (04:00 PT) or
    manual (`make scrape`). ``GET /api/health/scrape`` returns the latest one."""

    id: int | None = None
    started_at: str  # ISO 8601 UTC
    finished_at: str  # ISO 8601 UTC
    venues: list[ScrapeRunVenue] = Field(default_factory=list)


class WatchedVenue(BaseModel):
    """A venue the user follows (Phase 9). Single-tenant, keyed on slug."""

    venue_slug: str
    added_at: str  # ISO 8601 UTC
    notes: str | None = None


class MailSender(BaseModel):
    """A mailing-list sender foghorn knows (Phase 8): the newsletter's From:
    address mapped to the artist it announces. artist ≈ headliner for the
    solo-project mailing lists this targets; the review queue is where that
    assumption gets corrected when a list announces someone else's gig."""

    email: str  # stored lowercased — the lookup key
    artist_display: str


# Review-queue lifecycle: rows are born 'pending'; approving creates the
# manual event and stamps 'approved'; 'rejected' keeps the row (with its raw
# text) as a record that a human looked and said no.
PendingStatus = Literal["pending", "approved", "rejected"]


class PendingEvent(BaseModel):
    """One ingested mailing-list email awaiting review (Phase 8). The draft
    fields are deterministic parser guesses — any of them may be None; the
    verbatim ``raw_text`` always survives so the reviewer can fill gaps."""

    id: int | None = None
    received_at: str  # ISO 8601 UTC
    from_addr: str
    subject: str
    # RFC 5322 Message-ID — the IMAP idempotency key. None for pasted emails.
    message_id: str | None = None
    raw_text: str
    artist_display: str | None = None  # from the sender map
    venue_slug: str | None = None  # a known venue found in the text
    venue_name_guess: str | None = None  # that venue's display name
    date_guess: str | None = None  # YYYY-MM-DD
    time_guess: str | None = None  # HH:MM (24h)
    status: PendingStatus = "pending"


class Watchlist(BaseModel):
    """A performer a user follows. ``canonical_name`` (the canonicalized
    ``display_name``) is the match key; ``display_name`` is the verbatim
    string the user added, kept for the UI. Keyed per-user since the
    multi-user re-key (August 2026)."""

    canonical_name: str
    display_name: str
    added_at: str  # ISO 8601 UTC
    notes: str | None = None


class User(BaseModel):
    """An account (August 2026). Created at invite time; ``invite_token`` is
    both the invite and the durable login credential (the "keep this link"
    model), so ``claimed_at`` merely records first use. ``email`` is optional
    and only collected to enable magic-link recovery later."""

    id: int | None = None
    display_name: str
    email: str | None = None
    invite_token: str
    is_admin: bool = False
    disabled: bool = False
    created_at: str  # ISO 8601 UTC
    claimed_at: str | None = None
