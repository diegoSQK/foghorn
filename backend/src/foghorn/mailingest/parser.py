"""Deterministic email → draft-fields parser (Phase 8 stage 1).

Pure: ``parse_email`` takes the email's parts plus the known-venue list, the
sender→artist map, and ``today`` (injected so date resolution is testable),
and returns best-effort draft guesses. Every rule is allowed to fumble — a
field it can't read stays ``None`` and the review queue still gets the raw
text. Nothing here writes to the DB or the network.

Rules:

- **artist** — the sender map keyed on the From: address (``Name <addr>``
  forms are unwrapped, matching is case-insensitive).
- **venue** — scan subject+body for a known venue's name, canonicalized on
  both sides so punctuation/case don't matter ("Make-Out Room" matches
  "make out room"); a leading "The " on the venue name is optional; the
  longest match wins ("Keys Jazz Bistro" beats a hypothetical "Keys").
- **date** — "Thursday July 16", "July 16th", "7/16", "7/16/26", ISO, and
  tonight/today/tomorrow; month/day without a year resolves to the next
  occurrence on-or-after ``today``. The earliest mention in the text wins.
- **time** — "8pm" / "8:30 PM" first; else a bare "7:30" (read as evening);
  else "doors 7" (read as 7pm — stage 1 doesn't distinguish doors from
  downbeat).
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Mapping, Sequence
from email.utils import parseaddr

from pydantic import BaseModel

from foghorn.ingest.pipeline import canonicalize
from foghorn.models import Venue


class ParsedDraft(BaseModel):
    """The parser's best-effort guesses — the draft columns of a
    ``pending_events`` row. Any field may be None."""

    artist_display: str | None = None
    venue_slug: str | None = None
    venue_name_guess: str | None = None
    date_guess: str | None = None  # YYYY-MM-DD
    time_guess: str | None = None  # HH:MM (24h)


# --- date -------------------------------------------------------------------

# Month names: full or the standard 3-letter abbreviation (optionally dotted).
# Bounded alternatives rather than a greedy [a-z]* so "Marina 8" doesn't read
# as March 8.
_MONTH_PATTERN = (
    r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?"
    r"|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
)
_MONTH_NUMBERS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}  # fmt: skip

_ISO_RE = re.compile(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b")
# "July 16", "July 16th", "Sept. 5" — an optional ordinal suffix, and a \b so
# "July 16th2" can't half-match.
_MONTH_DAY_RE = re.compile(
    rf"\b{_MONTH_PATTERN}\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?\b", re.IGNORECASE
)
# "7/16", "7/16/26", "7/16/2026". The lookarounds keep it out of times and
# set lists ("7:30/9:30" must not read as a date).
_SLASH_DATE_RE = re.compile(r"(?<![:\d/])(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?(?![:/\d])")
_RELATIVE_RE = re.compile(r"\b(tonight|today|tomorrow)\b", re.IGNORECASE)


def _next_occurrence(month: int, day: int, today: dt.date) -> dt.date | None:
    """The next real calendar date with this month/day on-or-after ``today``
    (an email announces an upcoming show, not an anniversary)."""
    for year in (today.year, today.year + 1):
        try:
            candidate = dt.date(year, month, day)
        except ValueError:
            continue  # e.g. Feb 30, or Feb 29 in a non-leap year — try next year
        if candidate >= today:
            return candidate
    return None


def _guess_date(haystack: str, today: dt.date) -> str | None:
    """The earliest date mention in the text, resolved to a real date."""
    best: tuple[int, dt.date] | None = None

    def consider(position: int, resolved: dt.date | None) -> None:
        nonlocal best
        if resolved is not None and (best is None or position < best[0]):
            best = (position, resolved)

    for iso in _ISO_RE.finditer(haystack):
        year, month, day = (int(group) for group in iso.groups())
        try:
            consider(iso.start(), dt.date(year, month, day))
        except ValueError:
            pass
    for month_day in _MONTH_DAY_RE.finditer(haystack):
        month = _MONTH_NUMBERS[month_day.group(1)[:3].lower()]
        consider(month_day.start(), _next_occurrence(month, int(month_day.group(2)), today))
    for slash in _SLASH_DATE_RE.finditer(haystack):
        month, day = int(slash.group(1)), int(slash.group(2))
        if not (1 <= month <= 12 and 1 <= day <= 31):
            continue
        if slash.group(3) is not None:
            year = int(slash.group(3))
            if year < 100:
                year += 2000
            try:
                consider(slash.start(), dt.date(year, month, day))
            except ValueError:
                pass
        else:
            consider(slash.start(), _next_occurrence(month, day, today))
    for relative in _RELATIVE_RE.finditer(haystack):
        word = relative.group(1).lower()
        consider(relative.start(), today + dt.timedelta(days=1 if word == "tomorrow" else 0))

    return best[1].isoformat() if best is not None else None


# --- time -------------------------------------------------------------------

_AMPM_RE = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*([ap])\.?m\b\.?", re.IGNORECASE)
_BARE_HHMM_RE = re.compile(r"\b(\d{1,2}):(\d{2})\b")
_DOORS_RE = re.compile(
    r"\bdoors?\s*(?:at\s+|@\s*)?(\d{1,2})(?::(\d{2}))?\b", re.IGNORECASE
)


def _pm_assumed(hour: int, minute: int) -> str | None:
    """Format a clock reading with no am/pm marker, read as evening: shows
    start at night, so 1–11 mean pm; 12–23 are taken as written."""
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    if 1 <= hour <= 11:
        hour += 12
    return f"{hour:02d}:{minute:02d}"


def _guess_time(haystack: str) -> str | None:
    """The start-time guess. Explicit am/pm wins; else a bare H:MM; else a
    "doors N". Earliest mention wins within each rule."""
    ampm = _AMPM_RE.search(haystack)
    if ampm is not None:
        hour, minute = int(ampm.group(1)), int(ampm.group(2) or 0)
        if 1 <= hour <= 12 and 0 <= minute <= 59:
            hour %= 12
            if ampm.group(3).lower() == "p":
                hour += 12
            return f"{hour:02d}:{minute:02d}"
    bare = _BARE_HHMM_RE.search(haystack)
    if bare is not None:
        formatted = _pm_assumed(int(bare.group(1)), int(bare.group(2)))
        if formatted is not None:
            return formatted
    doors = _DOORS_RE.search(haystack)
    if doors is not None:
        return _pm_assumed(int(doors.group(1)), int(doors.group(2) or 0))
    return None


# --- venue ------------------------------------------------------------------


def _guess_venue(haystack: str, venues: Sequence[Venue]) -> Venue | None:
    """The known venue whose name appears in the text; the longest (canonical)
    name wins. Both sides are canonicalized, matching whole tokens only, so
    "Yoshi's" matches "yoshi s" but a venue named "Keys" wouldn't fire on
    "keys to the city". A leading "The " on the venue name is optional."""
    padded_haystack = f" {canonicalize(haystack)} "
    best: tuple[int, Venue] | None = None
    for venue in venues:
        canonical_name = canonicalize(venue.name)
        candidates = {canonical_name}
        if canonical_name.startswith("the "):
            candidates.add(canonical_name[4:])
        for candidate in candidates:
            if candidate and f" {candidate} " in padded_haystack:
                if best is None or len(canonical_name) > best[0]:
                    best = (len(canonical_name), venue)
    return best[1] if best is not None else None


# --- entry point -------------------------------------------------------------


def parse_email(
    from_addr: str,
    subject: str,
    text: str,
    *,
    venues: Sequence[Venue],
    senders: Mapping[str, str],
    today: dt.date,
) -> ParsedDraft:
    """Parse one email into draft fields. ``senders`` maps lowercased email
    addresses to artist display names (the ``mail_senders`` table); ``today``
    anchors year-less date resolution."""
    _, address = parseaddr(from_addr)
    artist = senders.get(address.strip().lower()) if address else None

    haystack = f"{subject}\n{text}"
    venue = _guess_venue(haystack, venues)

    return ParsedDraft(
        artist_display=artist,
        venue_slug=venue.slug if venue is not None else None,
        venue_name_guess=venue.name if venue is not None else None,
        date_guess=_guess_date(haystack, today),
        time_guess=_guess_time(haystack),
    )
