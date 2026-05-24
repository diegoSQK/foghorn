"""Per-venue scrapers.

Each scraper lives in ``foghorn.scrapers.<venue_slug>`` and exposes a
zero-argument ``scrape() -> list[ScrapedShow]``. ``REGISTERED_SCRAPERS`` maps a
venue slug to its scrape callable; the ``make scrape`` CLI
(``foghorn.cli.scrape``) iterates it, runs each through the ingest pipeline, and
prints per-venue counts.

Adding a venue: implement ``foghorn/scrapers/<slug>.py`` with a ``scrape()``
(see ``bird_and_beckett`` for the pattern — fetch is isolated from a pure,
fixture-testable parse), then add an entry here.
"""

from __future__ import annotations

from collections.abc import Callable

from foghorn.models import ScrapedShow
from foghorn.scrapers import bird_and_beckett

REGISTERED_SCRAPERS: dict[str, Callable[[], list[ScrapedShow]]] = {
    bird_and_beckett.VENUE_SLUG: bird_and_beckett.scrape,
}
