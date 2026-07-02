"""Seed the scraped venue set (the Phase 2 jazz four + the venue-expansion
batch).

Idempotent by construction: ``venues.upsert`` keys on ``slug``, so calling
``seed`` repeatedly converges to exactly these rows without duplicating. A
``calendar_url`` is a placeholder until the venue's scraper discovers and sets
the real one.

Runnable standalone: ``python -m foghorn.repo.seed_venues`` seeds the default DB.
"""

from __future__ import annotations

import sqlite3

from foghorn.models import Venue
from foghorn.repo import db
from foghorn.repo import venues as venues_repo

_TBD = "TBD"  # set by each venue's Phase 2.x scraper ticket

SEED_VENUES: list[Venue] = [
    Venue(
        slug="sfjazz",
        name="SFJAZZ Center",
        neighborhood="Hayes Valley",
        region="SF",
        address="201 Franklin St, San Francisco, CA",
        tz="America/Los_Angeles",
        website_url="https://www.sfjazz.org",
        calendar_url=_TBD,
        genre="jazz",
    ),
    Venue(
        slug="keys_jazz_bistro",
        name="Keys Jazz Bistro",
        neighborhood="North Beach",
        region="SF",
        address="530 Broadway, San Francisco, CA",
        tz="America/Los_Angeles",
        website_url="https://www.keysjazzbistro.com",
        # Set by Phase 2.2a. The scraper parses the forward-looking
        # /upcoming-shows/ page — see scrapers/keys_jazz_bistro.
        calendar_url="https://keysjazzbistro.com/upcoming-shows/",
        genre="jazz",
    ),
    Venue(
        slug="bird_and_beckett",
        name="Bird & Beckett Books and Records",
        neighborhood="Glen Park",
        region="SF",
        address="653 Chenery St, San Francisco, CA",
        tz="America/Los_Angeles",
        website_url="https://www.birdbeckett.com",
        # Set by Phase 2.1 (the pilot venue). The scraper reads the public
        # Google Calendar .ics behind this page — see scrapers/bird_and_beckett.
        calendar_url="https://birdbeckett.com/events/",
        genre="jazz",
    ),
    Venue(
        slug="mr_tipples",
        name="Mr. Tipple's Recording Studio",
        neighborhood="Hayes Valley",
        region="SF",
        address="39 Fell St, San Francisco, CA",
        tz="America/Los_Angeles",
        # The seed originally had mrtipples.com (NXDOMAIN). Live site is
        # mrtipplessf.com; the scraper reads its Tribe Events REST API.
        website_url="https://mrtipplessf.com",
        calendar_url="https://mrtipplessf.com/calendar/",
        genre="jazz",
    ),
    # --- Venue-expansion batch (June 2026) ---
    Venue(
        slug="black_cat",
        name="Black Cat",
        neighborhood="Tenderloin",
        region="SF",
        address="400 Eddy St, San Francisco, CA",
        tz="America/Los_Angeles",
        website_url="https://www.blackcatsf.com",
        # The scraper reads the Turntable Tickets performance API behind this
        # calendar — see scrapers/black_cat.
        calendar_url="https://blackcatsf.turntabletickets.com/calendar",
        genre="jazz",
    ),
    Venue(
        slug="ocean_ale_house",
        name="Ocean Ale House",
        neighborhood="Ingleside",
        region="SF",
        address="1314 Ocean Ave, San Francisco, CA",
        tz="America/Los_Angeles",
        website_url="https://oceanalehouse.com",
        # The site is client-rendered; the scraper reads the schedule TSV the
        # events page itself fetches — see scrapers/ocean_ale_house.
        calendar_url="https://oceanalehouse.com/events/",
        # Jazz-leaning but genuinely mixed bookings (jazz, DJ nights, rock).
        genre="eclectic",
    ),
    Venue(
        slug="kilowatt",
        name="Kilowatt",
        neighborhood="Mission",
        region="SF",
        address="3160 16th St, San Francisco, CA",
        tz="America/Los_Angeles",
        website_url="https://www.kilowattbar.com",
        # The scraper reads the Dice.fm events API via the venue's public
        # widget key — see scrapers/kilowatt.
        calendar_url="https://www.kilowattbar.com/events",
        genre="rock",
    ),
    Venue(
        slug="the_knockout",
        name="The Knockout",
        neighborhood="Mission",
        region="SF",
        address="3223 Mission St, San Francisco, CA",
        tz="America/Los_Angeles",
        website_url="https://theknockoutsf.com",
        # Squarespace calendar-collection month JSON; the older /calendar
        # collection is stale test data — see scrapers/the_knockout.
        calendar_url="https://theknockoutsf.com/calendar2",
        genre="rock",
    ),
    Venue(
        slug="bottom_of_the_hill",
        name="Bottom of the Hill",
        neighborhood="Potrero Hill",
        region="SF",
        address="1233 17th St, San Francisco, CA",
        tz="America/Los_Angeles",
        website_url="https://www.bottomofthehill.com",
        # Hand-maintained static HTML calendar — see scrapers/bottom_of_the_hill.
        calendar_url="https://www.bottomofthehill.com/calendar.html",
        genre="rock",
    ),
    Venue(
        slug="rickshaw_stop",
        name="Rickshaw Stop",
        neighborhood="Hayes Valley",
        region="SF",
        address="155 Fell St, San Francisco, CA",
        tz="America/Los_Angeles",
        website_url="https://rickshawstop.com",
        # SeeTickets white-label calendar (server-rendered + nonce'd AJAX
        # pagination) — see scrapers/rickshaw_stop.
        calendar_url="https://rickshawstop.com/calendar/",
        genre="rock",
    ),
    Venue(
        slug="natural_grocery_annex",
        name="El Cerrito Natural Grocery Annex",
        neighborhood="El Cerrito",
        region="East Bay",
        # The grocery store is 10367; the Annex performance space next door is
        # 10387 (per the venue's own Tribe venue record).
        address="10387 San Pablo Ave, El Cerrito, CA",
        tz="America/Los_Angeles",
        website_url="https://naturalgrocery.com/annex/",
        # The scraper reads the company-wide Tribe Events REST API and keeps
        # only events at the Annex — see scrapers/natural_grocery_annex.
        calendar_url="https://naturalgrocery.com/events/",
        genre="jazz",
    ),
    Venue(
        slug="madrone_art_bar",
        name="Madrone Art Bar",
        neighborhood="NoPa",
        region="SF",
        address="500 Divisadero St, San Francisco, CA",
        tz="America/Los_Angeles",
        website_url="https://madroneartbar.com",
        # The scraper reads the site's Tribe Events REST API — see
        # scrapers/madrone_art_bar.
        calendar_url="https://madroneartbar.com/calendar/",
        # Funk/soul/disco DJ parties + live bands; no single genre lean.
        genre="eclectic",
    ),
    Venue(
        slug="boom_boom_room",
        name="Boom Boom Room",
        neighborhood="Fillmore",
        region="SF",
        address="1601 Fillmore St, San Francisco, CA",
        tz="America/Los_Angeles",
        website_url="https://boomboomroom.com",
        calendar_url="https://boomboomroom.com/events/",
        genre="funk",
    ),
]


def seed(conn: sqlite3.Connection | None = None) -> None:
    """Upsert the seed venues. Opens the default DB if no connection is given
    (and closes it again); pass a connection in tests to reuse it."""
    own_conn = conn is None
    if conn is None:
        conn = db.connect()
    try:
        for venue in SEED_VENUES:
            venues_repo.upsert(conn, venue)
    finally:
        if own_conn:
            conn.close()


if __name__ == "__main__":
    seed()
