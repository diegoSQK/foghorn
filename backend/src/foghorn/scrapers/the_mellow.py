"""The Mellow SF scraper — covers both rooms the shop programs.

The Mellow (1401 Haight St) is a plant store / cafe / barbershop that took on
ticketed live music in August 2026 once its Type 90 entertainment licence came
through; jazz is the primary booking. It also runs the weekly **Lakehouse
Jazz** series out of the **Blue Heron Lake Boathouse** in Golden Gate Park.
Those are different neighborhoods, so they are two venue rows and this one
scraper routes each show to the right one off the source's own location
taxonomy.

**Source: EventON, not The Events Calendar.** The site is WordPress running
EventON 5.x (custom post type ``ajde_events``). The usual Tribe REST route
(``/wp-json/tribe/events/v1/events``) 404s, and the generic WordPress route
(``/wp-json/wp/v2/ajde_events``) is a trap: its ``date`` / ``date_gmt`` are the
*post* timestamps — several sit in 2021–2023 — and it exposes no showtime at
all. EventON keeps real showtimes in post meta (``evcal_srow`` / ``evcal_erow``,
unix seconds) that the REST API does not register.

So the datetimes come from the endpoint the ``/calendar/`` page itself calls:

    POST https://themellowsf.com/?evo-ajax=eventon_get_events

It answers unauthenticated, but only with a nonce and a shortcode payload
harvested from ``/calendar/`` (a hand-built minimal shortcode returns
``status: GOOD`` and zero rows, and a missing/bogus nonce returns ``status:
bad``). Its ``json`` key is the useful part: one entry **per occurrence** with
``unix_start`` / ``unix_end``, so a weekly series expands to per-date rows
rather than a single row — as long as ``show_repeats=yes`` is set, which the
site's own calendar does not use.

What that endpoint does *not* carry is the room. The location taxonomy lives on
the WordPress REST objects as ``class_list`` entries
(``event_location-the-mellow-haight`` / ``event_location-blue-heron-boathouse``),
so the two payloads are joined on the event id. Plain HTTP throughout — no
headless browser.

Runnable standalone: ``python -m foghorn.scrapers.the_mellow`` prints the
scraped shows as JSON and exits. No DB writes here — that's the ingest pipeline.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import re
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from foghorn.models import ScrapedShow

VENUE_SLUG_HAIGHT = "the_mellow_haight"
VENUE_SLUG_BOATHOUSE = "blue_heron_boathouse"
VENUE_TZ = ZoneInfo("America/Los_Angeles")

BASE_URL = "https://themellowsf.com"
CALENDAR_URL = f"{BASE_URL}/calendar/"
AJAX_URL = f"{BASE_URL}/?evo-ajax=eventon_get_events"
EVENTS_REST_URL = f"{BASE_URL}/wp-json/wp/v2/ajde_events"
USER_AGENT = "foghorn-scraper/0.1 (contact via diegoSQK/foghorn issues)"
SCRAPE_WINDOW_DAYS = 120
REQUEST_TIMEOUT = 30.0

# EventON location taxonomy term -> foghorn venue slug. Anything outside this
# map (and the closed-room set below) is a routing failure, not a show to
# guess at — see ``venue_slug_for``.
_LOCATION_SLUGS = {
    "the-mellow-haight": VENUE_SLUG_HAIGHT,
    "blue-heron-boathouse": VENUE_SLUG_BOATHOUSE,
}
# The Mission room closed in August 2026. Rows still tagged to it are dropped
# rather than raising — a closed room is expected data, not a broken taxonomy.
_CLOSED_LOCATIONS = ("mission",)

# Non-music programming, dropped so retail pop-ups and plant workshops don't
# land in the jazz calendar as shows. The venue's own ``event_type`` taxonomy
# is the primary signal (``concerts`` / ``workshops`` / ``pop-up``); the title
# list is the backstop for the untagged entries the calendar also carries
# (e.g. "Mindful Flow", which has no event_type term at all). Everything else
# — including an untagged entry with a music-looking title — is kept, matching
# the err-toward-inclusion posture of the other mixed-programming scrapers.
_NON_MUSIC_EVENT_TYPES = ("workshops", "pop-up", "pop-ups", "classes", "markets")
_NON_MUSIC_SIGNALS = (
    "workshop",
    "pop up",
    "pop-up",
    "repotting",
    "floral arranging",
    "wreath making",
    "mindful flow",
    "yoga",
    "meditation",
    "book club",
    "market",
)

_EVO_PARAMS_RE = re.compile(r"var evo_general_params\s*=\s*(\{.*?\});", re.S)
_CAL_DATA_RE = re.compile(r"evo_cal_data'?\s+data-sc=\"(.*?)\"", re.S)


class MellowSourceError(RuntimeError):
    """The source changed shape in a way that would silently lose or misroute
    shows — raised rather than returning a plausible-looking partial result."""


# --------------------------------------------------------------------------
# fetch
# --------------------------------------------------------------------------


def _client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    )


def fetch_calendar_page(client: httpx.Client) -> str:
    """Fetch ``/calendar/``. It renders no event rows itself — it is fetched
    for the AJAX nonce and the shortcode config the endpoint requires."""
    response = client.get(CALENDAR_URL)
    response.raise_for_status()
    return response.text


def parse_calendar_config(page: str) -> tuple[str, dict[str, Any]]:
    """Pull the AJAX nonce and the calendar's shortcode config out of
    ``/calendar/``. Both are required: the endpoint rejects a missing or wrong
    nonce, and a hand-built shortcode returns an empty result set."""
    params_match = _EVO_PARAMS_RE.search(page)
    if params_match is None:
        raise MellowSourceError("evo_general_params not found on the calendar page")
    nonce = json.loads(params_match.group(1)).get("n")
    if not nonce:
        raise MellowSourceError("no AJAX nonce in evo_general_params")

    sc_match = _CAL_DATA_RE.search(page)
    if sc_match is None:
        raise MellowSourceError("evo_cal_data shortcode config not found on the calendar page")
    shortcode = json.loads(html.unescape(sc_match.group(1)))
    if not isinstance(shortcode, dict):
        raise MellowSourceError("evo_cal_data shortcode config is not an object")
    return str(nonce), shortcode


def _unix_range(today: dt.date, window_days: int) -> tuple[int, int]:
    """The forward window as the unix-second bounds the endpoint filters on."""
    start = dt.datetime.combine(today, dt.time.min, tzinfo=VENUE_TZ)
    end = dt.datetime.combine(today + dt.timedelta(days=window_days), dt.time.max, tzinfo=VENUE_TZ)
    return int(start.timestamp()), int(end.timestamp())


def fetch_occurrences(
    client: httpx.Client,
    nonce: str,
    shortcode: dict[str, Any],
    today: dt.date,
    window_days: int = SCRAPE_WINDOW_DAYS,
) -> list[dict[str, Any]]:
    """Fetch every occurrence in the forward window in one request.

    Two overrides carry this. ``focus_start_date_range`` / ``focus_end_date_range``
    (unix seconds) are what actually select the events — ``fixed_month`` /
    ``fixed_year`` only relabel the calendar header, so paging by month returns
    the *same* rows under five different titles. And ``show_repeats=yes``
    expands a repeating series into one entry per date; the site's own calendar
    ships ``no``, which would collapse weekly Lakehouse Jazz to a single row.

    The harvested config is the base rather than a hand-built payload: blanking
    the focus range makes the endpoint answer with a non-JSON body, and a
    minimal shortcode answers ``GOOD`` with zero events.
    """
    window_start, window_end = _unix_range(today, window_days)
    params = dict(shortcode)
    params.update(
        {
            "focus_start_date_range": str(window_start),
            "focus_end_date_range": str(window_end),
            "show_repeats": "yes",
            "hide_mult_occur": "no",
            "hide_past": "yes",
            "event_count": "500",
            "show_limit": "no",
        }
    )
    form: dict[str, str] = {"direction": "none", "ajaxtype": "switchmonth", "nonce": nonce}
    for key, value in params.items():
        form[f"shortcode[{key}]"] = str(value)

    response = client.post(AJAX_URL, data=form, headers={"Referer": CALENDAR_URL})
    response.raise_for_status()
    try:
        payload = response.json()
    except ValueError:
        raise MellowSourceError("eventon_get_events returned a non-JSON body") from None
    if payload.get("status") != "GOOD":
        raise MellowSourceError(
            f"eventon_get_events refused the request: status={payload.get('status')!r}"
        )
    occurrences: list[dict[str, Any]] = payload.get("json") or []
    return occurrences


def fetch_event_index(client: httpx.Client) -> dict[int, dict[str, Any]]:
    """Map event id -> WordPress REST object, for the room taxonomy and the
    event permalink. Paginated defensively; the CPT is small today."""
    index: dict[int, dict[str, Any]] = {}
    page = 1
    while True:
        response = client.get(EVENTS_REST_URL, params={"per_page": 100, "page": page})
        if response.status_code == 400 and page > 1:
            break  # WP answers 400 past the last page
        response.raise_for_status()
        batch = response.json()
        if not batch:
            break
        for event in batch:
            index[int(event["id"])] = event
        if len(batch) < 100:
            break
        page += 1
    if not index:
        raise MellowSourceError("the ajde_events REST route returned no events")
    return index


# --------------------------------------------------------------------------
# parse
# --------------------------------------------------------------------------


def _terms(event: dict[str, Any], prefix: str) -> list[str]:
    classes = event.get("class_list")
    if not isinstance(classes, list):
        raise MellowSourceError(
            f"event {event.get('id')!r} has no class_list — the room taxonomy is unreadable"
        )
    return [c[len(prefix) :] for c in classes if isinstance(c, str) and c.startswith(prefix)]


def venue_slug_for(event: dict[str, Any]) -> str | None:
    """Route an event to its venue slug off the location taxonomy.

    ``None`` means "drop this one on purpose" (the closed Mission room). An
    unrecognized term raises: silently folding an unknown room into one of the
    two known ones would put shows in the wrong neighborhood, which is exactly
    the failure this venue split exists to prevent.
    """
    terms = _terms(event, "event_location-")
    if not terms:
        raise MellowSourceError(
            f"event {event.get('id')!r} carries no event_location term — cannot route it"
        )
    for term in terms:
        if term in _LOCATION_SLUGS:
            return _LOCATION_SLUGS[term]
    for term in terms:
        if any(closed in term for closed in _CLOSED_LOCATIONS):
            return None
    raise MellowSourceError(
        f"event {event.get('id')!r} has unrecognized event_location term(s) {terms!r}; "
        f"expected one of {sorted(_LOCATION_SLUGS)}"
    )


def _is_non_music(event: dict[str, Any], title: str) -> bool:
    if any(term in _NON_MUSIC_EVENT_TYPES for term in _terms(event, "event_type-")):
        return True
    lowered = title.lower()
    return any(signal in lowered for signal in _NON_MUSIC_SIGNALS)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _first_meta(occurrence: dict[str, Any], key: str) -> str | None:
    values = (occurrence.get("event_pmv") or {}).get(key)
    if isinstance(values, list) and values:
        value = str(values[0]).strip()
        return value or None
    if isinstance(values, str) and values.strip():
        return values.strip()
    return None


def _ticket_url(occurrence: dict[str, Any], fallback: str) -> str | None:
    # evcal_lmlink is EventON's "learn more / tickets" link (Eventbrite here);
    # evcal_exlink is the alternate external link. Neither is guaranteed.
    for key in ("evcal_lmlink", "evcal_exlink"):
        value = _first_meta(occurrence, key)
        if value and value.startswith("http") and value != fallback:
            return value
    return None


def _price_text(occurrence: dict[str, Any]) -> str | None:
    price = _first_meta(occurrence, "_seo_offer_price")
    if not price:
        return None
    currency = _first_meta(occurrence, "_seo_offer_currency") or "$"
    return f"{currency}{price}" if len(currency) == 1 else f"{price} {currency}"


def _local(unix_seconds: Any) -> dt.datetime | None:
    try:
        stamp = int(unix_seconds)
    except (TypeError, ValueError):
        return None
    if stamp <= 0:
        return None
    return dt.datetime.fromtimestamp(stamp, tz=VENUE_TZ).replace(tzinfo=None)


def parse_occurrences(
    occurrences: list[dict[str, Any]],
    event_index: dict[int, dict[str, Any]],
    today: dt.date,
    window_days: int = SCRAPE_WINDOW_DAYS,
) -> list[ScrapedShow]:
    """Turn EventON occurrences into shows, one row per date.

    Pure — the tests drive it from saved payloads. Occurrences already arrive
    expanded per date (``show_repeats=yes``), so a weekly series needs no
    recurrence maths here; each entry carries its own ``unix_start``.
    """
    horizon = today + dt.timedelta(days=window_days)
    shows: list[ScrapedShow] = []
    seen: set[tuple[str, str, str]] = set()
    for occurrence in occurrences:
        raw_id = occurrence.get("event_id", occurrence.get("ID"))
        try:
            event_id = int(raw_id)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            raise MellowSourceError(f"occurrence with no usable event id: {occurrence!r}") from None
        event = event_index.get(event_id)
        if event is None:
            raise MellowSourceError(
                f"occurrence for event {event_id} has no matching REST object — "
                "cannot determine which room it belongs to"
            )

        venue_slug = venue_slug_for(event)
        if venue_slug is None:
            continue  # closed Mission room

        title = _clean(str(occurrence.get("event_title") or ""))
        if not title:
            rendered = (event.get("title") or {}).get("rendered", "")
            title = _clean(str(rendered))
        if not title or _is_non_music(event, title):
            continue

        start_local = _local(occurrence.get("unix_start"))
        if start_local is None:
            continue
        if not (today <= start_local.date() <= horizon):
            continue
        end_local = _local(occurrence.get("unix_end"))
        if end_local is not None and end_local <= start_local:
            end_local = None

        source_url = str(event.get("link") or CALENDAR_URL)
        key = (venue_slug, start_local.isoformat(), title.casefold())
        if key in seen:
            continue
        seen.add(key)
        shows.append(
            ScrapedShow(
                venue_slug=venue_slug,
                headliner_raw=title,
                start_local=start_local,
                end_local=end_local,
                doors_local=None,
                ticket_url=_ticket_url(occurrence, source_url),
                price_text=_price_text(occurrence),
                source_url=source_url,
            )
        )
    shows.sort(key=lambda show: (show.start_local, show.venue_slug, show.headliner_raw))
    return shows


# --------------------------------------------------------------------------
# entry points
# --------------------------------------------------------------------------


def scrape(today: dt.date | None = None) -> list[ScrapedShow]:
    """Fetch and parse both rooms' shows for the forward window."""
    day = today or dt.date.today()
    with _client() as client:
        nonce, shortcode = parse_calendar_config(fetch_calendar_page(client))
        occurrences = fetch_occurrences(client, nonce, shortcode, day)
        event_index = fetch_event_index(client)
    return parse_occurrences(occurrences, event_index, day)


def scrape_haight() -> list[ScrapedShow]:
    """The Haight shop's shows only — the registry entry for
    ``the_mellow_haight``. Registered per venue so the nightly run prunes each
    room against its own listings."""
    return [show for show in scrape() if show.venue_slug == VENUE_SLUG_HAIGHT]


def scrape_boathouse() -> list[ScrapedShow]:
    """The Golden Gate Park boathouse's shows only (Lakehouse Jazz) — the
    registry entry for ``blue_heron_boathouse``."""
    return [show for show in scrape() if show.venue_slug == VENUE_SLUG_BOATHOUSE]


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
