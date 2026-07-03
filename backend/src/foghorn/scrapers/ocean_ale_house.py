"""Ocean Ale House scraper.

Source: the venue's schedule TSV on GitHub. oceanalehouse.com is a fully
client-rendered React site (the served HTML has an empty ``<body>``), so there
is no server-rendered calendar to scrape — but its ``/events/`` route fetches a
tab-separated schedule from the site's public content repo,
``raw.githubusercontent.com/aspyrx/oah-content`` (``events.tsv``), and renders
it in the browser. We fetch the same file: it's the venue's single source of
truth and is plain structured text.

Column semantics are mirrored from the site's own bundled parser (PapaParse +
a small loader class in the events chunk): columns are ``month, weekday, day,
time, <unused>, title, summary[, blurb]`` with no header row; a blank month or
day carries the previous row's value forward; rows with no time or whose title
is empty/"-"/"#N/A" are placeholders to skip. The file carries **no year** —
the site assumes the current year; we additionally roll far-past dates into
the next year so the scraper stays correct across the December→January
boundary. The bar's calendar mixes live music with game/trivia/karaoke/comedy
nights, which are dropped by a title+summary keyword filter (ambiguous entries
are kept).

Runnable standalone: ``python -m foghorn.scrapers.ocean_ale_house`` prints the
scraped shows as JSON and exits. No DB writes here — that's the ingest pipeline.
"""

from __future__ import annotations

import calendar
import datetime as dt
import json

import httpx

from foghorn.models import ScrapedShow

VENUE_SLUG = "ocean_ale_house"

# The exact URL the site's events page loads (see module docstring).
EVENTS_TSV_URL = "https://raw.githubusercontent.com/aspyrx/oah-content/refs/heads/main/events.tsv"
# Human-viewable calendar; also every show's source_url (the TSV itself isn't
# a browseable page and there are no per-event pages).
SOURCE_URL = "https://oceanalehouse.com/events/"
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 90
REQUEST_TIMEOUT = 30.0

# A date more than this many days in the past (with the current year applied)
# is assumed to belong to the next year — the forward-looking schedule never
# reaches this far back, so it can only be a year-boundary artifact.
_YEAR_ROLLOVER_DAYS = 180

_MONTHS = {name.lower(): number for number, name in enumerate(calendar.month_name) if name}

# Recurring non-music programming to drop; matched against title + summary.
# Anything ambiguous (DJ sets, vinyl nights, "Latin Band" food events) is kept.
_NON_MUSIC_SIGNALS = (
    "trivia",
    "game night",
    "karaoke",
    "comedy",
    "bingo",
    "private event",
    "closed",
)

# Title placeholders the site's own parser skips.
_PLACEHOLDER_TITLES = frozenset({"-", "#N/A"})


def fetch_tsv(url: str = EVENTS_TSV_URL) -> str:
    """Fetch the raw schedule TSV. Kept separate from parsing so tests drive
    ``parse_tsv`` from a fixture without touching the network."""
    response = httpx.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    )
    response.raise_for_status()
    return response.text


def _is_non_music(title: str, summary: str) -> bool:
    haystack = f"{title} {summary}".lower()
    return any(signal in haystack for signal in _NON_MUSIC_SIGNALS)


def _parse_time(time_text: str) -> dt.time | None:
    """Parse "6:00 PM" / "10:30 PM" (or "7 PM") into a time, ``None`` if the
    cell doesn't parse."""
    normalized = time_text.replace(" ", "").replace(".", "").upper()
    fmt = "%I:%M%p" if ":" in normalized else "%I%p"
    try:
        return dt.datetime.strptime(normalized, fmt).time()
    except ValueError:
        return None


def _resolve_date(month: int, day: int, today: dt.date) -> dt.date | None:
    """Attach a year to a month/day. The file assumes "this year"; a date far
    in the past rolls to next year (Dec→Jan boundary). ``None`` for invalid
    combinations (e.g. Feb 30)."""
    try:
        candidate = dt.date(today.year, month, day)
    except ValueError:
        return None
    if (today - candidate).days > _YEAR_ROLLOVER_DAYS:
        try:
            return dt.date(today.year + 1, month, day)
        except ValueError:
            return None
    return candidate


def parse_tsv(
    tsv_text: str, today: dt.date, window_days: int = SCRAPE_WINDOW_DAYS
) -> list[ScrapedShow]:
    """Return one ``ScrapedShow`` per musical event row whose date falls in
    ``[today, today + window_days]``.

    ``today`` is injected (not read from the clock) so the parser is
    deterministic and fixture-testable — it drives both the window and the
    year inference for the year-less month/day columns.
    """
    window_end = today + dt.timedelta(days=window_days)
    month: int | None = None
    day: int | None = None

    shows: list[ScrapedShow] = []
    for line in tsv_text.splitlines():
        fields = line.split("\t")
        # Month and day carry forward across rows when their cells are blank
        # (multiple shows on one day are listed under a single date).
        if fields[0].strip():
            month = _MONTHS.get(fields[0].strip().lower())
        if len(fields) > 2 and fields[2].strip():
            try:
                day = int(fields[2].strip())
            except ValueError:
                day = None
        if month is None or day is None or len(fields) < 6:
            continue
        time_text = fields[3].strip()
        title = " ".join(fields[5].split())
        summary = " ".join(fields[6].split()) if len(fields) > 6 else ""
        if not time_text or not title or title in _PLACEHOLDER_TITLES:
            continue
        if _is_non_music(title, summary):
            continue
        date = _resolve_date(month, day, today)
        if date is None or not (today <= date <= window_end):
            continue
        start_time = _parse_time(time_text)
        if start_time is None:
            continue

        shows.append(
            ScrapedShow(
                venue_slug=VENUE_SLUG,
                headliner_raw=title,
                support_raw=[],
                start_local=dt.datetime.combine(date, start_time),
                doors_local=None,
                ticket_url=None,
                price_text=None,
                source_url=SOURCE_URL,
            )
        )
    shows.sort(key=lambda show: show.start_local)
    return shows


def scrape() -> list[ScrapedShow]:
    """Fetch and parse the live schedule for the next ~90 days."""
    return parse_tsv(fetch_tsv(), dt.date.today())


def main() -> None:
    shows = scrape()
    print(
        json.dumps(
            [show.model_dump(mode="json") for show in shows],
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
