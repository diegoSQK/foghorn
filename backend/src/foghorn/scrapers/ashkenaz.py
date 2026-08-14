"""Ashkenaz Music & Dance Community Center scraper — via VenuePilot's API.

Ashkenaz (1317 San Pablo Ave, Berkeley) has been running since 1973: a
world-music and participatory-dance room — zydeco, bachata, Balkan folk,
square dance, salsa — with live bands behind almost all of it.

**Source.** The site is Squarespace, but its calendar is a VenuePilot widget,
and VenuePilot has a public GraphQL API. The account id (1228) and server come
from the ``venuepilotSettings`` blob the page sets for the widget; the query
shape came out of the widget bundle (``vp-widget.umd.js``), since the endpoint
has introspection disabled — ``__schema`` is rejected, so the schema can't be
read from the server itself.

    POST https://www.venuepilot.co/graphql
    query ($accountIds: [Int!]!, $startDate: String!, $endDate: String) {
      publicEvents(accountIds: ..., startDate: ..., endDate: ...) { ... }
    }

Unauthenticated, one request for the whole window.

**``support`` is not a support act.** The field is free text and Ashkenaz uses
it as a subtitle: "Cajun/Zydeco", "A Grateful Dead Night", "Berkeley-Based Big
Band", "Just Announced!", "Fundraising Event". Across a 6-month window not one
value was a billed act. Mapping it to ``support_raw`` would invent performers
named "Just Announced!" and put them on the watchlist-matching surface, so it
feeds ``genre`` instead — which is what it usually is, and where ingest's
normalization drops the junk to None and lets the venue default apply.

``artists`` is present in the schema but empty for every Ashkenaz event, so the
headliner is ``name``.

**Dance nights are kept.** Much of the calendar is socials and square dances
with a lesson attached ("BACHATA Nightz — Class and Social Dance Party"). They
have live bands and participatory dancing is the venue's whole identity; a
"drop anything with a class" rule would gut it.

Runnable standalone: ``python -m foghorn.scrapers.ashkenaz``.
"""

from __future__ import annotations

import datetime as dt
import json
import urllib.error
import urllib.request
from typing import Any

from foghorn.models import ScrapedShow

VENUE_SLUG = "ashkenaz"
GRAPHQL_URL = "https://www.venuepilot.co/graphql"
ACCOUNT_ID = 1228
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 180
REQUEST_TIMEOUT = 40.0

# Trimmed from the widget bundle's query to the fields actually used.
_QUERY = """
query ($accountIds: [Int!]!, $startDate: String!, $endDate: String) {
  publicEvents(accountIds: $accountIds, startDate: $startDate, endDate: $endDate) {
    id
    name
    date
    doorTime
    startTime
    endTime
    support
    ticketsUrl
    websiteUrl
  }
}
"""


class AshkenazSourceError(RuntimeError):
    """The API changed shape or refused the request."""


def fetch_events(
    today: dt.date, window_days: int = SCRAPE_WINDOW_DAYS
) -> list[dict[str, Any]]:
    """Every public event in the forward window, in one GraphQL call."""
    payload = json.dumps(
        {
            "query": _QUERY,
            "variables": {
                "accountIds": [ACCOUNT_ID],
                "startDate": today.isoformat(),
                "endDate": (today + dt.timedelta(days=window_days)).isoformat(),
            },
        }
    ).encode()
    request = urllib.request.Request(
        GRAPHQL_URL,
        data=payload,
        headers={
            "User-Agent": USER_AGENT,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            body = json.load(response)
    except urllib.error.HTTPError as exc:
        raise AshkenazSourceError(f"venuepilot returned HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise AshkenazSourceError(f"venuepilot unreachable: {exc.reason}") from exc
    except ValueError:
        raise AshkenazSourceError("venuepilot returned a non-JSON body") from None

    if body.get("errors"):
        raise AshkenazSourceError(f"venuepilot query rejected: {body['errors']}")
    events = (body.get("data") or {}).get("publicEvents")
    if not isinstance(events, list):
        raise AshkenazSourceError("venuepilot payload has no publicEvents list")
    return events


def _combine(date_text: Any, time_text: Any) -> dt.datetime | None:
    """``"2026-08-13"`` + ``"20:00:00"`` → naive venue-local datetime."""
    if not isinstance(date_text, str) or not isinstance(time_text, str):
        return None
    try:
        return dt.datetime.fromisoformat(f"{date_text}T{time_text}")
    except ValueError:
        return None


def parse_events(
    events: list[dict[str, Any]],
    today: dt.date,
    window_days: int = SCRAPE_WINDOW_DAYS,
) -> list[ScrapedShow]:
    """Turn API events into shows. Pure — tests drive it from a saved payload."""
    horizon = today + dt.timedelta(days=window_days)
    shows: list[ScrapedShow] = []
    seen: set[tuple[str, str]] = set()
    for event in events:
        name = str(event.get("name") or "").strip()
        if not name:
            continue
        start_local = _combine(event.get("date"), event.get("startTime"))
        if start_local is None or not (today <= start_local.date() <= horizon):
            continue
        end_local = _combine(event.get("date"), event.get("endTime"))
        # A show ending "before" it starts has run past midnight; the model
        # documents that shape, so it's kept rather than discarded.
        doors_local = _combine(event.get("date"), event.get("doorTime"))

        tickets = event.get("ticketsUrl")
        website = event.get("websiteUrl")
        ticket_url = tickets if isinstance(tickets, str) and tickets else None
        source_url = (
            website if isinstance(website, str) and website else ticket_url
        ) or "https://www.ashkenaz.com/"

        key = (start_local.isoformat(), name.casefold())
        if key in seen:
            continue
        seen.add(key)
        shows.append(
            ScrapedShow(
                venue_slug=VENUE_SLUG,
                headliner_raw=name,
                # NOT support_raw — see the module docstring. This field is a
                # subtitle, and every observed value was a genre or a notice.
                start_local=start_local,
                end_local=end_local,
                doors_local=doors_local,
                ticket_url=ticket_url,
                price_text=None,  # not exposed by the API
                source_url=source_url,
                genre=str(event["support"]).strip()
                if isinstance(event.get("support"), str) and event["support"].strip()
                else None,
            )
        )
    shows.sort(key=lambda show: (show.start_local, show.headliner_raw))
    return shows


def scrape(today: dt.date | None = None) -> list[ScrapedShow]:
    day = today or dt.date.today()
    return parse_events(fetch_events(day), day)


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
