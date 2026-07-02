"""The ingest pipeline: scraper output → normalized, deduped, persisted rows.

This is the only layer that turns ``ScrapedShow`` records into DB state. It
normalizes performer names, resolves the venue tz to compute ``start_utc``,
upserts performers, and upserts each show on its natural key. A failure on one
show is captured in ``IngestResult.errors`` and doesn't abort the batch.
"""

from __future__ import annotations

import sqlite3
import unicodedata
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from foghorn.models import (
    IngestResult,
    Performer,
    ScrapedShow,
    Show,
    ShowPerformer,
    Venue,
)
from foghorn.repo import performers as performers_repo
from foghorn.repo import shows as shows_repo


def canonicalize(name: str) -> str:
    """Normalize a performer name for search / watchlist matching.

    Lowercase, NFKD-decompose and drop combining marks (so ``é`` → ``e``),
    replace every non-alphanumeric character with a space, and collapse runs of
    whitespace. Punctuation becomes a separator rather than vanishing, so
    ``"Earth, Wind & Fire"`` → ``"earth wind fire"`` rather than ``"earthwind
    fire"``.
    """
    decomposed = unicodedata.normalize("NFKD", name)
    without_marks = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    lowered = without_marks.lower()
    spaced = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in lowered)
    return " ".join(spaced.split())


def _to_show(venue: Venue, scraped: ScrapedShow, scraped_at: str) -> Show:
    """Build a persistable ``Show`` from a ``ScrapedShow``, applying the venue
    tz to the naive local times to derive ``start_utc``."""
    tz = ZoneInfo(venue.tz)
    start_local = scraped.start_local.replace(tzinfo=tz)
    assert venue.id is not None  # caller resolves the venue before ingest
    return Show(
        venue_id=venue.id,
        start_utc=start_local.astimezone(UTC).isoformat(),
        start_local_date=scraped.start_local.strftime("%Y-%m-%d"),
        start_local_time=scraped.start_local.strftime("%H:%M"),
        doors_local_time=(
            scraped.doors_local.strftime("%H:%M")
            if scraped.doors_local is not None
            else None
        ),
        headliner_canonical=canonicalize(scraped.headliner_raw),
        ticket_url=scraped.ticket_url,
        price_text=scraped.price_text,
        source_url=scraped.source_url,
        scraped_at=scraped_at,
    )


def _build_bill(
    conn: sqlite3.Connection, scraped: ScrapedShow
) -> list[ShowPerformer]:
    """Upsert the headliner (position 0) and support acts, returning the bill
    with persisted ``performer_id``s in display order."""
    bill: list[ShowPerformer] = []
    headliner = performers_repo.upsert(
        conn,
        Performer(
            display_name=scraped.headliner_raw,
            canonical_name=canonicalize(scraped.headliner_raw),
        ),
    )
    bill.append(
        ShowPerformer(
            performer_id=headliner.id,
            display_name=headliner.display_name,
            canonical_name=headliner.canonical_name,
            role="headliner",
            position=0,
        )
    )
    # Venues sometimes bill the same act twice (the headliner repeated in the
    # support list, or a placeholder like "TBA" filling several slots). The
    # show_performers PK is (show_id, performer_id), so keep only the first
    # occurrence of each performer — earliest billing position wins.
    seen_ids = {headliner.id}
    position = 1
    for support_raw in scraped.support_raw:
        support = performers_repo.upsert(
            conn,
            Performer(
                display_name=support_raw,
                canonical_name=canonicalize(support_raw),
            ),
        )
        if support.id in seen_ids:
            continue
        seen_ids.add(support.id)
        bill.append(
            ShowPerformer(
                performer_id=support.id,
                display_name=support.display_name,
                canonical_name=support.canonical_name,
                role="support",
                position=position,
            )
        )
        position += 1
    return bill


def ingest_scraped_shows(
    conn: sqlite3.Connection, venue: Venue, scraped: list[ScrapedShow]
) -> IngestResult:
    """Normalize, dedupe, and persist a venue's scraped shows.

    Counts a show as ``created`` if no row existed for its natural key,
    ``updated`` otherwise. Per-show failures land in ``errors`` and the batch
    continues.
    """
    result = IngestResult(venue_slug=venue.slug)
    scraped_at = datetime.now(UTC).isoformat()
    for record in scraped:
        try:
            show = _to_show(venue, record, scraped_at)
            existing = shows_repo.get_by_natural_key(
                conn,
                show.venue_id,
                show.start_local_date,
                show.start_local_time,
                show.headliner_canonical,
            )
            bill = _build_bill(conn, record)
            shows_repo.upsert(conn, show, bill)
            if existing is None:
                result.created += 1
            else:
                result.updated += 1
        except Exception as exc:
            # Isolate one malformed show so the rest of the batch still lands.
            result.errors.append(f"{record.headliner_raw} @ {record.start_local}: {exc}")
    return result
