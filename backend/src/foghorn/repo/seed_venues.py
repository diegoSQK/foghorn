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
        slug="medicine_for_nightmares",
        name="Medicine for Nightmares",
        neighborhood="Mission",
        region="SF",
        address="3036 24th St, San Francisco, CA",
        tz="America/Los_Angeles",
        website_url="https://medicinefornightmares.com",
        # Squarespace ?format=json events collection; the bookstore's calendar
        # mixes the "Other Dimensions in Sound" creative-music series with
        # non-music programming — see scrapers/medicine_for_nightmares.
        calendar_url="https://medicinefornightmares.com/events",
        genre="jazz",
    ),
    Venue(
        slug="piedmont_piano",
        name="Piedmont Piano Company",
        neighborhood="Uptown",
        region="East Bay",
        address="1728 San Pablo Ave, Oakland, CA",
        tz="America/Los_Angeles",
        website_url="https://piedmontpiano.com",
        # Squarespace ?format=json calendar collection — see
        # scrapers/piedmont_piano.
        calendar_url="https://piedmontpiano.com/calendar",
        genre="jazz",
    ),
    Venue(
        slug="center_for_new_music",
        name="Center for New Music",
        neighborhood="Tenderloin",
        region="SF",
        address="55 Taylor St, San Francisco, CA",
        tz="America/Los_Angeles",
        website_url="https://centerfornewmusic.com",
        # Server-rendered /event/ listing (custom post type; the RSS feed has
        # no event dates) — see scrapers/center_for_new_music.
        calendar_url="https://centerfornewmusic.com/event/",
        # Contemporary/experimental/new-music programming.
        genre="eclectic",
    ),
    Venue(
        slug="the_back_room",
        name="The Back Room",
        neighborhood="Downtown Berkeley",
        region="East Bay",
        address="1984 Bonita Ave, Berkeley, CA",
        tz="America/Los_Angeles",
        website_url="https://backroommusic.com",
        # Humanitix collection: JSON-LD + the tRPC events endpoint behind the
        # "Load more" button — see scrapers/the_back_room.
        calendar_url="https://collections.humanitix.com/the-back-room-calendar",
        # Acoustic listening room: jazz, folk, classical, bluegrass.
        genre="eclectic",
    ),
    Venue(
        slug="guild_theatre",
        name="Guild Theatre",
        neighborhood="Menlo Park",
        region="Peninsula",
        address="949 El Camino Real, Menlo Park, CA",
        tz="America/Los_Angeles",
        website_url="https://guildtheatre.com",
        # The homepage IS the calendar (JSON-LD blocks + card markup times);
        # /events 404s — see scrapers/guild_theatre.
        calendar_url="https://guildtheatre.com/",
        genre="eclectic",
    ),
    Venue(
        slug="fox_theater_oakland",
        name="Fox Theater Oakland",
        neighborhood="Uptown",
        region="East Bay",
        address="1807 Telegraph Ave, Oakland, CA",
        tz="America/Los_Angeles",
        website_url="https://thefoxoakland.com",
        # Server-rendered APE listing — see scrapers/fox_theater_oakland
        # (+ _ape_listing helper, shared with the Greek).
        calendar_url="https://thefoxoakland.com/listing/",
        genre="rock",
    ),
    Venue(
        slug="greek_theatre_berkeley",
        name="Greek Theatre Berkeley",
        neighborhood="UC Berkeley",
        region="East Bay",
        address="2001 Gayley Rd, Berkeley, CA",
        tz="America/Los_Angeles",
        website_url="https://thegreekberkeley.com",
        calendar_url="https://thegreekberkeley.com/event-listing/",
        genre="rock",
    ),
    Venue(
        slug="the_independent",
        name="The Independent",
        neighborhood="NoPa",
        region="SF",
        address="628 Divisadero St, San Francisco, CA",
        tz="America/Los_Angeles",
        website_url="https://www.theindependentsf.com",
        # The homepage renders the full TicketWeb "tw-" show list server-side
        # — see scrapers/the_independent (+ _ticketweb_calendar helper).
        calendar_url="https://www.theindependentsf.com/",
        genre="rock",
    ),
    Venue(
        slug="cafe_du_nord",
        name="Cafe du Nord",
        neighborhood="Castro",
        region="SF",
        address="2174 Market St, San Francisco, CA",
        tz="America/Los_Angeles",
        website_url="https://cafedunord.com",
        # Same TicketWeb template, paginated; also bills shows at the attached
        # Swedish American Hall — see scrapers/cafe_du_nord.
        calendar_url="https://cafedunord.com/calendar/",
        genre="rock",
    ),
    Venue(
        slug="dna_lounge",
        name="DNA Lounge",
        neighborhood="SoMa",
        region="SF",
        address="375 Eleventh St, San Francisco, CA",
        tz="America/Los_Angeles",
        website_url="https://www.dnalounge.com",
        # The venue's self-published iCalendar feed — see scrapers/dna_lounge.
        calendar_url="https://cdn.dnalounge.com/calendar/dnalounge.ics",
        genre="electronic",
    ),
    Venue(
        slug="cornerstone_berkeley",
        name="Cornerstone Berkeley",
        neighborhood="Downtown Berkeley",
        region="East Bay",
        address="2367 Shattuck Ave, Berkeley, CA",
        tz="America/Los_Angeles",
        website_url="https://www.cornerstoneberkeley.com",
        # Server-rendered JSON-LD Event blocks + Tixr offers; start times
        # paired from the card markup — see scrapers/cornerstone_berkeley.
        calendar_url="https://cornerstoneberkeley.com/events/",
        genre="rock",
    ),
    Venue(
        slug="great_american_music_hall",
        name="Great American Music Hall",
        neighborhood="Tenderloin",
        region="SF",
        address="859 O'Farrell St, San Francisco, CA",
        tz="America/Los_Angeles",
        website_url="https://gamh.com",
        # SeeTickets white-label calendar (GAMH markup flavor) — see
        # scrapers/great_american_music_hall.
        calendar_url="https://gamh.com/calendar/",
        # Indie/roots/rock plus jazz and soul bookings; no single lean.
        genre="eclectic",
    ),
    Venue(
        slug="the_chapel",
        name="The Chapel",
        neighborhood="Mission",
        region="SF",
        address="777 Valencia St, San Francisco, CA",
        tz="America/Los_Angeles",
        website_url="https://thechapelsf.com",
        # SeeTickets white-label calendar (same flavor as Rickshaw Stop);
        # covers the whole complex incl. Curio + outdoor stage — see
        # scrapers/the_chapel.
        calendar_url="https://thechapelsf.com/calendar/",
        genre="rock",
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
        slug="yoshis",
        name="Yoshi's",
        neighborhood="Jack London Square",
        region="East Bay",
        address="510 Embarcadero West, Oakland, CA",
        tz="America/Los_Angeles",
        website_url="https://yoshis.com",
        # The scraper POSTs the fullCalendar JSON feed behind this page (one
        # entry per set) and joins prices from the HTML — see scrapers/yoshis.
        calendar_url="https://yoshis.com/events/default/calendar",
        genre="jazz",
    ),
    Venue(
        slug="california_jazz_conservatory",
        name="California Jazz Conservatory",
        neighborhood="Downtown Berkeley",
        region="East Bay",
        address="2087 Addison St, Berkeley, CA",
        tz="America/Los_Angeles",
        website_url="https://jazzschool.org",
        # The school's dedicated public-concerts subdomain (classes never
        # appear there) — see scrapers/california_jazz_conservatory.
        calendar_url="https://concerts.jazzschool.org/",
        genre="jazz",
    ),
    Venue(
        slug="ivy_room",
        name="Ivy Room",
        neighborhood="Albany",
        region="East Bay",
        address="860 San Pablo Ave, Albany, CA",
        tz="America/Los_Angeles",
        website_url="https://www.ivyroom.com",
        # The scraper reads Venuepilot's public GraphQL API (the site itself
        # is a JS widget shell) — see scrapers/ivy_room.
        calendar_url="https://www.ivyroom.com/shows",
        genre="rock",
    ),
    Venue(
        slug="gilman_924",
        name="924 Gilman",
        neighborhood="West Berkeley",
        region="East Bay",
        address="924 Gilman St, Berkeley, CA",
        tz="America/Los_Angeles",
        website_url="https://www.924gilman.org",
        # The collective's ShowSlinger ticketing listing (the Wix site's
        # calendar is client-rendered) — see scrapers/gilman_924.
        calendar_url="https://app.showslinger.com/e1/460/924-gilman/8c96699fd6",
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
    Venue(
        slug="bimbos_365",
        name="Bimbo's 365 Club",
        neighborhood="North Beach",
        region="SF",
        address="1025 Columbus Ave, San Francisco, CA",
        tz="America/Los_Angeles",
        website_url="https://bimbos365club.com",
        # TicketWeb "tw-" template — see scrapers/bimbos_365.
        calendar_url="https://bimbos365club.com/shows/",
        genre="eclectic",
    ),
    Venue(
        slug="neck_of_the_woods",
        name="Neck of the Woods",
        neighborhood="Inner Richmond",
        region="SF",
        address="406 Clement St, San Francisco, CA",
        tz="America/Los_Angeles",
        website_url="https://www.neckofthewoodssf.com",
        # TicketWeb "tw-" template on the homepage — see
        # scrapers/neck_of_the_woods.
        calendar_url="https://www.neckofthewoodssf.com/",
        genre="rock",
    ),
    Venue(
        slug="august_hall",
        name="August Hall",
        neighborhood="Union Square",
        region="SF",
        address="420 Mason St, San Francisco, CA",
        tz="America/Los_Angeles",
        website_url="https://www.augusthallsf.com",
        # TicketWeb "tw-" template + per-event pages for times — see
        # scrapers/august_hall.
        calendar_url="https://www.augusthallsf.com/events/",
        genre="rock",
    ),
    Venue(
        slug="the_warfield",
        name="The Warfield",
        neighborhood="Mid-Market",
        region="SF",
        address="982 Market St, San Francisco, CA",
        tz="America/Los_Angeles",
        website_url="https://www.thewarfieldtheatre.com",
        # carbonhouse (AEG) static blocks + events_ajax lazy-load feed — see
        # scrapers/the_warfield.
        calendar_url="https://www.thewarfieldtheatre.com/events",
        genre="rock",
    ),
    Venue(
        slug="thee_stork_club",
        name="Thee Stork Club",
        neighborhood="Uptown",
        region="East Bay",
        address="380 12th St, Oakland, CA",
        tz="America/Los_Angeles",
        website_url="https://theestorkclub.com",
        # SeeTickets white-label (Rickshaw flavor) — see
        # scrapers/thee_stork_club.
        calendar_url="https://theestorkclub.com/calendar/",
        # Punk/goth/DJ booking — "rock" in the coarse vocabulary.
        genre="rock",
    ),
    Venue(
        slug="uc_theatre",
        name="The UC Theatre",
        neighborhood="Downtown Berkeley",
        region="East Bay",
        address="2036 University Ave, Berkeley, CA",
        tz="America/Los_Angeles",
        website_url="https://www.theuctheatre.org",
        # Static Webflow listing with per-event genre — see
        # scrapers/uc_theatre.
        calendar_url="https://www.theuctheatre.org/events/",
        genre="eclectic",
    ),
    Venue(
        slug="club_deluxe",
        name="Club Deluxe",
        neighborhood="Haight",
        region="SF",
        address="1511 Haight St, San Francisco, CA",
        tz="America/Los_Angeles",
        website_url="https://thedeluxesf.com",
        # Server-rendered Simple Calendar (simcal) list — see
        # scrapers/club_deluxe.
        calendar_url="https://thedeluxesf.com/calendar/",
        genre="jazz",
    ),
    Venue(
        slug="club_fox",
        name="Club Fox",
        neighborhood="Redwood City",
        region="Peninsula",
        address="2209 Broadway, Redwood City, CA",
        tz="America/Los_Angeles",
        website_url="https://clubfoxrwc.com",
        # Hand-authored homepage show blocks + Eventbrite links — see
        # scrapers/club_fox.
        calendar_url="https://clubfoxrwc.com/",
        genre="eclectic",
    ),
    Venue(
        slug="mystic_theatre",
        name="Mystic Theatre",
        neighborhood="Petaluma",
        region="North Bay",
        address="23 Petaluma Blvd N, Petaluma, CA",
        tz="America/Los_Angeles",
        website_url="https://mystictheatre.com",
        # SeeTickets white-label — see scrapers/mystic_theatre.
        calendar_url="https://mystictheatre.com/calendar/",
        genre="rock",
    ),
    Venue(
        slug="sweetwater_music_hall",
        name="Sweetwater Music Hall",
        neighborhood="Mill Valley",
        region="North Bay",
        address="19 Corte Madera Ave, Mill Valley, CA",
        tz="America/Los_Angeles",
        website_url="https://sweetwatermusichall.org",
        # Rockhouse/etix list view, server-rendered — see
        # scrapers/sweetwater_music_hall.
        calendar_url="https://sweetwatermusichall.org/events/?view=list",
        # Roots/rock/reggae/bluegrass/tributes.
        genre="eclectic",
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
