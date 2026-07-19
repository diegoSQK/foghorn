"""The Crepe Place scraper.

Source: the Seabright creperie/venue's **Squarespace events collection** at
``thecrepeplace.com/shows-list?format=json`` (the ``/shows`` page is a
summary block over that collection) — the shared ``_squarespace_events``
core (pre-split ``upcoming`` array, epoch-ms starts/ends, per-event pages,
TicketWeb links in the body HTML).

Quirk: titles are hand-written flyers with the date/time/price/stage baked
in ("ROSEBUD, SATURDAY AUGUST 1 @9PM, $10", "JAZZ ON THE ROCKS 5:30 PM
-7:30 PM FREE"). The epoch ``startDate`` is authoritative for the clock, so
``_clean_title`` strips trailing comma-segments (and trailing tokens) that
are nothing but date/time/price/stage noise, plus a leading "<promoter>
PRESENTS:" credit. Comma-separated multi-act bills are kept whole — the
same commas also separate the noise, so a headliner/support split would be
guesswork. Non-music admixtures (talk series, dance showcases, trivia)
drop on title signal.

Runnable standalone: ``python -m foghorn.scrapers.the_crepe_place`` prints
the scraped shows as JSON and exits. No DB writes here — that's the ingest
pipeline.
"""

from __future__ import annotations

import datetime as dt
import json
import re

from foghorn.models import ScrapedShow
from foghorn.scrapers import _squarespace_events as core

VENUE_SLUG = "the_crepe_place"
BASE_URL = "https://thecrepeplace.com"
CALENDAR_URL = f"{BASE_URL}/shows"
EVENTS_JSON_URL = f"{BASE_URL}/shows-list?format=json"

_NON_MUSIC_RE = re.compile(
    r"\bscience on tap\b|\bbelly ?dance\b|\btrivia\b|\bcomedy\b|\bkaraoke\b",
    re.IGNORECASE,
)
_JAM_RE = re.compile(r"\bfamily jam\b|\bopen jam\b|\bjam session\b", re.IGNORECASE)
_TICKET_URL_RE = re.compile(r'href="(https?://(?:www\.)?ticketweb\.com[^"]+)"')

# A leading promoter credit: "(((folkYEAH))) PRESENTS:", "REDWOOD RECORDS
# PRESENTS:".
_PRESENTS_RE = re.compile(r"^.{0,40}?\bpresents\b\s*[:\-–—]?\s*", re.IGNORECASE)

# Exact month names/abbreviations only — a prefix match would eat names
# ("PHIL MARSH" is not a March).
_MONTH_TOKEN = (
    r"january|february|march|april|may|june|july|august|september|october|"
    r"november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec"
)
# One title token that is date/time/price/stage noise rather than a name.
_NOISE_TOKEN_RE = re.compile(
    r"^(?:"
    r"(?:mon|tue|tues|wed|wednes|thu|thur|thurs|fri|sat|satur|sun)(?:day)?|"
    rf"(?:{_MONTH_TOKEN})\.?|"
    r"\d{1,2}(?::\d{2})?(?:am|pm)?|am|pm|"
    r"\$?\d+(?:\.\d{2})?(?:adv|door)?|"
    r"from|to|til|till|at|on|in|the|a|an|and|garden|bar|stage|door|doors|"
    r"free|show|shows|event|brunch|adv|advance|close|live"
    r")$",
    re.IGNORECASE,
)
# Trailing noise tokens stripped from the end of the kept title ("JAZZ ON
# THE ROCKS 5:30 PM -7:30 PM FREE" carries its noise without commas).
_TRAILING_NOISE_RE = re.compile(
    r"[\s,\-–—@]+(?:"
    r"(?:mon|tue|tues|wed|wednes|thu|thur|thurs|fri|sat|satur|sun)(?:day)?|"
    rf"(?:{_MONTH_TOKEN})\.?|"
    r"\d{1,2}(?::\d{2})?(?:am|pm)?|am|pm|"
    r"\$?\d+(?:\.\d{2})?(?:adv|door)?|"
    r"from|to|til|till|free|close|at|on|in|the|garden|bar|stage|door|doors"
    r")[!.\s]*$",
    re.IGNORECASE,
)


def _is_noise_segment(segment: str) -> bool:
    """True when every token in a comma-segment is date/time/price/stage
    noise ("SATURDAY, JULY 18 @9PM, $15" → all three segments)."""
    tokens = [t.strip("!.,()@") for t in re.split(r"[\s@\-–—]+", segment)]
    tokens = [t for t in tokens if t]
    return bool(tokens) and all(_NOISE_TOKEN_RE.match(t) for t in tokens)


def _clean_title(raw: str) -> str:
    """Strip the flyer noise off a title, keeping the billing verbatim."""
    title = _PRESENTS_RE.sub("", raw).strip()
    segments = [s.strip() for s in title.split(",")]
    # Drop trailing all-noise segments; the first segment always survives.
    while len(segments) > 1 and _is_noise_segment(segments[-1]):
        segments.pop()
    cleaned = ", ".join(s for s in segments if s)
    while True:
        stripped = _TRAILING_NOISE_RE.sub("", cleaned)
        if stripped == cleaned:
            break
        cleaned = stripped
    cleaned = cleaned.strip(" ,-–—")
    return cleaned or raw


def parse_items(payload: dict[str, object], today: dt.date) -> list[ScrapedShow]:
    shows = core.parse_items(
        payload,
        today,
        venue_slug=VENUE_SLUG,
        base_url=BASE_URL,
        calendar_url=CALENDAR_URL,
        non_music_re=_NON_MUSIC_RE,
        ticket_url_re=_TICKET_URL_RE,
        jam_re=_JAM_RE,
    )
    return [
        show.model_copy(update={"headliner_raw": _clean_title(show.headliner_raw)})
        for show in shows
    ]


def scrape() -> list[ScrapedShow]:
    """Fetch and parse the live collection for the next ~90 days."""
    return parse_items(core.fetch_collection(EVENTS_JSON_URL), dt.date.today())


def main() -> None:
    print(
        json.dumps(
            [show.model_dump(mode="json") for show in scrape()],
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
