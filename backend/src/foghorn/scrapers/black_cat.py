"""Black Cat (SF) scraper.

Source: the club's ticketing platform, **Turntable Tickets**. Black Cat's own
site (blackcatsf.com) is a marketing page whose "Shows" links all point at
``blackcatsf.turntabletickets.com`` — a Vue SPA whose calendar hydrates from a
clean JSON REST API at ``/api/performance/``. Querying it the same way the
calendar page does (``booking=true&pagination=false&start_date=…&end_date=…``)
returns every performance in the range in one response, each with a nested
``show`` object carrying the title and per-person price range. That beats
scraping the SPA's HTML, which server-renders only an empty ``performances``
store.

Performance ``datetime`` values are UTC (``…Z``); we convert to naive
venue-local time here because the local calendar date is also needed to build
the per-show booking URL (``/shows/<id>/?date=YYYY-MM-DD``), matching the
site's own links. Ingest re-applies the venue tz as usual.

Runnable standalone: ``python -m foghorn.scrapers.black_cat`` prints the
scraped shows as JSON and exits. No DB writes here — that's the ingest pipeline.
"""

from __future__ import annotations

import datetime as dt
import json
from zoneinfo import ZoneInfo

import httpx

from foghorn.models import ScrapedShow

VENUE_SLUG = "black_cat"
VENUE_TZ = ZoneInfo("America/Los_Angeles")

PERFORMANCE_API = "https://blackcatsf.turntabletickets.com/api/performance/"
# Human-viewable calendar (also the venue's seed calendar_url).
CALENDAR_URL = "https://blackcatsf.turntabletickets.com/calendar"
# Per-show booking page, as linked from the site's own calendar. ``date`` is
# the *local* calendar date of the performance.
SHOW_URL_TEMPLATE = "https://blackcatsf.turntabletickets.com/shows/{show_id}/?date={date}"
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 90
REQUEST_TIMEOUT = 30.0


def _is_non_show(title: str) -> bool:
    """The venue posts closure markers as show entries ("*CLOSED* 4th of July
    Weekend", …). These aren't public shows — drop them."""
    lowered = title.lower().lstrip("*! ")
    return lowered.startswith("closed") or "private event" in lowered


def _client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    )


def fetch_performances(
    today: dt.date,
    window_days: int = SCRAPE_WINDOW_DAYS,
    client: httpx.Client | None = None,
) -> list[dict[str, object]]:
    """Fetch every performance in ``[today, today + window_days]`` in a single
    request (``pagination=false`` returns the full range). The end date gets a
    one-day buffer because the API filters on UTC datetimes, which run ahead of
    Pacific calendar dates; ``parse_performances`` re-applies the exact local
    window. ``client`` is injectable so tests use a mock transport."""
    own_client = client is None
    if client is None:
        client = _client()
    try:
        params = {
            "booking": "true",
            "pagination": "false",
            "start_date": today.isoformat(),
            "end_date": (today + dt.timedelta(days=window_days + 1)).isoformat(),
        }
        response = client.get(PERFORMANCE_API, params=params)
        response.raise_for_status()
        payload = response.json()
        results = payload.get("results", []) if isinstance(payload, dict) else []
        return results if isinstance(results, list) else []
    finally:
        if own_client:
            client.close()


def _to_local(iso_utc: str) -> dt.datetime:
    """Convert an ISO 8601 UTC timestamp ("2026-07-03T02:00:00Z") to a naive
    venue-local datetime."""
    aware = dt.datetime.fromisoformat(iso_utc)
    if aware.tzinfo is None:
        aware = aware.replace(tzinfo=dt.UTC)
    return aware.astimezone(VENUE_TZ).replace(tzinfo=None)


def _price_text(show: dict[str, object]) -> str | None:
    """Format ``price_per_person`` (a ["low", "high"] pair of decimal strings)
    as "$14.50–$44.50", collapsing to a single "$25.00" when low == high."""
    prices = show.get("price_per_person")
    if not isinstance(prices, list):
        return None
    texts = [f"${value}" for value in prices if isinstance(value, str) and value]
    if not texts:
        return None
    if len(set(texts)) == 1:
        return texts[0]
    return f"{texts[0]}–{texts[-1]}"


def parse_performances(
    performances: list[dict[str, object]],
    today: dt.date,
    window_days: int = SCRAPE_WINDOW_DAYS,
) -> list[ScrapedShow]:
    """Map Turntable performance dicts to ``ScrapedShow``s. Pure /
    fixture-testable; ``today`` is injected so the window and the
    not-yet-published filter don't depend on the clock.

    Skips closure markers, performances without a start or title, and
    performances whose ``publish_datetime`` is still in the future (the site's
    own calendar applies the same publish gate). The API results are not
    date-ordered — sorting happens here.
    """
    window_end = today + dt.timedelta(days=window_days)

    shows: list[ScrapedShow] = []
    for performance in performances:
        start_raw = performance.get("datetime")
        show = performance.get("show")
        if not isinstance(start_raw, str) or not isinstance(show, dict):
            continue
        name = show.get("name")
        title = " ".join(str(name).split()) if isinstance(name, str) else ""
        if not title or _is_non_show(title):
            continue
        publish_raw = performance.get("publish_datetime")
        if isinstance(publish_raw, str) and publish_raw:
            if _to_local(publish_raw).date() > today:
                continue
        start_local = _to_local(start_raw)
        if not (today <= start_local.date() <= window_end):
            continue

        show_id = performance.get("show_id") or show.get("id")
        if isinstance(show_id, int):
            show_url = SHOW_URL_TEMPLATE.format(
                show_id=show_id, date=start_local.date().isoformat()
            )
        else:
            show_url = CALENDAR_URL

        shows.append(
            ScrapedShow(
                venue_slug=VENUE_SLUG,
                headliner_raw=title,
                support_raw=[],
                start_local=start_local,
                doors_local=None,
                ticket_url=show_url,
                price_text=_price_text(show),
                source_url=show_url,
            )
        )
    shows.sort(key=lambda show: show.start_local)
    return shows


def scrape() -> list[ScrapedShow]:
    """Fetch and parse the live calendar for the next ~90 days."""
    today = dt.date.today()
    return parse_performances(fetch_performances(today), today)


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
