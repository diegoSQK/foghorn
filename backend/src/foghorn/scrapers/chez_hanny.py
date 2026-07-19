"""Jazz Chez Hanny scraper.

Source: the legendary Portola house-concert salon's hand-maintained
static homepage — "Coming Events" lists ``Act — Month D, YYYY — H:MMPM —
$N`` tuples in plain server-rendered HTML (Sundays at 4 PM, typically
~monthly). The parser walks date/time/price triples and takes the text
between matches as the act name, stripping the section's header words.
Tiny volume, pure wheelhouse.

Runnable standalone: ``python -m foghorn.scrapers.chez_hanny`` prints the
scraped shows as JSON and exits. No DB writes here — that's the ingest
pipeline.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import re

import httpx

from foghorn.models import ScrapedShow

VENUE_SLUG = "chez_hanny"
HOMEPAGE_URL = "https://www.chezhanny.com/"
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 180  # ~monthly shows post far ahead; keep two quarters
REQUEST_TIMEOUT = 30.0

_MONTHS = (
    "January", "February", "March", "April", "May", "June", "July",
    "August", "September", "October", "November", "December",
)
_ENTRY_RE = re.compile(
    r"(" + "|".join(_MONTHS) + r")\s+(\d{1,2}),\s*(\d{4})\s+"
    r"(\d{1,2}):(\d{2})\s*([AP]M)\s*\$(\d+)",
    re.IGNORECASE,
)
_HEADER_WORDS_RE = re.compile(
    r"^(?:Coming Events|Click Date for Details|Admission)\s*", re.IGNORECASE
)


def fetch_page(client: httpx.Client | None = None) -> str:
    own_client = client is None
    if client is None:
        client = httpx.Client(
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
            follow_redirects=True,
        )
    try:
        response = client.get(HOMEPAGE_URL)
        response.raise_for_status()
        return response.text
    finally:
        if own_client:
            client.close()


def parse_page(
    page_html: str, today: dt.date, window_days: int = SCRAPE_WINDOW_DAYS
) -> list[ScrapedShow]:
    """Homepage → ``ScrapedShow``s. Pure / fixture-testable."""
    text = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", page_html)).split())
    section_start = text.lower().find("coming events")
    section_end = text.lower().find("seating", section_start)
    section = text[
        max(section_start, 0) : section_end if section_end > 0 else len(text)
    ]
    window_end = today + dt.timedelta(days=window_days)
    shows: list[ScrapedShow] = []
    cursor = 0
    for match in _ENTRY_RE.finditer(section):
        name = section[cursor : match.start()].strip(" -–—·,")
        cursor = match.end()
        for _ in range(3):  # the header words stack before the first name
            stripped = _HEADER_WORDS_RE.sub("", name).strip(" -–—·,")
            if stripped == name:
                break
            name = stripped
        if not name:
            continue
        month = _MONTHS.index(match.group(1).capitalize()) + 1
        hour = int(match.group(4)) % 12
        if match.group(6).upper() == "PM":
            hour += 12
        try:
            start_local = dt.datetime(
                int(match.group(3)), month, int(match.group(2)),
                hour, int(match.group(5)),
            )
        except ValueError:
            continue
        if not (today <= start_local.date() <= window_end):
            continue
        shows.append(
            ScrapedShow(
                venue_slug=VENUE_SLUG,
                headliner_raw=name,
                support_raw=[],
                start_local=start_local,
                doors_local=None,
                ticket_url=None,
                price_text=f"${match.group(7)}",
                source_url=HOMEPAGE_URL,
            )
        )
    shows.sort(key=lambda show: show.start_local)
    return shows


def scrape() -> list[ScrapedShow]:
    """Fetch and parse the live schedule."""
    return parse_page(fetch_page(), dt.date.today())


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
