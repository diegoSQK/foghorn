"""Shared parser for the "APE" (Another Planet Entertainment) WordPress
listing template.

Fox Theater Oakland and the Greek Theatre Berkeley (both APE-operated) run the
same WordPress theme, which server-renders every upcoming show on one listing
page as a ``div.mix.detail-information`` block: an ``h2.show-title`` headliner
inside a link to the venue's per-event page, an optional ``div.topline`` tour
banner, an optional ``div.support`` element with one act per ``<br>``-separated
line, a ``div.single-date-show`` whose microdata ``content`` attribute carries
the full start ("July 7, 2026 8:00 pm"), an ``event__doors-open`` span, and a
Ticketmaster button marked ``itemprop="url"`` ("Buy Tickets" or "Sold Out!" —
either way the event link we want). No prices appear anywhere on the template.

This module is the one place that markup is understood; per-venue scrapers stay
thin wrappers supplying the URL and slug. Quirks handled here rather than per
venue:

- **Cancelled shows stay listed.** A cancelled show keeps its block with a
  "SHOW CANCELLED" banner in the topline — dropped on a cancelled/postponed
  keyword in the topline.
- **Non-music events.** Both rooms also book comedy, podcast tapings, and
  screenings. Blocks whose title or topline clearly says so are dropped;
  anything merely ambiguous is kept.
- **Support lines that aren't acts.** The support element sometimes carries an
  italicized annotation ("*An all encompassing retrospective*") instead of a
  band — italic-only lines are dropped. A "Featuring …"/"With …" lead-in is
  stripped ("Featuring Grahame Lesh" → "Grahame Lesh").
"""

from __future__ import annotations

import datetime as dt
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag
from bs4.element import PageElement

from foghorn.models import ScrapedShow

# Titles/toplines that are clearly not concerts. Deliberately conservative —
# comedian names without a label ("Ilana Glazer Live!") stay in (ambiguous →
# keep); dropping those needs venue-side genre data the template doesn't have.
DROP_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bcomedy\b", re.IGNORECASE),
    re.compile(r"\bcomedians?\b", re.IGNORECASE),
    re.compile(r"\bstand-?up\b", re.IGNORECASE),
    re.compile(r"\bpodcasts?\b", re.IGNORECASE),
    re.compile(r"\bscreenings?\b", re.IGNORECASE),
    re.compile(r"\bmovie night\b", re.IGNORECASE),
    re.compile(r"\bfilm series\b", re.IGNORECASE),
    re.compile(r"\btrivia\b", re.IGNORECASE),
)

# Cancelled/postponed shows keep their listing block with a topline banner.
_CANCELLED_RE = re.compile(r"\b(?:cancell?ed|postponed)\b", re.IGNORECASE)

# The single-date-show microdata content: "July 7, 2026 8:00 pm" (rarely
# without the space before am/pm, as in the sibling date-show element).
_CONTENT_FORMATS = ("%B %d, %Y %I:%M %p", "%B %d, %Y %I %p")

# "7:00 pm | " in the doors span; tolerant of "7pm" / "7:00 p.m.".
_TIME_RE = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*([ap])\.?\s*m\.?", re.IGNORECASE)

# Support-line lead-ins that label the act rather than name one.
_SUPPORT_LEAD_IN_RE = re.compile(r"^(?:featuring|feat\.?|with)\s+", re.IGNORECASE)


def _clean(text: str) -> str:
    return " ".join(text.split())


def _attr(tag: Tag, name: str) -> str | None:
    """Read a single-valued attribute as a clean ``str``. bs4 types attributes
    as ``str | list[str] | None``; ``href``/``content`` are always single, but
    we coerce defensively to stay type-safe."""
    value = tag.get(name)
    if isinstance(value, str):
        return value
    if isinstance(value, list) and value:
        return str(value[0])
    return None


def _parse_content_datetime(value: str) -> dt.datetime | None:
    """Parse the microdata ``content`` start ("July 7, 2026 8:00 pm") into a
    naive local datetime. The venue tz is applied at ingest, not here."""
    text = re.sub(r"(?<=\d)([ap]m)\b", r" \1", _clean(value), flags=re.IGNORECASE)
    for fmt in _CONTENT_FORMATS:
        try:
            return dt.datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _parse_time(text: str) -> dt.time | None:
    """Extract "7:00 pm" from a time fragment, ignoring any label or the
    template's trailing " | " separator."""
    match = _TIME_RE.search(text)
    if match is None:
        return None
    hour = int(match.group(1)) % 12
    minute = int(match.group(2) or 0)
    if match.group(3).lower() == "p":
        hour += 12
    if hour > 23 or minute > 59:
        return None
    return dt.time(hour, minute)


def _support_acts(support: Tag) -> list[str]:
    """Split the support element into one act per ``<br>``-separated line.

    Lines whose visible text is entirely italicized are annotations, not acts
    ("*An all encompassing retrospective*") — dropped. A "Featuring …"/"With …"
    lead-in is stripped; multi-artist prose within one line is kept verbatim
    (splitting "Peter Rowan with Sam Grisman Project…" would mangle it).
    """
    segments: list[list[PageElement]] = [[]]
    for child in support.children:
        if isinstance(child, Tag) and child.name == "br":
            segments.append([])
        else:
            segments[-1].append(child)

    acts: list[str] = []
    for segment in segments:
        text = _clean(
            "".join(
                node.get_text(" ") if isinstance(node, Tag) else str(node) for node in segment
            )
        )
        if not text:
            continue
        plain = _clean(
            "".join(
                str(node)
                for node in segment
                if not (isinstance(node, Tag) and node.name in ("i", "em"))
            )
        )
        if not plain:
            continue  # italic-only annotation, not an act
        act = _SUPPORT_LEAD_IN_RE.sub("", text)
        if act:
            acts.append(act)
    return acts


def parse_listing_html(
    html: str,
    *,
    venue_slug: str,
    today: dt.date,
    window_days: int,
    fallback_source_url: str,
) -> list[ScrapedShow]:
    """Parse one APE listing page into ``ScrapedShow``s dated within
    ``[today, today + window_days]``, sorted by ``start_local``.

    ``today`` is injected (not read from the clock) so the parser is
    deterministic and fixture-testable.
    """
    soup = BeautifulSoup(html, "html.parser")
    window_end = today + dt.timedelta(days=window_days)

    shows: list[ScrapedShow] = []
    for block in soup.select("div.mix.detail-information"):
        title_el = block.select_one("h2.show-title")
        if title_el is None:
            continue
        headliner = _clean(title_el.get_text(" ", strip=True))
        if not headliner:
            continue

        topline_el = block.select_one("div.topline")
        topline = _clean(topline_el.get_text(" ", strip=True)) if topline_el is not None else ""
        label = f"{topline} {headliner}"
        if _CANCELLED_RE.search(topline):
            continue
        if any(pattern.search(label) for pattern in DROP_PATTERNS):
            continue

        date_el = block.select_one("div.single-date-show")
        content = _attr(date_el, "content") if date_el is not None else None
        start_local = _parse_content_datetime(content) if content else None
        if start_local is None:
            continue
        if not (today <= start_local.date() <= window_end):
            continue

        doors_el = block.select_one("span.event__doors-open")
        doors_time = (
            _parse_time(doors_el.get_text(" ", strip=True)) if doors_el is not None else None
        )

        support_el = block.select_one("div.support")
        support = _support_acts(support_el) if support_el is not None else []

        entry_link = block.select_one("div.entry a[href]")
        event_href = _attr(entry_link, "href") if entry_link is not None else None

        ticket_link = block.select_one('a[itemprop="url"]')
        ticket_url = _attr(ticket_link, "href") if ticket_link is not None else None

        shows.append(
            ScrapedShow(
                venue_slug=venue_slug,
                headliner_raw=headliner,
                support_raw=support,
                start_local=start_local,
                doors_local=(
                    dt.datetime.combine(start_local.date(), doors_time)
                    if doors_time is not None
                    else None
                ),
                ticket_url=ticket_url,
                price_text=None,  # the template shows no prices
                source_url=(
                    urljoin(fallback_source_url, event_href)
                    if event_href
                    else fallback_source_url
                ),
            )
        )
    shows.sort(key=lambda show: show.start_local)
    return shows
