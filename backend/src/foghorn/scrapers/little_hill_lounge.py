"""Little Hill Lounge scraper — the OCR pattern.

Source: littlehillelcerrito.com publishes its calendar **only as a monthly
flyer JPEG** (the "COMING UP" section; a former Tribe install was removed).
The flyer is cleanly typeset — a ``DAY M/D`` date column beside a
description column with times — so OCR reads it essentially verbatim: this
scraper fetches the flyer image and runs it through the **pluggable OCR
layer** (``foghorn.ocr``, selected via ``FOGHORN_OCR_ENGINE``; Apple
Vision by default on macOS, RapidOCR elsewhere — see that module for the
engine contract and quality notes). The parser tolerates engine
differences that don't break structure: spacing-less date cells
("WED7/1", RapidOCR) and fullwidth commas are normalized; a missing
engine dependency raises clearly into ``/api/health/scrape``. The parser
itself is pure and tested from checked-in fixtures of both engines' real
output on any platform.

**Layout → shows.** OCR observations carry normalized bounding boxes.
Lines matching ``DAY M/D`` anchor rows; description-column lines pair to
the date with the nearest center-y (same row), else attach upward as
continuation lines (multi-line bills). The flyer year/month come from the
image's WordPress upload path (``/uploads/YYYY/MM/``) — not the clock — so
a stale flyer can't mint wrong-year shows. Times parse from the trailing
"8pm" / "7-11pm" / "7pm - 12am" forms (ranges keep the start); **rows
without an explicit time are skipped** rather than given a fabricated one,
per the Bird & Beckett convention. Bills split on commas (first act
headliner, rest support, "w/" prefixes stripped); non-music rows (karaoke,
bingo, movie nights, "OPEN FOR …") drop on title signal.

**Known limitation.** OCR confuses letter-O runs with zeros in stylized
sans ("OOO" → "00O"), and language correction doesn't help (band names
aren't words). Rare; accepted — the flyer is otherwise read verbatim.

Runnable standalone: ``python -m foghorn.scrapers.little_hill_lounge``
prints the scraped shows as JSON and exits. No DB writes here — that's the
ingest pipeline.
"""

from __future__ import annotations

import datetime as dt
import json
import re

import httpx

from foghorn.models import ScrapedShow
from foghorn.ocr import OcrLine, get_engine

VENUE_SLUG = "little_hill_lounge"

HOMEPAGE_URL = "https://littlehillelcerrito.com/"
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 90
REQUEST_TIMEOUT = 30.0

# The flyer <img> inside the COMING UP section: a wp-content upload whose
# path carries year/month. WordPress serves scaled variants with a -WxH
# suffix; stripping it fetches the original.
_FLYER_IMG_RE = re.compile(
    r'<img[^>]+src="(https://littlehillelcerrito\.com/wp-content/uploads/'
    r"(\d{4})/(\d{2})/[^\"]+\.(?:jpe?g|png))\"",
    re.IGNORECASE,
)
_SCALED_SUFFIX_RE = re.compile(r"-\d{2,4}x\d{2,4}(\.(?:jpe?g|png))$", re.IGNORECASE)

# \s* not \s+: RapidOCR drops the space in date cells ("WED7/1").
_DATE_LINE_RE = re.compile(
    r"^(?:MON|TUE|WED|THU|FRI|SAT|SUN)\s*(\d{1,2})/(\d{1,2})$", re.IGNORECASE
)
# Trailing time, permissive: ", 8pm" / ", 7-11pm" / ", 7pm - 12am" /
# ", 7:30pm". Ranges keep the start; a bare-start range ("7-11pm") borrows
# the end's meridiem.
_TIME_RE = re.compile(
    r"[,\s]\s*(\d{1,2})(?::(\d{2}))?\s*(pm|am)?"
    r"(?:\s*[-–]\s*(\d{1,2})(?::(\d{2}))?\s*(pm|am))?\s*$",
    re.IGNORECASE,
)

_NON_MUSIC_SIGNALS = (
    "karaoke",
    "bingo",
    "movie",
    "trivia",
    "open for",
    "closed",
    "private event",
)

# Row pairing tolerances, in normalized image units. Same-row date and
# description centers land well inside 0.013; successive rows sit ~0.02
# apart (measured on the 2026-07 flyer at 1080×1350).
_SAME_ROW_TOLERANCE = 0.013


def fetch_flyer(
    client: httpx.Client | None = None,
) -> tuple[bytes, int, int]:
    """Locate the current flyer on the homepage and fetch the full-size
    image. Returns ``(image_bytes, year, month)`` — year/month from the
    upload path. ``client`` is injectable for tests."""
    own_client = client is None
    if client is None:
        client = httpx.Client(
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
            follow_redirects=True,
        )
    try:
        home = client.get(HOMEPAGE_URL)
        home.raise_for_status()
        # The page also serves logo images from wp-content (2022 uploads), so
        # scope to the COMING UP section when present and take the newest
        # upload — the current month's flyer.
        html = home.text
        marker = html.upper().find("COMING UP")
        candidates = _FLYER_IMG_RE.findall(html[marker:] if marker >= 0 else html)
        if not candidates:
            raise RuntimeError("no flyer image found on the Little Hill homepage")
        url, year_raw, month_raw = max(candidates, key=lambda c: (c[1], c[2]))
        year, month = int(year_raw), int(month_raw)
        full_url = _SCALED_SUFFIX_RE.sub(r"\1", url)
        image = client.get(full_url)
        if image.status_code != httpx.codes.OK:
            image = client.get(url)  # scaled fallback if no original exists
            image.raise_for_status()
        return image.content, year, month
    finally:
        if own_client:
            client.close()


def _start_time(text: str) -> tuple[str, dt.time] | None:
    """Extract the trailing time; returns ``(text_without_time, start)`` or
    None when the row states no time (those rows are skipped)."""
    match = _TIME_RE.search(text)
    if match is None:
        return None
    hour_raw, minute_raw, meridiem = match.group(1), match.group(2), match.group(3)
    if meridiem is None:
        meridiem = match.group(6)  # "7-11pm": the range end's pm applies
    if meridiem is None:
        return None
    hour = int(hour_raw) % 12
    if meridiem.lower() == "pm":
        hour += 12
    return text[: match.start()].strip(" ,"), dt.time(hour, int(minute_raw or 0))


def _clean_act(raw: str) -> str:
    """Trim a billing segment: drop "w/" prefixes and an unbalanced
    trailing parenthetical (a flyer typo Vision reads verbatim)."""
    act = raw.strip(" ,&")
    act = re.sub(r"^w/\s*", "", act, flags=re.IGNORECASE).strip()
    if "(" in act and ")" not in act:
        act = act[: act.index("(")].strip(" ,")
    return act


def _split_bill(text: str) -> tuple[str, list[str]]:
    """Comma-separated billing → (headliner, support). Series titles with
    no commas ("Jazz on Tuesdays: X", DJ nights) stay whole."""
    acts = [
        cleaned for part in text.split(",") if (cleaned := _clean_act(part))
    ]
    if not acts:
        return "", []
    return acts[0], acts[1:]


def parse_flyer(
    lines: list[OcrLine],
    year: int,
    month: int,
    today: dt.date,
    window_days: int = SCRAPE_WINDOW_DAYS,
) -> list[ScrapedShow]:
    """OCR observations → ``ScrapedShow``s in ``[today, today + window]``.
    Pure / fixture-testable. Rows pair by center-y (see module docstring);
    non-music rows and rows without an explicit time are skipped."""
    dates: list[tuple[OcrLine, dt.date]] = []
    others: list[OcrLine] = []
    for line in lines:
        match = _DATE_LINE_RE.match(line.text.strip())
        if match:
            row_month, day = int(match.group(1)), int(match.group(2))
            # The flyer is monthly; a mismatched month is an OCR misread.
            if row_month != month:
                continue
            try:
                dates.append((line, dt.date(year, month, day)))
            except ValueError:
                continue
        else:
            others.append(line)
    if not dates:
        return []

    # Description-column lines sit right of every date line.
    date_right_edge = max(line.x + line.w for line, _ in dates)
    rows: dict[dt.date, list[tuple[float, str]]] = {date: [] for _, date in dates}
    for line in others:
        if line.x < date_right_edge:
            continue  # logo / header / footer text
        same_row = min(dates, key=lambda d: abs(d[0].cy - line.cy))
        if abs(same_row[0].cy - line.cy) <= _SAME_ROW_TOLERANCE:
            rows[same_row[1]].append((line.cy, line.text))
            continue
        above = [d for d in dates if d[0].cy > line.cy]
        if above:  # continuation of the nearest row above
            parent = min(above, key=lambda d: d[0].cy - line.cy)
            rows[parent[1]].append((line.cy, line.text))

    window_end = today + dt.timedelta(days=window_days)
    shows: list[ScrapedShow] = []
    for date in sorted(rows):
        if not (today <= date <= window_end):
            continue
        parts = [text for _, text in sorted(rows[date], key=lambda r: -r[0])]
        # RapidOCR emits fullwidth commas on some glyphs; normalize
        # before signal checks, time parsing, and bill splitting.
        text = " ".join(" ".join(parts).split()).replace("\uff0c", ",")
        if not text or any(s in text.lower() for s in _NON_MUSIC_SIGNALS):
            continue
        timed = _start_time(text)
        if timed is None:
            continue
        bill_text, start = timed
        headliner, support = _split_bill(bill_text)
        if not headliner:
            continue
        shows.append(
            ScrapedShow(
                venue_slug=VENUE_SLUG,
                headliner_raw=headliner,
                support_raw=support,
                start_local=dt.datetime.combine(date, start),
                doors_local=None,
                # "ALL SHOWS $10" is a blanket flyer line, not per-event
                # pricing — not propagated.
                ticket_url=None,
                price_text=None,
                source_url=HOMEPAGE_URL,
            )
        )
    shows.sort(key=lambda show: show.start_local)
    return shows


def scrape() -> list[ScrapedShow]:
    """Fetch the current flyer, OCR it (pluggable engine — see
    ``foghorn.ocr``), and parse the next ~90 days."""
    image_bytes, year, month = fetch_flyer()
    recognize = get_engine()
    return parse_flyer(recognize(image_bytes), year, month, dt.date.today())


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
