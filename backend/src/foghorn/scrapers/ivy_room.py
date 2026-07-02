"""Ivy Room scraper.

Source: Venuepilot's public GraphQL API. The Ivy Room (860 San Pablo Ave,
Albany) runs its calendar on Venuepilot — the Squarespace site's ``/shows``
page embeds the Venuepilot widget (``window.venuepilotSettings`` with
``accountIds: [992]``), which hydrates from ``https://www.venuepilot.co/graphql``.
Querying that API directly beats scraping the page: the widget is entirely
JS-rendered (the served HTML contains no events), while the GraphQL
``paginatedEvents`` query returns structured names, dates, door/start times,
price ranges, and per-event ticket pages, filtered server-side by date range.

Bills are usually packed into ``name`` as "HEADLINER + SUPPORT + SUPPORT";
we split on that separator to fill ``support_raw`` (dropping "TBD"-style
placeholders).

Runnable standalone: ``python -m foghorn.scrapers.ivy_room`` prints the
scraped shows as JSON and exits. No DB writes here — that's the ingest pipeline.
"""

from __future__ import annotations

import datetime as dt
import json
import re

import httpx

from foghorn.models import ScrapedShow

VENUE_SLUG = "ivy_room"

GRAPHQL_URL = "https://www.venuepilot.co/graphql"
ACCOUNT_ID = 992
# Human-viewable calendar (the page embedding the Venuepilot widget); fallback
# provenance when an event carries no ticket page of its own.
CALENDAR_URL = "https://www.ivyroom.com/shows"
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 90
REQUEST_TIMEOUT = 30.0

# The fields the widget itself uses; ``announceArtists`` is unreliable (it can
# omit acts named in ``name``), so the bill is split from ``name`` instead.
_EVENTS_QUERY = """
query ($accountIds: [Int!]!, $startDate: String, $endDate: String, $page: Int) {
  paginatedEvents(
    arguments: {accountIds: $accountIds, startDate: $startDate, endDate: $endDate, page: $page}
  ) {
    collection {
      id
      name
      date
      doorTime
      startTime
      priceMin
      priceMax
      ticketsUrl
      websiteUrl
      status
    }
    metadata {
      totalPages
      currentPage
    }
  }
}
"""

# Support-slot placeholders that aren't real acts ("... + TBD").
_PLACEHOLDER_RE = re.compile(r"^(tbd|tba|more)\W*$", re.IGNORECASE)


def _client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    )


def fetch_events(
    today: dt.date,
    window_days: int = SCRAPE_WINDOW_DAYS,
    client: httpx.Client | None = None,
) -> list[dict[str, object]]:
    """Page through ``paginatedEvents`` for ``[today, today + window_days]``.
    ``client`` is injectable so tests can drive pagination with a mock
    transport instead of the network."""
    own_client = client is None
    if client is None:
        client = _client()
    try:
        events: list[dict[str, object]] = []
        page = 1
        while True:
            response = client.post(
                GRAPHQL_URL,
                json={
                    "query": _EVENTS_QUERY,
                    "variables": {
                        "accountIds": [ACCOUNT_ID],
                        "startDate": today.isoformat(),
                        "endDate": (today + dt.timedelta(days=window_days)).isoformat(),
                        "page": page,
                    },
                },
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("errors"):
                raise RuntimeError(f"Venuepilot GraphQL errors: {payload['errors']}")
            paginated = payload["data"]["paginatedEvents"]
            events.extend(paginated["collection"])
            metadata = paginated["metadata"]
            if metadata["currentPage"] >= metadata["totalPages"]:
                break
            page += 1
        return events
    finally:
        if own_client:
            client.close()


def _split_bill(name: str) -> tuple[str, list[str]]:
    """Split "HEADLINER + SUPPORT + SUPPORT" billing into headliner + support.
    Segments are kept verbatim; TBD-style placeholder slots are dropped."""
    parts = [part.strip() for part in name.split(" + ") if part.strip()]
    if not parts:
        return name.strip(), []
    support = [part for part in parts[1:] if not _PLACEHOLDER_RE.match(part)]
    return parts[0], support


def _parse_time(value: object) -> dt.time | None:
    """Venuepilot times are local "HH:MM:SS" strings (or null)."""
    if not isinstance(value, str) or not value:
        return None
    return dt.datetime.strptime(value, "%H:%M:%S").time()


def _format_price(value: float) -> str:
    return f"${value:g}"


def _price_text(price_min: object, price_max: object) -> str | None:
    """"$15" / "$15–$18" from the numeric range. None when unpriced (both
    absent or zero); a zero ``priceMin`` next to a real ``priceMax`` is
    Venuepilot's "no floor set", not a free tier, so only the max is shown."""
    low = float(price_min) if isinstance(price_min, int | float) else 0.0
    high = float(price_max) if isinstance(price_max, int | float) else 0.0
    if high <= 0 and low <= 0:
        return None
    if low <= 0 or high <= 0 or low == high:
        return _format_price(max(low, high))
    return f"{_format_price(low)}–{_format_price(high)}"


def parse_events(
    events: list[dict[str, object]], today: dt.date, window_days: int = SCRAPE_WINDOW_DAYS
) -> list[ScrapedShow]:
    """Map Venuepilot event dicts to ``ScrapedShow``s in
    ``[today, today + window_days]``. Pure / fixture-testable: ``today`` is
    injected, and the window is re-checked locally rather than trusting the
    server-side filter."""
    window_end = today + dt.timedelta(days=window_days)
    shows: list[ScrapedShow] = []
    for event in events:
        name = str(event.get("name") or "").strip()
        date_raw = event.get("date")
        if not name or not isinstance(date_raw, str):
            continue
        # ``status`` is the widget's button/state text; live values seen are
        # "Tickets" / "PURCHASE TICKETS" / "Free" / "SHOW POSTPONED".
        status = str(event.get("status") or "").lower()
        if "cancel" in status or "postpon" in status:
            continue
        date = dt.date.fromisoformat(date_raw)
        if not (today <= date <= window_end):
            continue
        start_time = _parse_time(event.get("startTime"))
        door_time = _parse_time(event.get("doorTime"))
        if start_time is None:
            # Rare: door time only. Use it as the best-known start.
            start_time = door_time
        if start_time is None:
            continue
        headliner, support = _split_bill(name)
        tickets_url = str(event.get("ticketsUrl") or "") or None
        website_url = str(event.get("websiteUrl") or "") or None
        shows.append(
            ScrapedShow(
                venue_slug=VENUE_SLUG,
                headliner_raw=headliner,
                support_raw=support,
                start_local=dt.datetime.combine(date, start_time),
                doors_local=dt.datetime.combine(date, door_time) if door_time else None,
                ticket_url=tickets_url,
                price_text=_price_text(event.get("priceMin"), event.get("priceMax")),
                # The Venuepilot ticket page is the closest thing to a stable
                # per-event page (the site's own widget uses hash routes).
                source_url=website_url or tickets_url or CALENDAR_URL,
            )
        )
    shows.sort(key=lambda show: show.start_local)
    return shows


def scrape() -> list[ScrapedShow]:
    """Fetch and parse the live calendar for the next ~90 days."""
    today = dt.date.today()
    return parse_events(fetch_events(today), today)


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
