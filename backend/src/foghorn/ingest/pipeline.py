"""The ingest pipeline: scraper output → normalized, deduped, persisted rows.

This is the only layer that turns ``ScrapedShow`` records into DB state. It
normalizes performer names, resolves the venue tz to compute ``start_utc``,
upserts performers, and upserts each show on its natural key. A failure on one
show is captured in ``IngestResult.errors`` and doesn't abort the batch.
"""

from __future__ import annotations

import re
import sqlite3
import unicodedata
from datetime import UTC, datetime
from typing import Literal
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


# Unambiguous jam-session title patterns. Deliberately narrow — "jam" alone
# would misfire on band names (Pearl Jam tributes, "Space Jam" parties; note
# "James" never matches: the s? is optional but the \b still requires the
# word to end) — a genre word or session/night/open framing is required.
# Open mics and organ-session residencies count: they're participatory,
# which is the thing a jam filter is for. Sources that KNOW can set
# ScrapedShow.event_type explicitly, which always wins over this.
_JAM_TITLE_RE = re.compile(
    r"\bjam\s+sessions?\b|\bopen\s+jams?\b|\bjam\s+nights?\b"
    r"|\b(?:blues|funk|jazz|soul|latin)\s+jams?\b"
    r"|\bopen\s+mic\b|\b(?:b3|organ)\s+sessions?\b",
    re.IGNORECASE,
)


def infer_event_type(scraped: ScrapedShow) -> Literal["show", "jam"]:
    """The scraper's explicit tag if set, else a conservative title check."""
    if scraped.event_type is not None:
        return scraped.event_type
    return "jam" if _JAM_TITLE_RE.search(scraped.headliner_raw) else "show"


# Source genre strings → the coarse genre vocabulary (Phase 7.2). Sources are
# free-text ("Rock / Indie", "Hip-Hop", "Soul/Funk"); first matching keyword
# wins, ordered so the more specific buckets are checked before "rock". Junk
# and catch-all values ("Other Content") normalize to None — the venue's
# default genre applies then.
_GENRE_KEYWORDS: list[tuple[str, str]] = [
    ("jazz", "jazz"),
    ("blues", "blues"),
    ("funk", "funk"),
    ("soul", "funk"),
    ("r&b", "funk"),
    ("disco", "funk"),
    ("hip-hop", "hip-hop"),
    ("hip hop", "hip-hop"),
    ("rap", "hip-hop"),
    ("electronic", "electronic"),
    ("techno", "electronic"),
    ("house", "electronic"),
    ("edm", "electronic"),
    ("dance", "electronic"),
    ("dj", "electronic"),
    ("folk", "folk"),
    ("country", "country"),
    ("americana", "country"),
    ("bluegrass", "folk"),
    ("latin", "latin"),
    ("salsa", "latin"),
    ("cumbia", "latin"),
    ("reggae", "world"),
    ("world", "world"),
    ("pop", "pop"),
    ("indie", "rock"),
    ("punk", "rock"),
    ("metal", "rock"),
    ("emo", "rock"),
    ("garage", "rock"),
    ("psych", "rock"),
    ("alternative", "rock"),
    ("rock", "rock"),
]


def normalize_genre(raw: str | None) -> str | None:
    """Map a source's free-text genre to the coarse vocabulary, or None when
    the string carries no usable signal."""
    if raw is None:
        return None
    lowered = raw.lower()
    for keyword, bucket in _GENRE_KEYWORDS:
        if keyword in lowered:
            return bucket
    return None


# Title words safe to read as a genre claim ("Motown on Mondays", "Brazilian
# Disco"). A subset of the source-genre table: word-boundary matched, and the
# ambiguous-in-a-title words are deliberately absent — "pop" (pop-up), "house"
# (House of...), "dance"/"rock" (verbs), "world", "country" (place sense).
_TITLE_GENRE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(rf"\b{kw}\b", re.IGNORECASE), bucket)
    for kw, bucket in [
        ("jazz", "jazz"),
        ("swing", "jazz"),
        ("bebop", "jazz"),
        ("blues", "blues"),
        ("funk", "funk"),
        ("soul", "funk"),
        ("disco", "funk"),
        ("motown", "funk"),
        ("boogie", "funk"),
        ("hip-hop", "hip-hop"),
        ("hip\\s+hop", "hip-hop"),
        ("techno", "electronic"),
        ("latin", "latin"),
        ("salsa", "latin"),
        ("cumbia", "latin"),
        ("reggae", "world"),
        ("bluegrass", "folk"),
        ("punk", "rock"),
        ("metal", "rock"),
    ]
]


def infer_genre_from_title(title: str) -> str | None:
    """A conservative genre read of the headliner text: fires only when the
    title names exactly one genre bucket ("Jazz/Latin Trio" is ambiguous →
    None). Used as the last layer of genre resolution, and only for shows
    that would otherwise resolve to nothing (no source genre, no real venue
    lean)."""
    buckets = {
        bucket for pattern, bucket in _TITLE_GENRE_PATTERNS if pattern.search(title)
    }
    return buckets.pop() if len(buckets) == 1 else None


def _to_show(
    venue: Venue,
    scraped: ScrapedShow,
    scraped_at: str,
    source: Literal["scrape", "manual"] = "scrape",
) -> Show:
    """Build a persistable ``Show`` from a ``ScrapedShow``, applying the venue
    tz to the naive local times to derive ``start_utc``."""
    tz = ZoneInfo(venue.tz)
    start_local = scraped.start_local.replace(tzinfo=tz)
    assert venue.id is not None  # caller resolves the venue before ingest
    # Scraper genre strings are held to the coarse vocabulary (junk → venue
    # default); a manual entry's genre is kept verbatim (lowercased) when it
    # doesn't map — the user meant what they typed.
    genre_override = normalize_genre(scraped.genre)
    if genre_override is None and source == "manual" and scraped.genre:
        genre_override = scraped.genre.strip().lower() or None
    # Last layer: when neither the source nor the venue says anything useful
    # ("Motown on Mondays" at an eclectic room), an unambiguous genre word in
    # the title fills the gap. Venues with a real lean are left alone — the
    # title heuristic shouldn't second-guess curation.
    if genre_override is None and venue.genre in (None, "eclectic"):
        genre_override = infer_genre_from_title(scraped.headliner_raw)
    return Show(
        source=source,
        event_type=infer_event_type(scraped),
        genre_override=genre_override,
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
    conn: sqlite3.Connection,
    venue: Venue,
    scraped: list[ScrapedShow],
    source: Literal["scrape", "manual"] = "scrape",
) -> IngestResult:
    """Normalize, dedupe, and persist a venue's scraped shows.

    Counts a show as ``created`` if no row existed for its natural key,
    ``updated`` otherwise. Per-show failures land in ``errors`` and the batch
    continues. ``source="manual"`` marks user-entered events (POST
    /api/events), which reuse this exact path — same normalization, same
    natural-key dedup — but stay deletable through the API.
    """
    result = IngestResult(venue_slug=venue.slug)
    scraped_at = datetime.now(UTC).isoformat()
    for record in scraped:
        try:
            show = _to_show(venue, record, scraped_at, source)
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
