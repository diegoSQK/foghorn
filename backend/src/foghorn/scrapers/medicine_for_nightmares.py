"""Medicine for Nightmares scraper.

Source: the shop's **Squarespace events collection JSON**. Medicine for
Nightmares (a Mission bookstore/galeria at 3036 24th St, SF) lists everything
on ``medicinefornightmares.com/events``; appending ``?format=json`` returns
the collection's structured payload whose ``upcoming`` array carries every
posted future event (title, epoch-millisecond start instant, per-event page
URL, body HTML). The array is not paginated — the ``?offset=`` pagination only
walks the ``past`` list, and a GetItemsByMonth cross-check confirms
``upcoming`` covers all posted months — so one request covers the window.

**Music filtering.** The calendar mixes the shop's curated Friday
creative-music series ("Other Dimensions in Sound", jazz/improvised sets)
with chess club, poetry readings, book talks, author events, printmaking
workshops, zine fests, and film nights. Classification is signal-based, in
precedence order: a music signal in the title keeps; a non-music signal in
the title drops; a non-music signal in the body drops (this beats incidental
music mentions in author bios); a music signal in the body keeps (this
rescues ambiguous items like a musicians' open mic); anything left is kept
as ambiguous-musical. For kept "Other Dimensions in Sound" shows the series
prefix (often typo'd "Dimesnions" on the site) is stripped so the guest act
is the headliner. The JSON carries no ticket links or prices for music
events, so ``ticket_url``/``price_text`` are always ``None``.

Runnable standalone: ``python -m foghorn.scrapers.medicine_for_nightmares``
prints the scraped shows as JSON and exits. No DB writes here — that's the
ingest pipeline.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import re
from zoneinfo import ZoneInfo

import httpx

from foghorn.models import ScrapedShow

VENUE_SLUG = "medicine_for_nightmares"
VENUE_TZ = ZoneInfo("America/Los_Angeles")

BASE_URL = "https://medicinefornightmares.com"
# Human-viewable calendar (also the venue's seed calendar_url) — fallback
# provenance when an item carries no per-event URL.
CALENDAR_URL = f"{BASE_URL}/events"
EVENTS_JSON_URL = f"{CALENDAR_URL}?format=json"
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 90
REQUEST_TIMEOUT = 30.0

# Precedence 1: music-signaled titles are kept outright. "in sound" catches
# the "Other Dimensions in Sound" series (including the site's recurring
# "Dimesnions" typo, since only the stable tail is matched).
_TITLE_KEEP_RE = re.compile(
    r"\bin sound\b|\bmusic\b|\bconcert\b|\bband\b|\bdj\b|\bjazz\b", re.IGNORECASE
)
# Precedence 2: clearly-non-music titles — chess club, workshops, zine fests,
# art pláticas, poetry, book events, storytelling, film nights.
_TITLE_DROP_RE = re.compile(
    r"\bchess\b|\bworkshop\b|\bzine\b|\bpl[aá]tica\b|\bpoet\w*\b|\bbook\b"
    r"|\bstorytelling\b|\bmovies?\b|\bfilm\b|\bscreening\b|\bauthors?\b"
    r"|\bart opening\b|\blecture\b|\btatreez\b",
    re.IGNORECASE,
)
# Precedence 3: non-music signals in the body drop the event. Checked before
# body music signals so an author reading isn't rescued by a bio that happens
# to mention "music ensembles".
_BODY_DROP_RE = re.compile(
    r"\bauthors?\b|\bpoetry\b|\bpoems?\b|\bpoemas\b|\bpoes[ií]a\b|\bspoken ?word\b"
    r"|\bbook (?:club|talk|reading)\b|\bchess\b|\bembroidery\b|\breading series\b"
    r"|\bscreening\b|\bworkshop\b",
    re.IGNORECASE,
)
# Precedence 4: music-signaled bodies keep (e.g. an open mic "for queer
# musicians and songwriters"). Anything with no signal at all is kept as
# ambiguous-musical.
_BODY_KEEP_RE = re.compile(
    r"\bmusic\w*\b|\bband\b|\bconcert\b|\bjazz\b|\bsongwriters?\b|\bdj\b"
    r"|\bvinyl\b|\borchestra\b|\bsingers?\b",
    re.IGNORECASE,
)

# "Other Dimensions in Sound; <act>" / "… in Sound presents <act>" — strip the
# series prefix so the guest act is the headliner. \w* absorbs the site's
# "Dimesnions" typo.
_SERIES_PREFIX_RE = re.compile(
    r"^other\s+dim\w*\s+in\s+sound\s*(?:[;:,–—-]+\s*|presents\s+)?",
    re.IGNORECASE,
)

_STYLE_RE = re.compile(r"<style[^>]*>.*?</style>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


def fetch_events(client: httpx.Client | None = None) -> dict[str, object]:
    """Fetch the events collection JSON. ``client`` is injectable so tests can
    drive the request with a mock transport instead of the network."""
    own_client = client is None
    if client is None:
        client = httpx.Client(
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
            follow_redirects=True,
        )
    try:
        response = client.get(EVENTS_JSON_URL)
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else {}
    finally:
        if own_client:
            client.close()


def _clean_text(raw: str) -> str:
    """Unescape entities and collapse whitespace (incl. non-breaking spaces)."""
    return " ".join(html.unescape(raw).split())


def _body_text(item: dict[str, object]) -> str:
    """The item's excerpt+body as plain text, with Squarespace's inline
    ``<style>`` blocks removed so their CSS doesn't pollute signal matching."""
    parts: list[str] = []
    for key in ("excerpt", "body"):
        value = item.get(key)
        if isinstance(value, str):
            parts.append(value)
    stripped = _TAG_RE.sub(" ", _STYLE_RE.sub(" ", " ".join(parts)))
    return _clean_text(stripped)


def _is_music(title: str, body: str) -> bool:
    """Signal-precedence classifier; see module docstring. Defaults to keep so
    ambiguous-musical items survive."""
    if _TITLE_KEEP_RE.search(title):
        return True
    if _TITLE_DROP_RE.search(title):
        return False
    if _BODY_DROP_RE.search(body):
        return False
    if _BODY_KEEP_RE.search(body):
        return True
    return True


def _headliner(title: str) -> str:
    """Strip the "Other Dimensions in Sound" series prefix so the guest act is
    the headliner; other titles pass through verbatim."""
    stripped = _SERIES_PREFIX_RE.sub("", title).strip()
    return stripped or title


def _start_local(item: dict[str, object]) -> dt.datetime | None:
    """``startDate`` is a UTC epoch in milliseconds; convert to naive
    venue-local time (the tz is re-applied at ingest)."""
    raw = item.get("startDate")
    if not isinstance(raw, int | float):
        return None
    instant = dt.datetime.fromtimestamp(raw / 1000, tz=dt.UTC)
    return instant.astimezone(VENUE_TZ).replace(tzinfo=None, microsecond=0)


def parse_events(
    payload: dict[str, object], today: dt.date, window_days: int = SCRAPE_WINDOW_DAYS
) -> list[ScrapedShow]:
    """Map the collection JSON's ``upcoming`` items to ``ScrapedShow``s in
    ``[today, today + window_days]``. Pure / fixture-testable; ``today`` is
    injected so the window doesn't depend on the clock."""
    raw_items = payload.get("upcoming")
    if not isinstance(raw_items, list):
        raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        return []
    window_end = today + dt.timedelta(days=window_days)
    shows: list[ScrapedShow] = []
    seen: set[str] = set()
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        item_id = item.get("id")
        if isinstance(item_id, str):
            if item_id in seen:
                continue
            seen.add(item_id)
        title_raw = item.get("title")
        if not isinstance(title_raw, str):
            continue
        title = _clean_text(title_raw)
        if not title or not _is_music(title, _body_text(item)):
            continue
        start_local = _start_local(item)
        if start_local is None or not (today <= start_local.date() <= window_end):
            continue
        full_url = item.get("fullUrl")
        source_url = (
            f"{BASE_URL}{full_url}"
            if isinstance(full_url, str) and full_url.startswith("/")
            else CALENDAR_URL
        )
        shows.append(
            ScrapedShow(
                venue_slug=VENUE_SLUG,
                headliner_raw=_headliner(title),
                support_raw=[],
                start_local=start_local,
                doors_local=None,
                ticket_url=None,
                price_text=None,
                source_url=source_url,
            )
        )
    shows.sort(key=lambda show: show.start_local)
    return shows


def scrape() -> list[ScrapedShow]:
    """Fetch and parse the live calendar for the next ~90 days."""
    return parse_events(fetch_events(), dt.date.today())


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
