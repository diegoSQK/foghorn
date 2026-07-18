"""Poor House Bistro scraper — the OCR pattern, month-grid flavor.

Source: the San Jose blues/jazz bistro publishes its music schedule only as
a monthly **calendar-grid JPEG** (weekday columns × week rows, acts + time
ranges in day cells). Like Little Hill, the image goes through the
pluggable OCR layer (``foghorn.ocr``); unlike Little Hill's list layout,
this parser reconstructs a month grid.

**Grid strategy — compute dates, don't read them.** OCR of dense cells
merges some day numbers into neighboring act text, so day numbers are not
trusted per-cell. Instead: weekday header positions give the 7 column
bands, cleanly-read standalone day numbers give the week rows, and each
cell's date is *computed* from the month's first weekday — then
sanity-checked against every cleanly-read day anchor (a majority mismatch
aborts the parse rather than shipping shifted dates). The flyer month/year
come from the image's upload path, not the clock.

**Cells → shows.** Cell text splits on time-range matches ("6PM-9PM",
"12PM-3PM") — Sundays carry two slots (brunch + afternoon), so one cell
can yield two shows; ranges keep the start. "CLOSED" cells and segments
without a parseable range are dropped (never fabricate). Wednesday "PHB
JAZZ JAM" and "THEME JAM" rows are explicitly typed jams (the residency's
title says so; ingest inference can't see "host" phrasing). The venue
publishes one month at a time; the newest revision wins (uploads are
versioned "1Update…", "2Update…" in the month folder — pick the
lexicographically last, which the site nav links).

Runnable standalone: ``python -m foghorn.scrapers.poor_house_bistro``
prints the scraped shows as JSON and exits. No DB writes here — that's the
ingest pipeline.
"""

from __future__ import annotations

import calendar
import datetime as dt
import json
import re

import httpx

from foghorn.models import ScrapedShow
from foghorn.ocr import OcrLine, get_engine

VENUE_SLUG = "poor_house_bistro"

HOMEPAGE_URL = "https://poorhousebistro.com/"
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 90
REQUEST_TIMEOUT = 30.0

# Calendar uploads: wp-content/uploads/YYYY/MM/<rev>Update<Mon>_Cal<yy>.jpg
_CAL_IMG_RE = re.compile(
    r'(https://poorhousebistro\.com/wp-content/uploads/(\d{4})/(\d{2})/'
    r'[^"]*Cal[^"]*\.(?:jpe?g|png))"',
    re.IGNORECASE,
)

_DAY_NUMBER_RE = re.compile(r"^\s*(\d{1,2})\s*$")
_TIME_RANGE_RE = re.compile(
    r"(\d{1,2})(?::(\d{2}))?\s*([AP])M\s*[-–]\s*\d{1,2}(?::\d{2})?\s*[AP]M",
    re.IGNORECASE,
)
_WEEKDAY_HEADERS = (
    "sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday",
)
_JAM_SIGNALS = ("JAZZ JAM", "THEME JAM", "OPEN JAM")
_SKIP_SIGNALS = ("CLOSED", "PRIVATE EVENT")


def fetch_flyer(client: httpx.Client | None = None) -> tuple[bytes, int, int]:
    """Locate the newest calendar image on the homepage and fetch it.
    Returns ``(image_bytes, year, month)`` from the upload path."""
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
        candidates = _CAL_IMG_RE.findall(home.text)
        if not candidates:
            raise RuntimeError("no calendar image found on the PHB homepage")
        # Newest month folder, then the last revision name within it.
        url, year, month = max(candidates, key=lambda c: (c[1], c[2], c[0]))
        image = client.get(url)
        image.raise_for_status()
        return image.content, int(year), int(month)
    finally:
        if own_client:
            client.close()


def _column_bands(lines: list[OcrLine]) -> list[float] | None:
    """Weekday-header center-x per column (Sunday..Saturday), or None when
    the headers didn't all read."""
    centers: dict[int, float] = {}
    for line in lines:
        text = line.text.strip().lower()
        if text in _WEEKDAY_HEADERS:
            centers[_WEEKDAY_HEADERS.index(text)] = line.x + line.w / 2
    if len(centers) != 7:
        return None
    return [centers[i] for i in range(7)]


def _nearest_column(columns: list[float], x_center: float) -> int:
    return min(range(7), key=lambda i: abs(columns[i] - x_center))


def parse_flyer(
    lines: list[OcrLine],
    year: int,
    month: int,
    today: dt.date,
    window_days: int = SCRAPE_WINDOW_DAYS,
) -> list[ScrapedShow]:
    """OCR observations → ``ScrapedShow``s. Pure / fixture-testable; see the
    module docstring for the computed-grid strategy."""
    columns = _column_bands(lines)
    if columns is None:
        return []

    # Cleanly-read standalone day numbers: anchors for row bands + the
    # sanity check on the computed grid.
    anchors: list[tuple[OcrLine, int]] = []
    for line in lines:
        match = _DAY_NUMBER_RE.match(line.text)
        if match and 1 <= int(match.group(1)) <= 31:
            anchors.append((line, int(match.group(1))))
    if len(anchors) < 8:  # a grid we can't even band into rows
        return []

    # Row bands: cluster anchor center-ys (rows are ~0.1 apart; anchors
    # within 0.04 share a row).
    row_ys: list[float] = []
    for line, _day in sorted(anchors, key=lambda a: -a[0].cy):
        if not row_ys or row_ys[-1] - line.cy > 0.04:
            row_ys.append(line.cy)

    # Computed grid: cell (row, col) → day of month.
    first_weekday = (calendar.weekday(year, month, 1) + 1) % 7  # Sunday=0
    days_in_month = calendar.monthrange(year, month)[1]

    def cell_day(row: int, col: int) -> int | None:
        day = row * 7 + col - first_weekday + 1
        return day if 1 <= day <= days_in_month else None

    # A cell's text hangs from just below its anchor down to just above the
    # NEXT row's anchor (measured ~0.08 of image height on the live flyer),
    # so rows are bounded by the next anchor line, not a fixed margin. The
    # last row extends one median row-spacing down, which also fences off
    # the footer.
    _ANCHOR_MARGIN = 0.02
    spacings = [row_ys[i] - row_ys[i + 1] for i in range(len(row_ys) - 1)]
    median_spacing = sorted(spacings)[len(spacings) // 2] if spacings else 0.1

    def row_of(cy: float) -> int | None:
        for i, row_y in enumerate(row_ys):
            upper = row_y + _ANCHOR_MARGIN
            # The last row gets 1.2 spacings of reach — its cells run right
            # to the grid edge, while the footer sits well below.
            next_y = (
                row_ys[i + 1]
                if i + 1 < len(row_ys)
                else row_y - median_spacing * 1.2
            )
            lower = next_y + _ANCHOR_MARGIN
            if lower < cy <= upper:
                return i
        return None

    # Sanity check: the cleanly-read anchors must agree with the computed
    # grid, else the whole geometry is off — refuse to ship shifted dates.
    agree = disagree = 0
    for line, day in anchors:
        row = row_of(line.cy)
        if row is None:
            continue
        expected = cell_day(row, _nearest_column(columns, line.x + line.w / 2))
        if expected == day:
            agree += 1
        elif expected is not None:
            disagree += 1
    if agree < disagree * 3 or agree == 0:
        return []

    # Assign act text to cells. Day numbers and weekday headers are
    # excluded; header/footer lines fall outside every row band.
    cells: dict[tuple[int, int], list[OcrLine]] = {}
    for line in lines:
        text = line.text.strip()
        if not text or _DAY_NUMBER_RE.match(text):
            continue
        if text.lower() in _WEEKDAY_HEADERS:
            continue
        row = row_of(line.cy)
        if row is None:
            continue
        col = _nearest_column(columns, line.x + line.w / 2)
        cells.setdefault((row, col), []).append(line)

    window_end = today + dt.timedelta(days=window_days)
    shows: list[ScrapedShow] = []
    for (row, col), cell_lines in cells.items():
        day_of_month = cell_day(row, col)
        if day_of_month is None:
            continue
        date = dt.date(year, month, day_of_month)
        if not (today <= date <= window_end):
            continue
        ordered = sorted(cell_lines, key=lambda line: (-line.cy, line.x))
        # Strip day numbers OCR merged into text ("12 SID MORRIS").
        joined = " ".join(
            re.sub(r"^\d{1,2}\s+|\s+\d{1,2}$", "", line.text.strip())
            for line in ordered
        )
        joined = " ".join(joined.split())
        if any(signal in joined.upper() for signal in _SKIP_SIGNALS):
            continue
        # Split the cell into (act text, time range) segments.
        cursor = 0
        for match in _TIME_RANGE_RE.finditer(joined):
            act = joined[cursor:match.start()].strip(" ~•-–&,")
            cursor = match.end()
            if not act:
                continue
            hour = int(match.group(1)) % 12
            if match.group(3).upper() == "P":
                hour += 12
            upper_act = act.upper()
            shows.append(
                ScrapedShow(
                    venue_slug=VENUE_SLUG,
                    headliner_raw=act,
                    support_raw=[],
                    start_local=dt.datetime.combine(
                        date, dt.time(hour, int(match.group(2) or 0))
                    ),
                    doors_local=None,
                    ticket_url=None,
                    price_text=None,
                    source_url=HOMEPAGE_URL,
                    event_type=(
                        "jam"
                        if any(s in upper_act for s in _JAM_SIGNALS)
                        else None
                    ),
                )
            )
    shows.sort(key=lambda show: show.start_local)
    return shows


def scrape() -> list[ScrapedShow]:
    """Fetch the current calendar, OCR it (pluggable engine), parse."""
    image_bytes, year, month = fetch_flyer()
    recognize = get_engine()
    return parse_flyer(recognize(image_bytes), year, month, dt.date.today())


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
