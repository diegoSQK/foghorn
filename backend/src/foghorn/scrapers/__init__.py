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
from foghorn.scrapers import (
    bird_and_beckett,
    black_cat,
    boom_boom_room,
    bottom_of_the_hill,
    keys_jazz_bistro,
    kilowatt,
    madrone_art_bar,
    mr_tipples,
    natural_grocery_annex,
    ocean_ale_house,
    rickshaw_stop,
    the_knockout,
)

REGISTERED_SCRAPERS: dict[str, Callable[[], list[ScrapedShow]]] = {
    bird_and_beckett.VENUE_SLUG: bird_and_beckett.scrape,
    black_cat.VENUE_SLUG: black_cat.scrape,
    boom_boom_room.VENUE_SLUG: boom_boom_room.scrape,
    bottom_of_the_hill.VENUE_SLUG: bottom_of_the_hill.scrape,
    keys_jazz_bistro.VENUE_SLUG: keys_jazz_bistro.scrape,
    kilowatt.VENUE_SLUG: kilowatt.scrape,
    madrone_art_bar.VENUE_SLUG: madrone_art_bar.scrape,
    mr_tipples.VENUE_SLUG: mr_tipples.scrape,
    natural_grocery_annex.VENUE_SLUG: natural_grocery_annex.scrape,
    ocean_ale_house.VENUE_SLUG: ocean_ale_house.scrape,
    rickshaw_stop.VENUE_SLUG: rickshaw_stop.scrape,
    the_knockout.VENUE_SLUG: the_knockout.scrape,
}
