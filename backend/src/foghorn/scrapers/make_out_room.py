"""Make-Out Room scraper.

Source: the Mission mainstay's Weebly site publishes each night as a blog
post on the **homepage** — title "Tuesday, July 21", a ``M/D/YYYY`` date
line, then hand-written event blocks. Two quirks make this the oddest
fetch in the fleet: the site's **HTTPS is broken** (TLS handshake failure
on both hosts), so it's fetched over plain HTTP; and posts appear only
~4–5 days ahead, so the horizon is short by design — the nightly poll is
the coverage model (documented; the RSS feed at ``/2/feed`` mirrors the
same posts with empty bodies, so the homepage HTML is the richer source).

**Posts → shows.** A night's post can hold several events (an early jazz
show, a late DJ night). The date sits in the post *header*; Weebly then
fragments the body into many short lines, with each event's time range
("6:30pm - 9:30pm") ending its block — sometimes as a line suffix
(", donations accepted! ~ 6:30pm - 9:30pm"). A block's first line is the
billing, an explicit "7pm show" overrides the range start, "6pm doors"
becomes doors, and "FREE" / "NO COVER" set ``price_text="Free"``. Set
times and player names trail *after* the last range ("7pm / Ai-Ai /
7:45pm / Trio / Saki Minamimoto…"); those name-lines attach to the last
show's support so watchlist matching sees the actual players behind
series titles like "JAZZ at the MAKE OUT ROOM!". Blocks without any time
are skipped (never fabricate); karaoke/trivia/bingo drop on signal.

Runnable standalone: ``python -m foghorn.scrapers.make_out_room`` prints
the scraped shows as JSON and exits. No DB writes here — that's the
ingest pipeline.
"""

from __future__ import annotations

import datetime as dt
import json
import re

import httpx
from bs4 import BeautifulSoup

from foghorn.models import ScrapedShow

VENUE_SLUG = "make_out_room"

# Plain HTTP is deliberate — see module docstring.
HOMEPAGE_URL = "http://www.makeoutroom.com/"
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 90
REQUEST_TIMEOUT = 30.0

_DATE_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
_TIME_RANGE_RE = re.compile(
    r"(\d{1,2})(?::(\d{2}))?\s*([ap])m\s*[-–]\s*(\d{1,2})(?::(\d{2}))?\s*([ap])m",
    re.IGNORECASE,
)
_SHOW_TIME_RE = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*([ap])m\s+show", re.IGNORECASE)
_DOORS_TIME_RE = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*([ap])m\s+doors", re.IGNORECASE)
_TIME_ONLY_RE = re.compile(r"^\d{1,2}(?::\d{2})?\s*[ap]m$", re.IGNORECASE)
_FREE_RE = re.compile(r"\bFREE\b|\bNO COVER\b", re.IGNORECASE)
_NON_MUSIC_SIGNALS = ("karaoke", "trivia", "bingo", "private event", "comedy")


def _time(hour_raw: str, minute_raw: str | None, meridiem: str) -> dt.time:
    hour = int(hour_raw) % 12
    if meridiem.lower() == "p":
        hour += 12
    return dt.time(hour, int(minute_raw or 0))


def _clean_line(raw: str) -> str:
    """Strip the tildes / zero-width chars the venue decorates lines with."""
    return " ".join(raw.replace("​", "").replace("\xa0", " ").split()).strip("~ ")


def parse_posts(
    homepage_html: str, today: dt.date, window_days: int = SCRAPE_WINDOW_DAYS
) -> list[ScrapedShow]:
    """Homepage blog posts → ``ScrapedShow``s. Pure / fixture-testable."""
    soup = BeautifulSoup(homepage_html, "html.parser")
    window_end = today + dt.timedelta(days=window_days)
    shows: list[ScrapedShow] = []
    for post in soup.select("div.blog-post"):
        title_link = post.select_one(".blog-title a")
        content = post.select_one(".blog-content")
        if content is None:
            continue
        source_url = HOMEPAGE_URL
        if title_link is not None and title_link.get("href"):
            href = str(title_link["href"])
            source_url = f"http:{href}" if href.startswith("//") else href

        # The M/D/YYYY date lives in the post header, not the content.
        date_match = _DATE_RE.search(post.get_text(" "))
        if date_match is None:
            continue
        try:
            date = dt.date(
                int(date_match.group(3)),
                int(date_match.group(1)),
                int(date_match.group(2)),
            )
        except ValueError:
            continue
        if not (today <= date <= window_end):
            continue

        lines = [
            cleaned
            for raw in content.get_text("\n").split("\n")
            if (cleaned := _clean_line(raw))
        ]
        # A line containing a time range closes the current block; text
        # before the range on that line still belongs to the block.
        post_shows: list[ScrapedShow] = []
        block: list[str] = []
        tail_start = 0
        for index, line in enumerate(lines):
            if _DATE_RE.fullmatch(line):
                continue
            range_match = _TIME_RANGE_RE.search(line)
            if range_match is None:
                block.append(line)
                continue
            prefix = _clean_line(line[: range_match.start()]).strip(",")
            if prefix:
                block.append(prefix)
            show = _block_to_show(block, range_match, date, source_url)
            if show is not None:
                post_shows.append(show)
            block = []
            tail_start = index + 1
        # Set times + player names trail after the last range; attach them
        # to the last show's bill.
        if post_shows:
            support = _tail_acts(lines[tail_start:])
            if support:
                last = post_shows[-1]
                post_shows[-1] = last.model_copy(
                    update={"support_raw": list(last.support_raw) + support}
                )
        shows.extend(post_shows)
    shows.sort(key=lambda show: show.start_local)
    return shows


def _tail_acts(lines: list[str]) -> list[str]:
    """Player names from a trailing SET LIST ("7pm / Ai-Ai / 7:45pm / Trio
    Saki Minamimoto…"). Only lines after a time-only marker count — that's
    what distinguishes a set list from trailing promo prose (Instagram
    handles, release blurbs), which has no set times and yields nothing."""
    acts: list[str] = []
    in_sets = False
    for line in lines:
        if _TIME_ONLY_RE.match(line):
            in_sets = True
            continue
        if not in_sets or _TIME_RANGE_RE.search(line):
            continue
        act = line.strip(" ~,+&")
        if act.startswith(("-", "@")) or len(act) < 2 or len(act) > 45:
            continue
        if act.lower() in ("guests", "trio", "duo", "quartet"):
            continue
        if act not in acts:
            acts.append(act)
    return acts


def _block_to_show(
    block: list[str],
    range_match: re.Match[str],
    date: dt.date,
    source_url: str,
) -> ScrapedShow | None:
    text_lines = [line for line in block if not _DATE_RE.fullmatch(line)]
    if not text_lines:
        return None
    joined = " ".join(text_lines)
    if any(signal in joined.lower() for signal in _NON_MUSIC_SIGNALS):
        return None

    # The billing spans the leading short lines ("JAZZ" / "at the" / "MAKE
    # OUT ROOM!"); prose, prices, and door/show times end it.
    title_parts: list[str] = []
    for line in text_lines[:4]:
        if (
            _FREE_RE.search(line)
            or _SHOW_TIME_RE.search(line)
            or _DOORS_TIME_RE.search(line)
            or len(line) > 32
            or (
                len(line.split()) >= 4
                and sum(c.islower() for c in line) > sum(c.isupper() for c in line)
            )
        ):
            break
        title_parts.append(line)
    headliner = " ".join(title_parts).strip(" ~,+&")
    if not headliner:
        return None

    # Start: explicit "7pm show" inside the block wins over the range start.
    show_match = _SHOW_TIME_RE.search(joined)
    if show_match is not None:
        start = _time(show_match.group(1), show_match.group(2), show_match.group(3))
    else:
        start = _time(range_match.group(1), range_match.group(2), range_match.group(3))
    doors_match = _DOORS_TIME_RE.search(joined)
    doors = (
        _time(doors_match.group(1), doors_match.group(2), doors_match.group(3))
        if doors_match
        else None
    )

    end = _time(range_match.group(4), range_match.group(5), range_match.group(6))
    return ScrapedShow(
        venue_slug=VENUE_SLUG,
        headliner_raw=headliner,
        support_raw=[],
        start_local=dt.datetime.combine(date, start),
        end_local=dt.datetime.combine(date, end),
        doors_local=dt.datetime.combine(date, doors) if doors else None,
        ticket_url=None,
        price_text="Free" if _FREE_RE.search(joined) else None,
        source_url=source_url,
    )


def scrape() -> list[ScrapedShow]:
    """Fetch and parse the live homepage posts."""
    with httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    ) as client:
        response = client.get(HOMEPAGE_URL)
        response.raise_for_status()
        return parse_posts(response.text, dt.date.today())


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
