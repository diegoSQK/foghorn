# foghorn Shipped Work

Chronological record of completed work — what landed, when, and why. Each entry preserves the narrative context that informed the design so it stays available as scar tissue when scoping new work.

`PROJECT_PLAN.md` is the active doc: what's in flight, queued, and deferred. When a new phase/feature ships, its spec moves here and the active doc collapses to a one-line status with a link into this file. Read this file on demand when you need detail on past work; the active doc is the daily read.

Ordering: newest at top. When adding a new entry, insert it at the top of the file. Older entries preserve their original recording order — when reorganizing, prefer "insert at top of recent block" over "deeply reorder existing history."

---

## Venue size tier — making the coverage question answerable (September 2026)

foghorn's catalogue spans Bird & Beckett's back room to Bill Graham Civic, a
~100x range in capacity, with nothing in the model distinguishing them. The
cost showed up twice: the August 2026 venue sweep closed with a documented gap
list that a 7,000-seat room in the middle of San Francisco never appeared in,
and the calendar interleaves a bookshop jazz trio with an arena EDM bill with
no way to tell them apart.

`venues.size_tier` is four editorial tiers — `listening_room`, `club`,
`theatre`, `large` — assigned across all 90 seeded venues, surfaced on
`GET /api/venues` and named in the MCP `list_venues` description so the
distribution is queryable conversationally.

**Deliberately no filter facet.** The filter bar already carries region,
neighborhood, genre, origin, type, time-of-day, two watchlists and the
long-tail toggle, and three recent PRs were about managing that crowding.
Whether size earns a place there is a decision to make after seeing the
distribution, not before — a test pins that `/api/shows` gained no size
parameter.

### The tiers live in one table, not on 90 rows

`SIZE_TIERS` is a dict keyed by slug rather than a field on each `Venue(...)`
entry, because the *distribution* is the deliverable: the coverage question is
answerable by reading the table, and a gap is visible at a glance. A test
asserts the table covers the seed list exactly in both directions, so a venue
added without a tier — or a tier left behind after a venue is removed — fails
the gate rather than drifting.

They are judgments about the kind of room, not seat counts, and the awkward
ones carry their reasoning: Kuumbwa is a listening room in feel but well past
the band; Mills' Littlefield is a 350-seat recital hall where `club` is the
least-wrong bucket rather than a description; Fox Oakland and the Paramount
sit right on the theatre/large line. SFJAZZ is tiered by Miner Auditorium and
notes the compromise — the Joe Henderson Lab is a listening room under the
same slug, and tiers are venue-level.

### What the distribution says

| region | listening_room | club | theatre | large | total |
| --- | --- | --- | --- | --- | --- |
| SF | 10 | 20 | 14 | 2 | 46 |
| East Bay | 5 | 10 | 6 | 1 | 22 |
| North Bay | 0 | 3 | 3 | 0 | 6 |
| Santa Cruz | 1 | 4 | 1 | 0 | 6 |
| Peninsula | 1 | 2 | 2 | 0 | 5 |
| South Bay | 1 | 3 | 0 | 1 | 5 |
| **all** | **18** | **42** | **26** | **4** | **90** |

Two findings worth acting on, which is what the ticket asked the data to
produce:

- **South Bay has no theatre-tier venue at all** — one listening room, three
  clubs, and Mountain Winery. San Jose has several rooms in that band, so this
  is a real gap rather than an artefact of the region being small.
- **The `large` tier is four venues across the entire Bay Area.** The ticket
  already named the Cow Palace, Chase Center, the Palace of Fine Arts and Fort
  Mason's halls as invisible; the table confirms civic-scale coverage is thin
  everywhere outside SF and the East Bay.

Filed as a follow-up rather than widened into this PR.


## Bird & Beckett's non-shows: the venue's own tags, with the heuristic behind them (September 2026)

The shop's calendar carries more than gigs, and two entries that aren't events
at all were being ingested as shows: **"closed for Thanksgiving"** and
**"Glen Park Night Market"**. The `_NON_MUSIC_SIGNALS` keyword list — which
already caught poetry readings and author talks — had nothing to say about a
closure notice or a street fair.

#122 had just put Tribe's REST feed in place, and it carries the venue's own
categories (`Live Music`, `Poetry Reading`, `Talks / Interviews`,
`Book Event`, `Jam Session`). The obvious move was to replace the keyword
heuristic with them.

### Measuring first killed the obvious move

Pulling the live feed: **the two offending entries have no Tribe event at
all.** Categories alone can't fix the reported bug, because the rows that
caused it are exactly the ones Tribe doesn't carry — 4 of 51 shows in the
window have no match.

That also settles the design's real hazard. Reading "no category" as "not a
show" would drop those 4, including **Will Bernard + Beth Custer**, a real
November date. The fail-open property #122 established — a Tribe gap must
never reduce the show count — has to survive here too.

But categories genuinely earn their place on the other side: they drop two
events the keyword list misses and no title heuristic could ever catch, since
both read like gigs —

- *Amy O'Hair presents "History Walks in Sunnyside"* → `Talks / Interviews`
- *All About San Francisco Stairways w/Mary Burk* → `Book Event`

### What shipped

A category decides when there is one; the keyword list handles everything
else, and gained `"closed for"` and `"night market"`. Both are phrases rather
than bare words on purpose: "closed" and "market" are each plausible inside a
band name, and the whole point of this ticket was a filter that over-reached
in the other direction.

`Live Music` and `Jam Session` mark a show — a jam is programming foghorn
wants, and the event-type inference tags it separately.

### Verification

Live: **51 → 47 shows**, dropping exactly the four intended — the two reported
non-events by keyword, the two talks by category. `Will Bernard + Beth Custer`
survives with no Tribe match, and with the index removed entirely (the outage
path) the filter degrades to exactly the keyword heuristic, still dropping the
two non-events.


## The reaper stops being scoped to a venue (September 2026)

`reap_stale` was scoped to `(venue_id, source='scrape', span)`. That encoded an
assumption — **exactly one scraper is authoritative per venue** — which was
true only because the registry enforced it structurally, being a
`dict[venue_slug, callable]`.

It is false the moment a presenter books a room it doesn't own. SFJAZZ's feed
lists the two nights it presents at the Paramount; register it under
`paramount_theatre_oakland` and its run returns only those two, so the reaper
concludes every *other* Paramount show in the span is dead.

The granularity had been worked around twice, and the workarounds cost shows:

1. **`sfjazz.scrape_center()`** existed only for this, dropping every off-site
   SFJAZZ date. That is how a Julian Lage Quartet date at Davies went missing
   despite Lage being on the watchlist.
2. **`the_mellow`** registered one scraper twice — `scrape_haight` and
   `scrape_boathouse`, each filtering the same fetch — explicitly "so the
   nightly run's prune stays scoped to the venue it actually has authoritative
   listings for."

### What changed

`shows.source_scraper` records which scraper produced a row, and the reaper
matches on it: **a scraper can only ever delete rows it previously
contributed.** Sharing a venue becomes safe, so both workarounds are gone —
SFJAZZ registers wholesale and its off-site dates land at their host venues,
and The Mellow is one entry covering both rooms.

The registry needed its second dimension, and it turned out to need less than
expected: every `ScrapedShow` already carries its own `venue_slug`, so the
runner **groups a scraper's output by the venue each show names** rather than
assuming the registry key. The key becomes a scraper identity that happens to
equal the venue slug in the 1:1 case, so none of the ~85 existing entries
changed.

### What the rehearsal caught

Attributing pre-existing rows looked trivial — registration was 1:1, so stamp
each venue's rows with its own slug. Run against a copy of the live DB, that
stranded **76 Blue Heron Boathouse rows**: collapsing The Mellow's dual
registration means the boathouse's contributor is `the_mellow_haight`, not its
own slug, so nothing would ever have matched them — and a NULL
`source_scraper` is deliberately never swept either. They'd have lingered
forever as duplicates, which is precisely the failure the reaper exists to
prevent.

The fix is the coverage declaration the ticket asked for: `SCRAPER_VENUES`,
populated only for the two multi-venue scrapers and derived from their own
routing tables so it can't drift. Attribution then goes by venue coverage
rather than by registry id. Second run: **5,491 of 5,491 scraped rows
attributed, zero unattributed, zero rows lost.**

### The cost, and the backstop

Per-contributor scoping means a scraper that stops running never reaps its
rows again — deleted, renamed, or dropped from the registry, its shows linger.
Stale rows beat missing ones, but it is still a failure, so `reap_orphaned`
sweeps rows whose contributor is no longer registered, after a deliberately
generous 30 days: a scraper that is merely broken for a fortnight must not
have its venue's calendar deleted. Rows with a NULL contributor are left
alone — deleting what you can't attribute is the wrong instinct.

### A correction

Shipping #128 and #129 I argued this ticket's evidence was thinner than it
claimed — that #128 dissolved into the aggregator tier rather than needing
prune changes, leaving "really one case". **That was wrong**: I had missed
The Mellow's dual registration, which is a second, independent structural
workaround that has nothing to do with #128. The count in the ticket was
right.


## Bill Graham Civic — the Civic Center gap was civic-scale rooms, not geography (September 2026)

Bill Graham Civic Auditorium was absent from foghorn entirely — not seeded, not
quarantined, `grep -ri "bill graham"` returned nothing. A ~7,000-capacity room
in the middle of Civic Center booking national touring acts continuously.

The diagnosis in the ticket was the useful part: the corridor was already well
covered for *clubs* (SFJAZZ, Mr. Tipple's, Rickshaw Stop, Great American, the
Warfield, the Regency, Audium, Old First) while the only large rooms were the
three War Memorial halls, all seeded `classical` and all fed from presenter
feeds. The gap was a **size of room**, not a neighbourhood.

### One template, two generations

The venue is Another Planet Entertainment, and foghorn already had
`scrapers/_ape_listing.py` shared by Fox Oakland and the Greek. The ticket
flagged honestly that its recon couldn't see class attributes and said to treat
"the classes didn't appear" as *unobserved*, not absent — then gave the right
instruction for either outcome.

It's a variant. Bill Graham runs a newer generation of the same theme:
`article.event` blocks instead of `div.mix.detail-information`, support in
`div.bottomline` instead of `div.support`, an `a.more-info` event link, and —
better than the old one — a `p.event__start-date` whose `content` is already a
sortable `2026-09-19 19:00` rather than free text.

Per the ticket, `_ape_listing` was extended rather than forked. The four
differing selectors live in one `_SELECTORS` table and everything else is
shared, because the *rules* (cancelled shows stay listed, non-music bookings
need dropping, support lines carry italic annotations) belong to the template
rather than the venue, and two copies would drift. Blocks are paired with the
selector set that reads them rather than the page being classified up front,
so a theme caught mid-migration parses rather than coming back half-empty.

### Verification

21 shows off the live calendar, chronological, with per-show `source_url` and
Ticketmaster links. Every acceptance case checked: Bonnie Raitt 10/10 carries
Jon Cleary & The Absolute Monster Gentlemen as *support* rather than
concatenated into the headliner; Steve Aoki's three openers split correctly on
`<br>`; the two Sara Bareilles nights are two rows; sold-out shows (Bareilles,
Steve Lacy) still ingest; a rescheduled show is kept on its new date while a
cancelled one is dropped.

Fox Oakland and the Greek were re-verified unchanged after the helper was
extended, as the ticket required.

The **War Memorial Opera House** half of this ticket had already landed with
the War Memorial licensee feed, which both seeds the row and fills it — 44
Opera House shows rather than the empty row this ticket anticipated.


## A deliberate drop needs telemetry, or it's silent data loss (September 2026)

`scrapers/sfjazz.scrape_center()` drops SFJAZZ's off-site dates on purpose and
for a good reason — the nightly `prune=True` would otherwise reap the host
venue's own programming. Its docstring justified that by saying those dates
"arrive through the host venue's own scraper."

**Nothing checked that, and when it was wrong the show vanished.** It held for
the Paramount and the UC Theatre. It was false for Davies, whose only source
was a presenter feed that can't see rentals, so a Julian Lage date SFJAZZ
presented there was dropped and appeared nowhere. It surfaced because a friend
sent Diego the link.

The pointed detail: the scraper *already* warned about **unmapped** locations,
precisely so new programming gets a human glance. Davies is mapped, so it
stayed quiet. The mapped-and-deliberately-dropped path was the one with no
telemetry, and it was the one that lost a show. An exception handler covers a
run that broke; nothing covered a run that worked exactly as designed and still
dropped something.

### What shipped

`scrapers/diagnostics.py` — a small channel for a scraper to report what a
*successful* run still dropped. Notes ride the existing `scrape_runs` record
and surface on `GET /api/health/scrape` beside the error list, deliberately
*not* as errors: a considered drop shouldn't make a venue look broken.

SFJAZZ now reports its off-site drops per host, and separates the hosts that
have **no scraper of their own** — because a Paramount date is fine (its own
scraper lists it) while a Grace Cathedral date is a show foghorn simply loses:

```
sfjazz: 4 off-site date(s) not ingested: davies_symphony_hall 2,
  grace_cathedral 1, paramount_theatre_oakland 1; no scraper covers
  grace_cathedral 1
```

The channel is generic rather than SFJAZZ-specific, because the shape isn't:
any scraper that knowingly narrows its output has the same exposure. It's a
`ContextVar`, since the nightly run is on an APScheduler background thread
while `make scrape` is on the main one.

**Observability only.** What gets ingested is byte-identical; a test pins that
`scrape_center()` still returns exactly the in-house shows.

### Note for the PM thread

The ticket flagged this as the third case this quarter to hit per-venue prune
granularity and suggested filing the reaper rescope. Having now done #128, I'd
revise that count down: #128 dissolved into the aggregator tier rather than
needing prune changes, so the live evidence is **this** case plus
`scrape_center()`'s existence — which are really one case, the same scraper.
Worth waiting for a third that doesn't dissolve.


## War Memorial licensee calendar — the halls stop being one company's season (September 2026)

A Julian Lage Quartet date at Davies on 2026-10-19 was missing, with Lage on
the watchlist and Davies a seeded venue. It fell through a structural gap:
SFJAZZ presented it off-site, and `sfjazz.scrape_center()` drops off-site
dates by design (registering SFJAZZ under a host venue would let the nightly
`prune=True` reap every *other* show at that host). Its stated mitigation is
that off-site dates "arrive through the host venue's own scraper" — which
holds for the Paramount and the UC Theatre, and silently fails for any host
whose only source is a presenter feed.

Davies, Herbst and the Wilsey Atrium were **modelled as venues but sourced
from presenters**. A hall was therefore only ever as complete as one resident
company's season, and every rental — jazz presenters, touring recitals,
film-with-orchestra one-offs — was invisible.

### The source

`sfwarmemorial.org/calendar/` is the building operator's own record. The War
Memorial is the City department that rents these halls, which is exactly the
authority wanted: it covers **licensees**, not one company.

The ticket's recon said the events were JS-rendered and pointed at JetEngine
Custom Content Types as the likely path. Both turned out to be wrong in a
useful way. There is no events post type, `tribe/events/v1` 404s, and there is
no CCT — but the events aren't fetched at all. They're server-rendered into
the page as a `var eventsData = [...]` array by the building's booking system,
with Momentus/Ungerboeck field names (`arrangement_customer_entity_full_name`,
`activity_detail`) showing through. **A plain HTTP GET is the whole data
path**; Phase 1's no-headless bar is cleared with room to spare. 445 bookings,
2026-06-01 → 2027-05-29, carrying hall, presenter, genre and a ticket URL.

### The prune hazard dissolves rather than being solved

The ticket spent its longest section on the reaper: registering a Davies
scraper with `prune=True` would reap the Symphony aggregator's Davies rows —
`sfjazz`'s hazard pointed the other way. It offered two options, declare this
source authoritative, or scope prune per contributing source.

Neither was needed. **The aggregator tier already has the right shape**: it
ingests per event, never prunes, and resolves each event's hall from a
free-text venue name — which is precisely what a multi-hall building feed
produces. Landing it there means the hazard never arises. A test pins the
registration so a later move into `REGISTERED_SCRAPERS` fails loudly.

So this ticket does *not* add a third data point for per-source prune
scoping. Two of the three cases the tickets cite have architectural answers;
the remaining one is #129's.

### Two things measurement changed

**Symphony dates are dropped at the source.** The building sees the Symphony's
season too, so ingesting naively would have double-listed it. Measured against
live data first: of 171 Symphony dates, 86 canonicalize identically to the
existing rows (harmless), but **19 carry a different billing at the same
date and time** and would have landed as visible duplicates — the booking
record says "DOCTOR ATOMIC AND MENDELSSOHN VIOLIN CONCERTO" where the
Symphony's own feed says "Elim Chan conducts Adams and Mendelssohn". The
presenter's copy is better, and the ticket's own acceptance asks for
*non-Symphony* licensee events, so the feed defers.

**A second deferral rule came out of the rehearsal.** Ingesting onto a copy of
the live DB still produced 2 duplicates at Herbst, because
`ingest._is_duplicate` deliberately ignores rows whose source is `aggregator`
— two presenter feeds listing one hall on one night are usually two real
events, and suppressing one would lose a show. That reasoning doesn't hold for
a *building* feed, where an existing row for the same slot is almost certainly
the same booking, better described. `DEFER_TO_ALL_SOURCES` is the opt-in;
everything else keeps the old behaviour, and a test pins that too.

### Also

The War Memorial Opera House **was not a seeded venue at all** — the ticket
assumed it was. SF Opera's entire season and every Opera House rental had
nowhere to land; it's seeded here. And `sfwmpac.org`, still seeded as Herbst's
website and calendar URL, no longer resolves (DNS failure, confirmed
2026-09-18); both now point at `sfwarmemorial.org`.

Genre filtering rides the calendar's own facet, which is reliable for
everything but Film — that covers both plain screenings and live-orchestra
performances, so Film is admitted only on an explicit in-concert /
with-orchestra signal in the billing. Dance (the Ballet's season), ceremonies,
talks and receptions are dropped, as are the two back-of-house rooms.

### Verification

Rehearsed on a copy of the live DB: **123 new shows across the four halls, 0
pre-existing rows lost, 0 duplicate slots introduced** (the 3 remaining
same-slot collisions at Davies pre-date this change — the Symphony feed
duplicating itself, worth its own look). Davies gains 10 rentals, Herbst 65,
the Opera House 44, the Wilsey 4. The Julian Lage date is present at
2026-10-19 20:00 and matches the `julian lage` follow.

---

## Uniqueness-gated surname resolution — following a name that's billed by surname (September 2026)

A Lisa Mezzacappa show didn't reach the watchlist. It was in foghorn and
correctly ingested — `Ochs/Johnston/Mezzacappa/Davis` at Medicine for
Nightmares — but the follow is `lisa mezzacappa`, and token-bag matching needs
*every* token of the follow to appear in the performer name. `lisa` isn't in
that billing, so no match, silently.

The matcher wasn't broken in general. Every Mezzacappa show billed with her
full name matched fine. It failed on exactly one pattern: **collectives billed
by surname only**, which is the house style of the creative-music scene this
product exists to cover. A user-visible inconsistency made it worse —
`performer_query=mezzacappa` *did* find the show, because a one-token query is
a subset of the billing. Searching for her worked while following her didn't,
and the failing direction was the one with the alerting job.

### Why the obvious fix is wrong

Relax matching so a performer name that is a *subset* of the follow also
counts, and `mezzacappa` matches `lisa mezzacappa`. It also makes a followed
"Miles Davis" match the bare `Davis` on this very bill, and on every other bill
with a Davis on it. **A silent false positive in a digest is worse than a
miss**, because it costs trust in every other row — so the match rule was left
exactly as it was.

### What shipped instead

Two gaps, both required, neither sufficient alone:

**1. The billing is now parsed.** `ingest/billing.py` splits multi-artist
billings into the musicians they name — slash-separated surnames, comma lists
with role and instrument annotations, parenthesised personnel. The members
become *additional* `show_performers` rows: the display string is never
rewritten (per `AGENTS.md` → Conventions) and `headliner_canonical` keeps the
whole billing, so the dedupe natural key is untouched and no
`event_type_overrides` rule is orphaned.

**2. Bare surnames resolve against the catalogue, gated on uniqueness.**
`ingest/surnames.py` asks how many known people bear a surname: exactly one →
link the show to that person; two or more → leave it bare; none → leave it
bare and never invent anyone. Ambiguity stops being a judgement call and
becomes a fact measurable from the `performers` table, and the property
improves as the catalogue grows — a surname that gains a second bearer
silently stops resolving, which is the safe direction to fail.

**The reusable lesson is the gate**, and the same question will come back for
initials and nicknames: *don't loosen the matcher, resolve the identity, and
refuse when the data can't tell you.*

### The load-bearing detail nobody would guess

Who counts as "known" decides everything, and the naive answer is wrong. The
`performers` table is full of rows that merely *end* in a surname — "The Rob
Reich Swings Left Legacy Band Featuring Darren Johnston" is not a person called
Johnston. Counting those made `johnston` look ambiguous (blocking a correct
resolution) and would let a band become the unique bearer of a surname nobody
on the bill has. The index is therefore built only from *person-shaped* names:
two or three tokens, no collective markers, no digits.

### Parsing is biased to under-split, deliberately

A missed personnel list costs one watchlist match. A wrong split invents a
performer that pollutes the surname index, where a bogus name can *block* a
correct resolution or become the unique answer. So the parser refuses whenever
it isn't confident.

That bias was set empirically, by dry-running the parser over all 6,194 live
billings before wiring it to anything. The first draft split **179** of them —
including `Earth, Wind & Fire`, `Sincerely, Yours`, `Michael Wolff, solo` and
`TOMMY EMMANUEL, CGP` — while *failing* the Marina Crouse case the ticket
required. Every one of those would have minted a phantom performer. Tightening
(comma lists need three members or annotation evidence; `w/` is "with", not a
delimiter; mixed separators and bracket structure are vetoes; `Jazz/Latin` and
`AC/DC` are explicit refusals) brought it to **54 splits, 0.9%**, with all four
required shapes parsing. The adversarial cases in
`tests/test_billing_parse.py` are all real catalogue strings that a looser
parser got wrong.

### Convergence, and why one pass isn't enough

Parsing a billing is what *creates* the person a later bare surname resolves
to. `Larry Ochs` did not exist as a performer before this shipped — he was
buried inside `Larry Ochs, Ben Davis, Darren Johnston, Lisa Mezzacappa -
Subconscious Life` — so `ochs` had **zero** known bearers. Resolution therefore
lags parsing by one pass.

Inline resolution at ingest handles the ordinary case, since each ingest call
rebuilds the index. Past shows never re-scrape though, and they are exactly
what makes a surname known, so `cli/relink_performers.py` re-walks the stored
catalogue and runs to a fixpoint. On live data it converges on pass 3 and is a
no-op thereafter.

### Verification

Rehearsed against a copy of the live DB before anything touched the real one.
Show ids, show count, headliner canonicals, per-venue counts and
`event_type_overrides` all byte-identical across the backfill; 135 parsed links
and 10 inferred links added across 5,574 shows.

The reported show now reads:

```
[billed  ] Ochs/Johnston/Mezzacappa/Davis     <- display string unchanged
[inferred] Larry Ochs
[parsed  ] Ochs
[inferred] Darren Johnston
[parsed  ] Johnston
[parsed  ] Mezzacappa
[inferred] Lisa Mezzacappa                    <- the follow now matches
[parsed  ] Davis                              <- stays bare, correctly
```

And the acceptance question the ticket asked to be answered explicitly:
`ochs` → **Larry Ochs**, `johnston` → **Darren Johnston**, `mezzacappa` →
**Lisa Mezzacappa**, `davis` → **ambiguous, stays bare** (five known bearers:
Ben, Brittany, Evelyn, Jamie, Max). Partial resolution on one bill is the
correct outcome, not a failure.

---

## Bird & Beckett details links — `.ics` for billing, Tribe for metadata (September 2026)

Every Bird & Beckett row carried the same `source_url`, so the "details" link
on all ~50 shows landed on the generic `/events/` page instead of the show you
clicked. The scraper stamped a module constant on every event, because the
`.ics` feed it reads has no per-event link and there was nothing better at the
time.

There is now: B&B runs The Events Calendar, and `/wp-json/tribe/events/v1/events`
answers a plain HTTP client with each event's own `url` and `cost`.

### The interesting part: why we joined instead of switching

foghorn already has seven scrapers on this exact Tribe endpoint, and
`kuumbwa_jazz_center.parse_events` has the three lines this needed. The obvious
move was to swap B&B onto Tribe like the rest. **That would have been a
regression**, because the two feeds disagree about what a "billing" is:

| Date | `.ics` (kept) | Tribe |
| --- | --- | --- |
| Sep 13 | `Vocalist Marina Crouse, with Danny Caron, guitar; and Ruth Davies, bass` | `Marina Crouse Trio` |
| Sep 15 | `Alon Nechustan Quintet` | `Alon Nechustan's Venture Bound Quintet` |

The `.ics` names the whole band; Tribe names only the act. Switching would drop
the sidemen from `headliner_raw`, so Danny Caron and Ruth Davies would stop
token-matching the watchlist — a regression in the feature the product exists
for. It would also change `headliner_canonical`, part of the dedupe natural key
`(venue_id, start_local_date, start_local_time, headliner_canonical)`,
re-ingesting every B&B row and orphaning the six venue+billing jam rules in
`event_type_overrides`.

So the split: **the `.ics` stays authoritative for what exists and how it's
billed; Tribe is a metadata lookup only**, joined on `(date, start time)`.
Explicitly *not* joined on title — the table above is exactly why that would
misfire. This is the reusable lesson, since foghorn has other venues publishing
both a Google Calendar and a Tribe feed: a second feed doesn't have to be an
either/or, and the richer *structure* isn't automatically the richer *content*.

### Verifying the join before building on it

The whole design rests on the two feeds agreeing on start times, so that got
measured across the full window before any code was written rather than
sampled: **45 of 48 `.ics` events (93.8%) found a Tribe match, with zero
`(date, time)` collisions.** The three misses are all non-shows or genuinely
absent from Tribe — "Glen Park Night Market" (a street fair), "closed for
Thanksgiving" (a closure notice that the `_NON_MUSIC_SIGNALS` heuristic doesn't
catch — filed separately), and one November show Tribe hasn't published. All
three fall back cleanly.

That gate was worth running. A join that silently no-ops for a third of the
calendar would have been invisible in the UI, which is precisely how the
original bug survived this long.

### Shape

`parse_ics` stays pure and fixture-testable — it gained an optional
`details: Mapping[tuple[date, time], EventDetails]` argument rather than a
fetch, and `scrape()` does both fetches and wires them together. On a join hit
the show takes Tribe's `url` and `cost`; on a miss it keeps the previous
behavior exactly (`/events/`, null price).

Two deliberate refusals to guess:

- **Fail open.** Any Tribe error logs and yields an empty index, so every show
  still ingests with the fallback link. A Tribe outage must never reduce a
  load-bearing venue's show count — the `.ics` is what says a show exists.
- **Collisions fall back.** More than one Tribe event on a `(date, time)` key
  drops that key rather than picking arbitrarily, and logs it. Linking half a
  calendar to the wrong page is worse than linking it to the index.

Unlike kuumbwa, birdbeckett.com has no caching proxy in front of its REST API —
it honors `per_page` / `start_date` / `page` correctly (`total: 90,
total_pages: 45` at `per_page=2`), so this scraper deliberately does *not*
cargo-cult kuumbwa's browser-UA-and-id-seen-guard workaround.

### Verification

Live run: 48 shows, 45 with per-event URLs, 44 with prices, 3 clean fallbacks.
Tonight's show resolves to `/event/eric-the-in-crowd_2026-09-11/`; Sep 12 and
Sep 13 resolve to the truncated (`rob-zuckerman`) and happy-hour
(`marina-crouse`) slug shapes, confirming the slug really isn't derivable.
Diffed against the pre-change scraper on the same live feed: **48 → 48 shows,
natural keys and billing strings byte-identical**, so no row churns and the jam
overrides stay attached.

---

## Phase 10 — MCP surface: the calendar, conversationally (August 2026)

foghorn was the last of the three fleet apps without an MCP surface. ficycle
and cadence both have one and the pattern has earned its keep: a conversational
client becomes a second front-end over the same API, good at exactly the
queries a filter bar is bad at. foghorn's own facet surface had grown rich
enough — regions, neighborhoods, genres, origin, event types, two watchlists,
the long-tail toggle, all multi-select since #108 — that composing a query by
hand across facets had become real work.

The prerequisite that had been missing was auth. #100's single-user mode closed
it: on fleet the API resolves cookie-less requests to the bootstrap admin, so
the MCP server's auth story is nearly free, admin-only writes included.

### A wrapper, not a second path

`backend/src/foghorn/mcp/server.py` is a **thin httpx wrapper over the running
FastAPI**, mirroring ficycle's `portfolio_api/mcp/server.py`. Nothing reaches
into the repo layer. That keeps one authorization story — the API's — and means
the MCP surface cannot drift from REST semantics: if a filter changes shape,
MCP changes with it or fails visibly.

`[project.scripts]` didn't exist in `backend/pyproject.toml` and now does:
`foghorn-mcp = "foghorn.mcp.server:main"`, stdio.

The base URL defaults to `http://127.0.0.1:8100` — fleet's always-on
`foghorn-api`. Deliberately not `:8000` (ficycle-api's fleet port) and not
`:9100` (foghorn's own dev-run port, #99); pointing the MCP server at either
would silently talk to the wrong app or to nothing.

### Auth, and the failure mode

No credential by default, which is exactly right under `FOGHORN_SINGLE_USER=1`.
`FOGHORN_MCP_SESSION` is the escape hatch: set it to a `foghorn_session` token
and every request carries that cookie — enough for a multi-user backend, or for
pointing the server at the VPS later.

The interesting case is neither: a multi-user backend with no token. Browse
keeps working (`/api/shows` and `/api/venues` are public) and every personal or
admin tool would 401. Left alone that surfaces as a stack trace, so it's caught
and answered with something actionable instead:

```json
{"error": "sign-in required: set FOGHORN_MCP_SESSION to a foghorn_session token, or run the backend with FOGHORN_SINGLE_USER=1", "status": 401}
```

403 gets its own message naming the admin gate, since "the token works but
isn't an admin's" is a different fix. Handled 4xx generally comes back as
`{"error": detail, "status": n}` so a caller branches without parsing exception
text; 5xx still raises, because a server bug isn't something the caller can act
on. An unreachable backend — the likeliest failure in practice, since the MCP
server is a separate process from the API — is reported the same structured
way, naming the URL it tried.

### 13 tools

Public: `list_shows`, `list_venues`. Per-user: `get_watchlist`,
`list_watched_venues`, `get_watchlist_digest`, `add_watchlist_performer`,
`remove_watchlist_performer`, `watch_venue`, `unwatch_venue`. Admin:
`add_event`, `remove_event`, `set_event_type`, `clear_event_type`.

`list_shows` exposes the full current param surface — wider than the README
documented, which is fixed in the same PR (see below). Multi-value facets
accept a single value *or* a list (`region="SF"` and
`region=["SF", "East Bay"]` both work), OR within a facet and AND across.
`limit` defaults to 50 in the tool signature rather than reimplementing capping
— the endpoint already has the param, it just defaults to uncapped, which is
the wrong default for a conversational client. Rows come back in the API's
shape verbatim, `room` (#106) included.

Two naming notes. `from` is a Python keyword, so the parameter is `from_` — the
same spelling `api/shows.py` already uses for its own alias. `to` needs no such
dodge, so `to="all"` reads exactly as the API does.

Every write tool's description tells the client to confirm with the user first.
`set_event_type` / `clear_event_type` additionally spell out that they write a
**venue+billing override rule**, not a single-row edit: it survives re-ingest
and applies to every instance of a recurring session. A caller naming one show
should know the blast radius is wider than the show it named.

`get_watchlist_digest` looks thin next to `list_shows(watchlist=True)`, and
isn't: it carries `watchlist_matches` per row — *which* followed name hit —
which the filter doesn't.

### The literal-drift guard

The tool signatures need vocabularies that live elsewhere: `type`
(`show`/`jam`/`comedy` — `comedy` only arrived in #113), `origin`,
`time_of_day`, and the region list. ficycle has scar tissue here — a copied
category Literal drifted five values behind and silently blocked MCP writes for
those values, accepted by the HTTP API and rejected client-side by MCP, which
is why `tests/test_mcp_literal_drift.py` exists there.

foghorn's version takes the fix one step further: the Literals are *imported*
from `foghorn.models` rather than copied, so the drift can't start. What an
import alone doesn't protect is the **published schema**, which is what an MCP
client actually validates against — retyping a parameter as a bare `str` would
drop the enum without breaking anything the type checker looks at. So
`tests/mcp/test_literal_drift.py` pins the enum values in the emitted tool
schemas to `get_args(EventType)` / `Origin` / `Region`, and additionally
asserts that every region present in `SEED_VENUES` is expressible over MCP.

One model *is* re-declared: `NewVenueArg`, the `add_event` body's new-venue
object. Importing `api.events.NewVenue` would execute `foghorn/api/__init__.py`
and build the entire FastAPI app — routers, CORS, scheduler import — inside
what is meant to be a thin stdio client. The drift test pins its field set to
the real request model instead.

### Dependencies

`mcp==1.29.1` goes in the existing `[dev]` extra. This is the part that's easy
to get wrong: `make install` runs `pip install -e ".[dev]"` and `gate.yml` runs
`make install`, so a bare `[mcp]` extra would leave CI without the package and
fail every MCP test at import. The dev extra keeps `make install` a single line
and keeps the dependency off the scrape/API deployment.

### Also in this PR

`backend/README.md`'s `GET /api/shows` section was materially out of date — it
documented `region`/`neighborhood` as single-valued and omitted `genre`,
`origin`, `type`, `venue_watchlist`, `long_tail`, and `limit` entirely, all of
which the endpoint accepts today. Refreshed against the code, along with the
sample response (which was missing `id`, `source`, `event_type`, `genre`,
`end_local_time`, and performer `origin`), plus the new **MCP Server** section.

### Verification

41 new tests drive the tool layer with the HTTP calls mocked, covering param
passthrough, the `limit` default, the auth header, and every structured-error
branch. A manual smoke run against the live fleet backend on :8100 confirmed
each acceptance criterion: 13 tools listed; `list_shows()` → 50 rows;
`region=SF, type=jam, genre=jazz` → 14 rows, all three facets holding;
multi-value facets OR-ing within and AND-ing across; `to="all"` → 2,875 rows
out to April 2027 against the ~30-day default window; a throwaway event added,
found by date and venue, flipped to `jam` and back via the override rule, then
removed.

---

## Per-show `room` — multi-room venues stop looking double-booked (August 2026)

Shipping SFJAZZ exposed a modelling gap. Its `sfjazz` row covers two rooms in
one building — Miner Auditorium (~700 seats) and the Joe Henderson Lab (~100) —
and the scraper folded them together on the SoundBox-under-Davies precedent.
The numbers said that was wrong:

- The Lab is **45% of the venue's calendar** (80 of 177 shows in the window),
  not an occasional side room like SoundBox.
- **36 of 95 programmed nights (38%) run both rooms**, so the venue read as
  double- or triple-booking itself. Sep 19 listed five shows at "SFJAZZ Center",
  two of them at overlapping times.

The obvious fix was to split into two venue rows, as The Mellow's rooms are
split. But The Mellow's split earns its keep because those rooms sit in
*different neighborhoods*, so the region and neighborhood filters gain real
precision. SFJAZZ's rooms share an address; a split would buy nothing for
filtering while fragmenting a venue that genuinely is one place. The general
answer was the missing field, not a second row.

### The field

`shows.room TEXT` (nullable), threaded through `ScrapedShow` → pipeline → repo →
API → UI. Added via the existing additive-ALTER path in `init_schema`, since
`CREATE TABLE IF NOT EXISTS` skips tables that already exist and the live DB
carries ~1,000 shows predating the column.

**It is deliberately not part of the natural key**, which stays
`(venue_id, start_local_date, start_local_time, headliner_canonical)`. One room
can't host two bills at one moment, so the key already separates concurrent
shows on the headliner. Putting the room in it would mean a venue relabelling a
room — or a scraper *learning* to read one, which is exactly what happened here
— doubles every affected show instead of correcting it. There's a test pinning
that: ingesting the same show first without a room and then with one leaves one
row, updated.

Room strings are whitespace-normalized but keep the source's casing, the same
posture as performer display names. Where a source is internally inconsistent
the *scraper* canonicalizes: SFJAZZ ships both "Joe Henderson Lab" and "Joe
Henderson lab", and one venue's rooms shouldn't render two ways.

Off-site bookings carry no room — an off-site venue's "room" is its own venue
row, so the field stays empty rather than duplicating the venue name.

In the UI the room sits between venue and neighborhood, reading innermost
outward (venue → room → area), with slightly more weight than the neighborhood
so "Joe Henderson Lab" isn't misread as a district. Single-room venues render
exactly as before.

### Scope note

Only SFJAZZ populates it so far. Other multi-room venues in the set — DNA
Lounge's rooms, SoundBox inside Davies — can adopt it whenever their scrapers
are next touched; nothing forces a sweep, and `NULL` is the correct value until
then.

---

## Coverage audit — the August 2026 venue sweep, and what it closed (August 2026)

An audit prompted by the Freight and SFJAZZ asked what else was missing. It ran
from the registry and the DB first (per the audit rule), then verified every
candidate, and produced six shipped venues, one promotion, one correction, and
two documented dead ends.

### Shipped from the audit

| venue | region | route | shows |
|---|---|---|---|
| Brick & Mortar Music Hall | SF | Ticketmaster | 64 |
| The Masonic | SF | Ticketmaster | 26 |
| Mountain Winery | South Bay | Ticketmaster | 33 |
| The Midway | SF | Ticketmaster | 9 |
| Napa Music Hall | North Bay | Ticketmaster (2 rooms) | 29 |
| Blue Note Napa Summer Sessions | North Bay | Ticketmaster | 20 |
| Ashkenaz | East Bay | VenuePilot GraphQL | 28 |
| Stanford Live | Peninsula | Spektrix | 53 |
| Audium | SF | promoted from the aggregator quarantine | 12 |

South Bay went from 4 venues / 40 upcoming shows to 5 / 73; North Bay from
4 / 131 to 6 / 180.

### The method that mattered

**Reachability is worthless for "is this venue open".** Three venues answered
HTTP 200 from live, well-formed websites while being permanently closed:
Starline Social Club (Oakland, closed Dec 2022), Thee Parkside (SF, closed July
2026) and Cafe Stritch (San Jose). Zombie domains outlive venues. What actually
settles the question is **ticketing-platform inventory** and dated future
events — Cafe Stritch's page was 20kb of "CafeStritchSignOff", and Starline's
site still sells the venue it no longer is.

**A venue record is not inventory.** Both Freight & Salvage and Blue Note Napa
have multiple Ticketmaster venue records where only one — or none — carries
events. Matching by name would have shipped a summer series in place of a jazz
club. Confirm ids by querying for events.

**Chasing the top recommendation produced a correction.** Blue Note Napa, the
audit's highest-value jazz gap, turned out to have closed its club on 31
December; 1030 Main Street is now Napa Music Hall. The evidence was already in
hand (zero TM events for the club, a shows page listing only Summer Sessions)
and had been read as "operating but uncovered".

**Platform recon before building.** Reconning all candidates first collapsed
four bespoke scrapers into one batch of ~30-line Ticketmaster adapters, and
told us which of the rest needed real work.

### Dead ends, recorded so nobody re-runs them

**El Rio (SF) — blocked, no first-party calendar.** The site is Squarespace and
its sitemap has 15 URLs: pages and merch products, and *not one event*.
``?format=json`` 404s on every plausible collection slug because no events
collection exists. Its listings live only on third-party aggregators (ToS-barred
per the aggregator spike) and Instagram. Asking the venue for a feed is the
realistic path; there is nothing to scrape today.

**Montalvo Arts Center — access solved, data not viable.** It *is* Tessitura;
the earlier fingerprint failed only because the host is ``my.montalvoarts.org``,
not the ``secure.``/``tickets.`` guesses. **The Freight's endpoint works
verbatim there** (``POST /api/products/productionseasons``), which is worth
knowing: the Tessitura pattern generalises, and the subdomain is discoverable
from JSON-LD ``url`` fields on the venue's own pages.

The blocker is the content. Across a six-month window: 38 performances, of
which roughly five are music (Kings Return, NoorAva, Alphabet Rockers, Día de
los Muertos). The rest is a ceramics course, a theatre series, Halloween family
events, and *fundraiser ticket tiers* listed as separate performances ("VIP
Ticket", "Classic Ticket"). Unlike the Freight, ``productTypeId`` does not
segregate — id 12 alone mixes theatre, a stand-up competition and Persian
classical — and ``performanceTitle`` is an HTML blob with the description
mashed in, so a title denylist would be fragile. Montalvo is a visual-arts and
education centre whose concert programming is largely a summer series; the
music yield doesn't justify a scraper that would mostly emit noise. Revisit if
the Carriage House series is in season, or if the type ids get cleaner.

---

## Ticketmaster venue batch — 4 rooms, 132 shows (August 2026)

A coverage audit (August 2026) asked what was still missing after the Freight
and SFJAZZ. The answer turned on platform, not on venues: of the confirmed-
operating candidates, **five looked Ticketmaster-ticketed, and four actually
were**, which made them ~30-line adapters over the existing `_ticketmaster`
helper rather than four bespoke scrapers.

| venue | region | TM events |
|---|---|---|
| Brick & Mortar Music Hall | SF (Mission) | 64 |
| The Masonic | SF (Nob Hill) | 26 |
| Mountain Winery | South Bay (Saratoga) | 33 |
| The Midway | SF (Dogpatch) | 9 |

Mountain Winery matters out of proportion to its size: the South Bay had four
venues and 40 upcoming shows before this, the thinnest region in the set.

### Two traps the batch had to walk around

**A venue record is not inventory.** Blue Note Napa was the audit's top jazz
recommendation and is *not* in this batch. Discovery has four matching records
and the one with events — 21 of them — is "Blue Note Napa **Summer Sessions**"
at the Meritage Resort, a seasonal outdoor series at a different address. The
club itself (1030 Main Street) has **zero**. Seeding the series as the club
would have quietly substituted a summer programme for a year-round jazz room.
Same shape as the Freight, whose three TM records all returned zero. Every id
in this batch was confirmed by querying for events, never by matching a name.

**Comedy was arriving as music.** `_ticketmaster` mapped Discovery
classifications to a genre string but never filtered on them, so stand-up came
through as shows — 11 of the Masonic's 37 listings were Chelsea Handler, John
Mulaney, Daniel Sloss and friends. The helper now drops the `Arts & Theatre`
segment. Deliberately narrow: `Undefined` and `Miscellaneous` are kept, because
TM leaves plenty of real gigs unclassified (a sixth of the Regency's), and
dropping those would trade lost shows for a tidier taxonomy. The visible cost
is that a lecture at the Masonic still lands; that's the right side of the
trade.

This was pre-existing and affected the Fillmore and the Regency too — neither
had any `Arts & Theatre` listings, so nothing already ingested changed.

### What the audit found that isn't in this batch

- **Blue Note Napa** needs its own scraper (self-ticketed, WordPress).
- **Ashkenaz** (Berkeley) — Squarespace + **VenuePilot**, which has an API.
- **El Rio** (SF) — Squarespace; the existing `_squarespace_events` helper may
  cover it.
- **Montalvo Arts Center** — Tessitura TNEW, the same platform as the Freight,
  so a shared helper extracted from `freight_and_salvage` would cover both.
- **Stanford Live / Bing** — Spektrix.
- **Audium** (SF) — bespoke WordPress, and already arriving via the Bay
  Improviser aggregator; promoting it out of quarantine is cheaper than a
  scraper.
- **Napa Music Hall** — six TM events, surfaced incidentally while checking
  Blue Note. Not audited; worth a look.

And two closures the audit confirmed, worth recording so nobody re-adds them:
**Starline Social Club** (Oakland, closed Dec 2022), **Thee Parkside** (SF,
closed July 2026) and **Cafe Stritch** (San Jose). All three still serve live
websites, which is exactly why a reachability check is worthless for this
question — ticketing-platform inventory is the real signal.

---

## SFJAZZ — the last dormant Phase 2 venue, finally scraped (August 2026)

`sfjazz` has been seeded since Phase 2 with `calendar_url = "TBD"` and zero
shows — the original pilot venue, dormant for the entire life of the project
because the site sits behind a Cloudflare managed challenge. The venues endpoint
had a special case naming it as the one seeded-but-excluded row. That's closed:
**182 shows** over a 180-day window, 177 of them at the Center itself.

### What actually changed

The re-recon (#91) started by applying the Freight playbook — check for a
`secure.`/`tickets.` CNAME off the challenge — and that failed. Subdomains
enumerated from certificate-transparency logs (`admin`, `athome`, `shop`,
`staging`, `venuebuilder`, `vpn`, `wifi`, `www`) are all Cloudflare-fronted
except Shopify merch and Vimeo streaming; SFJAZZ self-hosts ticketing on
`sfjazz.org`. Ticketmaster remains a dead end.

What had changed since July is the site itself. `robots.txt` gives it away —
it's now Umbraco, built by Adage Technologies, and it disallows only
`/umbraco/`. The calendar renders client-side from an endpoint named in
`/Static/dist/calendar.js`:

```
GET https://www.sfjazz.org/ace-api/events/?startDate=YYYY-MM-DD&endDate=YYYY-MM-DD
```

Unauthenticated, no nonce, no key, one request for the whole window (a year =
282 events), already one entry per performance. It carries the room, the full
artist list, ticket and detail URLs, and sold-out state. No price — only the
per-production HTML pages have that, at ~300 extra fetches a night, which isn't
worth a price string.

### The client is load-bearing, and that is a real cost

Cloudflare fingerprints client stacks. Measured interleaved, same URL, same
polite UA, 2s apart: `urllib` `[200, 200, 200, 200]`, `httpx`
`[403, 403, 403, 403]` with `cf-mitigated: challenge`. `curl` is challenged too.
So this scraper deliberately uses stdlib `urllib` where every other scraper in
the repo uses `httpx`.

That was Diego's call, taken with the tradeoff stated: no challenge is solved
and no auth bypassed (these are ordinary GETs of openly-served endpoints),
`robots.txt` permits these paths, and it's one request per night from a
contactable UA — but it is **fragile**, because Cloudflare reclassifies clients
routinely.

The header set turned out to be load-bearing too, and counter-intuitively so.
Mid-build the scraper started 403ing, which looked like the predicted
reclassification. It wasn't — it was a `Referer` header added for politeness.
Reproducibly:

```
UA + Accept           -> 200
UA + Accept + Referer -> 403 cf-mitigated: challenge
UA, no Accept         -> 403 cf-mitigated: challenge
```

An explicit `Accept` is required and a `Referer` is fatal — the reverse of the
usual "look more like a browser" instinct. A test pins the exact header set so a
well-meaning edit can't quietly break it, and `fetch_events` translates a
returning challenge into a raised error so the venue reads as *errored* on the
scrape-health surface rather than reporting an empty calendar, which would look
identical to "SFJAZZ has no shows".

### SFJAZZ is a presenter, not just a venue

The feed's `location` field routes each event. Miner Auditorium and the Joe
Henderson Lab fold into the one `sfjazz` row (same building, same neighborhood —
the SoundBox-under-Davies precedent, unlike The Mellow's two rooms in different
neighborhoods). The feed spells the Lab both ways, `Lab` and `lab`, so matching
is casefolded — a case-sensitive map would have sent 7 events a year to the
unmapped-location warning.

SFJAZZ also books off-site: the Paramount, the UC Theatre, Davies, Grace
Cathedral. Those are routed but **not ingested**, and that restraint is a safety
property rather than tidiness. The runner ingests a registered scraper's whole
output against one venue with `prune=True`; SFJAZZ lists only the two nights it
presents at the Paramount, so registering this scraper under
`paramount_theatre_oakland` would reap every *other* Paramount show in that span
and wipe out that venue's own scraper's work. Off-site dates arrive through the
host venue's scraper, where they already do — Snarky Puppy's Paramount date was
in foghorn before this shipped, with a natural key identical to what this feed
reports. Unmapped locations drop with a warning rather than raising: losing one
one-off room beats losing the other ~180 shows in the window.

### SFJAM

`eventTypes` separates classes from concerts, but a bare `Education` tag is not
the class programme — it is SFJAZZ's monthly **SFJAM free community jam
session**, and every bare-`Education` event across a year of the feed is one.
Nine dates that a naive read of the taxonomy would have dropped, of exactly the
participatory "bring your horn" event `event_type="jam"` exists for. They're
kept and tagged explicitly. Family matinees carry `Education` alongside
`Family Events` and are kept; plain concerts sometimes carry no type at all and
are kept too.

Also worth keeping: the feed lists every named player, so a trio's sidemen
become support rows and the watchlist can follow a musician across the bands
they sit in.

A drop audit of the live run confirmed no silent losses: 207 events in window →
182 kept, 25 dropped (16 streamed "SFJAZZ At Home" dates, 9 classes/workshops),
zero unmapped locations.

### Postscript (2026-08-13): the fragility came due, and the cadence changed

The documented risk landed two days after shipping. From **2026-08-12** the site
serves the scraper a Cloudflare challenge again — the client-fingerprint gap
that made `urllib` work has closed. Both nightly runs since have failed
identically, and a check on the 13th was still blocked, so this isn't reputation
decay from the build's probing; it's the block.

What held up: the failure is **loud and contained**. `fetch_events` raises
`SFJazzSourceError`, so SFJAZZ shows as the one errored venue of 79 on
`GET /api/health/scrape` rather than reporting an empty calendar. Because the
raise happens before anything is returned, `ingest_scraped_shows` is never
reached and `prune=True` never fires — **a broken scraper cannot reap its own
venue**. All 177 shows, their rooms, and the 5 SFJAM jam tags are intact.

So SFJAZZ moved to `MONTHLY_SCRAPERS`: it now attempts on the 1st rather than
nightly. The season is already ingested through February, so freshness costs
little, and a nightly error nobody can act on is just noise on the health
surface. The monthly attempt is the cheap recovery probe — if the block lifts,
the calendar comes back on its own.

The durable fix is still to ask SFJAZZ for an `.ics` or a UA allowlist entry
(their `robots.txt` already permits these paths), or to pick them up via the
JamBase feed in #90. Chasing a new client fingerprint is explicitly *not* the
plan: it's an arms race that breaks on Cloudflare's schedule, and it would edge
from using an openly-served endpoint toward evading a block that is now
unambiguous.

---

## Freight & Salvage — behind the Cloudflare wall via Tessitura (August 2026)

Freight & Salvage (2020 Addison St) is a 400-seat nonprofit coffeehouse and the
most conspicuous hole in foghorn's East Bay coverage — every other Downtown
Berkeley room was already scraped. Folk/roots-led with a real jazz and world
strand: Bobby McFerrin, Jeff Parker's ETA IVtet, Bill Frisell, Bettye LaVette,
Meshell Ndegeocello, Bruce Cockburn, Ladysmith Black Mambazo.

What existed before was worse than nothing because it looked like coverage: an
aggregator-created `the_freight` row holding two past dates of a free lunchtime
talk series, quarantined, with empty region/neighborhood/genre so no filter
could reach it.

### The site is walled; the ticketing host is not

`thefreight.org` sits behind a Cloudflare managed challenge — 403 with a "Just a
moment..." interstitial to every plain client, polite UA and Chrome UA alike,
right down to `robots.txt` and `sitemap.xml`. Per the posture set in #91 we
don't touch the challenge. Ticketmaster Discovery was the obvious fallback and
is a dead end in a confusing way: it carries **three** Freight venue ids
(including a "Memberships" one) and every one returns `totalElements: 0`,
because the Freight self-tickets. A Berkeley city sweep returns 43 events across
only UC Theatre, Greek, and Cornerstone — all already covered.

**The way in was DNS, not HTTP.** `secure.thefreight.org` is a CNAME to
`frts-tnew-prod.tnhs.cloud` — Tessitura Network Hosting Services running TNEW
(Tessitura Network Express Web) — and that host has no bot challenge on it. It
answers 200 to a plain client with our polite UA and serves the real events
listing. The Cloudflare wall only ever covered the WordPress marketing site.

**Carry this forward: when a venue site is challenge-walled, check for a
`secure.` / `tickets.` / `ci.` CNAME before writing the venue off.** A
self-ticketing venue usually fronts ticketing on a separate host that has no
reason to be challenged. This is the cheapest unexplored move on any venue
currently parked as "blocked" — SFJAZZ included.

### The endpoint

The listing renders client-side from one unauthenticated JSON endpoint — no
nonce, no cookie, no key, found in the TNEW bundle on `tnew-assets.com`:

```
POST https://secure.thefreight.org/api/products/productionseasons
{"startDate": "2026-08-11T00:00", "endDate": "2027-02-07T23:59"}
```

It returns the whole window in one request (a year came back as 78 productions
/ 119 performances) with no pagination and no sign of a cap. Multi-night runs
and residencies arrive already expanded, one entry per performance, so there's
no recurrence maths.

Shape notes: `performanceTitle` is the billed act while `productionTitle` is the
umbrella ("Jeff Parker ETA IVtet" vs "Jeff Parker"); `iso8601DateString` is
local-with-offset and carries seven fractional digits that `fromisoformat`
won't take unaided; titles embed raw HTML (`<br>` + `<font>` subtitles, `&amp;`,
and two that leak a whole `<h1 id="tn-page-heading">`); there is no price field
anywhere, so `price_text` is always `None`; and 11 performances are
`isOnSale: false` ("Tickets Not On Sale") — real announced dates whose on-sale
hasn't opened, kept as shows but with the ticket link withheld.

### The product-type trap, and why the first filter was wrong

Tessitura's `productTypeId` looked like the clean classes-vs-concerts
discriminator: type 3 is the concert programme, types 1 and 2 the teaching
programme, and `productTypeName` is an empty string on every record so the id is
the only taxonomy available. Gating on it is wrong in **both** directions, and
the first cut of this scraper shipped that bug until an audit of what the live
run discarded caught it — **39 in-window entries dropped**, including the
weekly Country Bluegrass Jam, four open mics, and a booked Karl Evangelista /
Grex gig. Meanwhile type 3 happily carried a Berkeley Public Library story time.

The feed's real structure is three-way:

- **Term classes** are filed under a `"<Term> <N>: <instructor>"` production
  ("Fall I: Tamsen Fynn"). That production-title pattern is the single cleanest
  class marker in the feed and catches 17 performances exactly.
- **Community Mondays** is a genuinely mixed community series sitting on the
  teaching product type — jams, open mics, and booked gigs alongside comedy and
  a vinyl listening party. Kept as a carve-out and filtered on title.
- **Everything else** on a non-concert type is a one-off class, caught by
  skill-level title framing ("Beginning Harmonica with Aki Kumar").

So the filter drops the term-class production pattern first, then non-music
title signals (story time, The Moth's storytelling slams, comedy, listening
party, singalong, workshop, skill levels), and only then consults the product
type — with the Community Mondays carve-out on top. Live result: 80 shows over
the 180-day window, versus 71 under the broken gate.

Jams and open mics are tagged `event_type="jam"` explicitly. The ingest's own
inference is deliberately narrow and would catch "open mic" but miss "Country
Bluegrass Jam" (no genre word it knows, no session/night framing); the scraper
is the source that knows, and an explicit tag always wins.

### Reconciling the aggregator row

Seeding the venue was not sufficient, and the failure would have been silent.
`aggregators/ingest.py::resolve_venue` tries the alias map, then an **exact**
canonical-name match, then token-subset. Bay Improviser bills the venue as "The
Freight", which strips to canonical `"freight"` — and the pre-existing
aggregator row *named* "The Freight" strips to exactly that too. The quarantined
row wins the exact pass, while the seeded "Freight & Salvage" could only ever
match on token-subset, which runs later. One room, two venue rows, shows split
between them.

Fixed with a `VENUE_ALIASES` entry (`"the freight"` / `"freight"` →
`freight_and_salvage`), which is consulted before the exact pass, plus a
regression test that reconstructs the live DB's exact state — a quarantined
"The Freight" row alongside the seeded one — and asserts the seeded row wins.

Genre is `folk`, not `jazz`: the booking is folk/roots-led and the per-show
genre override (7.2) carries the jazz nights.

---

## The Mellow — EventON recon + two-room scraper (August 2026)

The Mellow (1401 Haight St) is a plant store / cafe / barbershop that took on
ticketed live music in early August 2026 once its Type 90 entertainment licence
came through; the owners are both musicians and jazz is the primary booking.
That's the Bird & Beckett shape — a room where the jazz is the point but the
building isn't a music venue — which is what foghorn exists to surface and what
a generic aggregator misses. Two rooms shipped: the Haight shop, and the **Blue
Heron Lake Boathouse** in Golden Gate Park, home of the weekly **Lakehouse
Jazz** series.

**Two venue rows, not one.** Following the Davies / Herbst / Wilsey precedent.
They're in different neighborhoods, so folding the boathouse under the shop
would file Lakehouse Jazz under "Haight" and make the venue watchlist unable to
pin one room without the other.

### The EventON datetime problem (the reusable part)

The site is WordPress running **EventON 5.0.11**, not The Events Calendar, so
the Tribe REST pattern used elsewhere in the codebase does not apply. Every
obvious route is a dead end, and one of them is an *attractive* dead end:

- `/wp-json/tribe/events/v1/events` → **404**. Not Tribe.
- `/wp-json/wp/v2/ajde_events` → **clean JSON, and a trap.** Its `date` /
  `date_gmt` are the WordPress *post* timestamps — several sit in 2021–2023 —
  and the object carries no start/end datetime at all. EventON keeps showtimes
  in post meta (`evcal_srow` / `evcal_erow`, unix seconds) that the REST API
  does not register: `?_fields=meta` returns only theme keys.
- `/events/feed/` → **301 to the archive**, no feed.
- `/calendar/` → renders client-side; the initial HTML says "10 Event(s) found"
  with zero event rows in the markup.
- Single-event pages **do** carry `schema.org/Event` JSON-LD with a real
  `startDate`, plus EventON's own `data-time="<srow>-<erow>"` — but only for the
  *first* occurrence of a repeating event. Lakehouse Jazz's two pages advertised
  2026-03-21 and 2026-05-16, both long past. Unusable for a weekly series, which
  is the whole calendar here.

The path that works is the endpoint `/calendar/` calls itself:

    POST https://themellowsf.com/?evo-ajax=eventon_get_events

It answers unauthenticated, and its `json` key is one entry **per occurrence**
with `unix_start` / `unix_end` — plus the ticket link (`evcal_lmlink`), price
(`_seo_offer_price`), and subtitle in `event_pmv`. Three constraints, each found
the hard way and each worth carrying to the next EventON site:

1. **The nonce is required.** It's `evo_general_params.n` on `/calendar/`.
   Missing or wrong returns `{"status":"bad"}` — a 200 with no error text.
2. **The harvested shortcode config is required.** A hand-built minimal payload
   returns `{"status":"GOOD"}` and *zero events*. The scraper reads the real
   config off the `evo_cal_data` `data-sc` attribute and overrides fields on top
   of it.
3. **`fixed_month` / `fixed_year` only relabel the calendar header.** Paging
   month-by-month returned the same 12 August rows five times under five
   different `cal_month_title`s — a bug that looks exactly like "the venue only
   books one month out". The real window is
   `focus_start_date_range` / `focus_end_date_range` (unix seconds), and setting
   those returns the whole window in **one** request. Blanking them makes the
   endpoint answer with a non-JSON body, so they're always set explicitly.

`show_repeats=yes` is the other load-bearing override: the site's own config
ships `no`, which collapses a weekly series to a single row.

**Room routing joins two payloads.** The AJAX response carries no location, and
the rendered HTML carries no location classes either. The taxonomy lives on the
WordPress REST objects as `class_list` entries
(`event_location-the-mellow-haight` / `event_location-blue-heron-boathouse`), so
the scraper joins occurrences to the REST index on event id. An unrecognized
location term **raises** rather than defaulting to a room — silently folding an
unknown room into one of the two known ones would put shows in the wrong
neighborhood, which is the exact failure the venue split exists to prevent. The
closed Mission room is the one deliberate drop.

**Non-music programming** (retail pop-ups, plant workshops) is dropped on the
venue's own `event_type` taxonomy, with a short title-signal backstop for the
entries carrying no type term at all — "Mindful Flow" has none. Everything else
is kept, matching the err-toward-inclusion posture of the other mixed-programming
scrapers.

**Registered twice, once per room.** `REGISTERED_SCRAPERS` maps one slug to one
callable and the runner ingests a scraper's whole output against that one venue,
so `scrape_haight()` / `scrape_boathouse()` each filter the shared fetch. That
keeps the nightly prune scoped to the venue it actually has authoritative
listings for — a single registration would have let one room's window reap the
other's shows.

### Coverage as shipped

The live run returns **68 shows** — Lakehouse Jazz, two sets a night (7:00 and
8:30), Fridays and Saturdays from 2026-08-14 through 2026-12-05, all with
Eventbrite ticket URLs and a `$35` price.

**The Haight room currently yields zero shows, and that's the source's state,
not a scraper bug.** Every Haight-tagged event on the site is stale: workshops
and pop-ups from 2021–2023, and a "Mellow Sessions" concert entry last dated
2024-01-06. The August 2026 ticketed shows that motivated the ticket are not
published to the EventON calendar, and `/music/` carries no calendar and no
ticket links either. The venue row and the routing are in place, so those shows
land automatically once they're scheduled — but if the Haight programming stays
off the site, picking it up needs a different source (an `.ics` from the venue,
or their Eventbrite org page) and that's a fresh decision, not this ticket.

Also resolved: the boathouse address. Listings disagree because the lake was
renamed from Stow Lake in 2024; The Mellow's own event pages give **50 Blue
Heron Lake Dr East**, which is what's seeded.

---

## Single-user mode for the fleet deployment (August 2026)

Multi-user (previous entry) left the fleet deployment stranded on the
anonymous view: no star/pin on venues, no `+` on performers, no `jam?`
correction. No data was lost — the migration re-keyed the 30 watchlist and
15 watched-venue rows onto a bootstrap admin — the deployment simply had no
session, and the frontend hides every follow affordance without one.

**Why the phone couldn't just sign in.** `/join/<token>` works fine on the
laptop, and that was verified. But foghorn is installed on the phone as an
iOS home-screen PWA (`display: "standalone"`): it gets its own storage
container, so a Safari sign-in doesn't carry; it has no address bar to reach
the join URL; iOS opens tapped links in Safari rather than the installed app;
and `UserMenu` renders nothing for anonymous visitors by design. A daily-use
deployment that couldn't sign itself in.

**Why not pin fleet to the pre-multi-user commit.** The live DB is already
migrated — `watchlist` / `watched_venues` carry a `NOT NULL user_id` with no
default, and the old repo layer inserts without it, so reads would render but
every new follow would `IntegrityError`. An honest revert also meant restoring
the Aug 1 DB copy and losing ~10 days of scrapes, and `fleet sync foghorn`
would silently undo the pin.

**The flag.** `FOGHORN_SINGLE_USER=1` makes `optional_user` resolve a
*cookie-less* request as the bootstrap admin (`users_repo.first_admin` —
lowest-id admin, the same selection `_ensure_bootstrap_admin` uses, so the
flag lands on exactly the account the migration gave the legacy rows to)
instead of anonymous. Precedence is the load-bearing part: a real session
cookie always wins, so a signed-in non-admin still resolves to *themselves*.
With no admin row it degrades to anonymous rather than conjuring a user on a
GET (`make auth-bootstrap` is the documented fix). Startup logs a `WARNING`
naming the resolved admin — unauthenticated admin should never be silent.
Multi-user on the VPS is untouched, and `deploy/`'s compose pins the flag to
`0` alongside `FOGHORN_SECURE_COOKIES=1` so an inherited env can't turn it on.

**The frontend change is one deleted line, and it mattered.**
`serverAuth.getMe()` short-circuited to `null` whenever there was no cookie to
forward — so no backend response could ever have revealed the mode. It now
always calls `/api/auth/me`; anonymous-in-normal-mode still yields `null`
because `getJSON` maps a non-OK response to `null`, leaving that UI unchanged.
`/api/auth/me` also grew `single_user: bool`, which `UserMenu` uses to drop
the sign-out control (signing out would just re-resolve to the same admin).

**Two e2e wrinkles worth remembering.** (1) "Anonymous" and "single-user" are
the *same* cookie-less request, distinguished only by the backend flag, so one
mock can't serve both: the mock backend now listens on two ports (:4010
normal, :4011 single-user) with a second Next app on :3201 in front of the
latter, and `auth-modes.spec.ts` clears the seeded cookie for both halves.
(2) Next resolves `next.config.ts` rewrites at **build** time — so the two
apps need separate builds (`NEXT_DIST_DIR`), not one shared one, or the
second app's *browser* calls proxy to the wrong mock. That also means
`BACKEND_URL` must be set for `next build`, not just `next start`; getting
this wrong silently sends browser mutations to the default backend.

The fleet side is a one-line `FOGHORN_SINGLE_USER: '1'` in the separate
`fleet` repo's `ecosystem.config.js` (`foghorn-api` only — the frontend asks
the backend). Resolves [#97](https://github.com/diegoSQK/foghorn/issues/97).

---

## Multi-user accounts + VPS deployment (August 2026)

Friends asked for access — the exact unblock condition the plan had written
for both "Hosting / deployment" and "Multi-user accounts." Both shipped
together in one arc (single session, Diego directing; PM+coding roles
merged for the sprint).

**Auth model: invite-link-as-credential.** Chosen over magic-link email (no
email-provider dependency) and passwords (wrong weight for a friends-tier
app). An admin mints a user row + token; `/join/<token>` claims the account
on first open and signs back in on any later open — the link *is* the
durable credential ("keep this link"), so a lost session costs nothing.
Sessions are opaque tokens (only SHA-256 stored) in an HttpOnly cookie with
rolling ~13-month expiry; `FOGHORN_SECURE_COOKIES=1` opts into Secure where
HTTPS terminates (the fleet deployment serves plain HTTP over Tailscale, so
it stays off there). An optional email is collected at claim time purely so
magic-link *recovery* can be added later without rework.

**Endpoint posture.** Browse is public (shows, venues, health — it's
aggregated public data); personal data (both watchlists, digest, the
`?watchlist=`/`?venue_watchlist=` filters) requires a session and is scoped
per-user; global mutations (inbox, manual events, origin/genre/event-type
corrections, user management) are admin-only. One subtlety: the aggregator
quarantine's pin-promotion is now per-user — one user pinning a long-tail
venue no longer reveals it to everyone (`ShowFilters.user_id` scopes the
exemption subquery).

**Schema.** `users` + `sessions` tables; `watchlist` and `watched_venues`
re-keyed to `(user_id, …)` via a row-preserving SQLite table rebuild (the
first non-additive migration — rename → recreate from canonical DDL →
copy → drop). Pre-existing rows land on a bootstrap admin the migration
creates; `python -m foghorn.cli.auth bootstrap` (or `make auth-bootstrap`)
prints that admin's login link. Frontend: `/join/<token>` claim page,
signed-in nav with sign-out, admin-only Add event/Inbox plus a new
`/people` management page (create invite, copy/regenerate link, disable
with session revocation); anonymous visitors get the public calendar with
all follow/correction affordances hidden and stale `?watchlist=true` URLs
degrading to the plain calendar. Server components forward the session
cookie to the backend (`lib/serverAuth.ts`); browser calls were already
same-origin via the `/api` rewrite, so cookies ride with zero CORS work.
The e2e suite runs "signed in" via a seeded cookie + a mock `/api/auth/me`.

**Hosting: VPS + Docker Compose** (chosen over Vercel+Fly, which would have
forced the Postgres migration, and over a Cloudflare tunnel, which ties
uptime to the laptop). `deploy/`: backend image (slim + `[rapidocr]` so the
flyer-venue OCR works off-macOS), frontend image (Next standalone), Caddy
with automatic HTTPS routing `/api/*` to the backend at the edge. SQLite
stays, scheduler stays in-process. `deploy.yml` SSH-deploys on merge to
main once `DEPLOY_*` secrets exist (no-ops until then); `backup.sh` +
host cron for nightly consistent `.backup`s. `docs/DEPLOY.md` is the
runbook — including the datacenter-IP caveat (WAF-touchy venues may 429
from a VPS; hybrid laptop-scrape fallback documented) and the pinned
`FOGHORN_SFJAZZ_ENABLED=0` (JamBase eval terms don't cover public
display). Both images smoke-tested: build, boot, public browse serves,
personal endpoints 401, bootstrap link mints.

**Still open after this arc:** actually provisioning the box + DNS +
secrets (Diego's action, runbook ready); CORS default stays permissive
(cookie auth is same-origin, so tightening is hygiene not blocker);
magic-link email recovery if "ask Diego for a fresh link" ever grates;
digest delivery (the endpoint is per-user now — a future cron consumer
needs its own auth story).

## Group feeds: ensembles are performers, halls are venues (July 2026)

Same-day model correction to classical tranche 2, from Diego's review: the
SF Symphony and SF Philharmonic had shipped as presenter *venue* rows (the
Cal Performances pattern), but they're performing **groups** — the two
things a follower wants are "watchlist the group" and "see which hall
they're actually playing." Both scrapers became **aggregator sources**
("group feeds"), because the aggregator layer already owns exactly this
shape: sources that name venues they don't own, venue resolution with
quarantine for the long tail, and the performer-watchlist bypass.

- **`AggregatedEvent` grew `support_raw` / `ticket_url` / `price_text`**
  (defaults keep Bay Improviser untouched), and aggregator ingest passes
  them through to the show row. Group feeds put the ensemble in
  `support_raw` on every bill, so any-performer watchlist matching follows
  the group across halls — including into quarantined venues, via the
  existing watchlist bypass. Covered by an end-to-end test
  (`tests/aggregators/test_group_feed_ingest.py`).
- **Seeded halls replace the presenter rows**: `davies_symphony_hall`
  (SoundBox and the venue-field quirk "Youth Orchestra" fold into Davies),
  `herbst_theatre`, `wilsey_center_atrium` (both Veterans Building rooms,
  Civic Center, classical). Rare SFS venue strings pass through to
  quarantine creation (Gunn Theater at the Legion of Honor); placeholder /
  missing venue fields land in a quarantined "San Francisco Symphony
  Offsite" bucket rather than being dropped or mis-attributed.
- **SF Philharmonic hall extraction**: each CBO event page cross-references
  the presenter's *other* events with venue lines in a server-rendered
  related-events block; the feed unions those blocks across all fetched
  pages, so every concert's hall comes from its siblings (complete coverage
  at ≥2 listed concerts; a never-named hall falls back to the offsite
  bucket instead of dropping the show).
- **Migration**: the two presenter venue rows and their 82 shows were
  deleted from the canonical DB (backup taken) and re-ingested through the
  group feeds; both group names were added to the performer watchlist.

The Cal Performances presenter-row precedent still stands for
*presenter-without-identity* cases, but ensembles that tour across halls
want the group-feed pattern. Candidates to revisit under it later: Kronos,
One Found Sound, SF Contemporary Music Players.

## Classical coverage tranche 2: SF Symphony + SF Philharmonic (July 2026)

The two flagship asks from Diego, both previously written off as headless
territory in the tranche-1 audit — both turned out to have plain-HTTP paths
once actually investigated in a browser.

- **San Francisco Symphony** (`sf_symphony`, presenter row at Davies, SF /
  Civic Center / classical) — sfsymphony.org is Kentico with the calendar
  grid rendered client-side, and on on-sale days the whole site sits behind
  a **Queue-it waiting room** (plain fetches get a 2KB interstitial — this
  is what the tranche-1 audit mistook for a JS-only calendar). The real
  feed is a **public Algolia index** (`prod_sfs_calendar`; app id + search
  key ship inline on the calendar page): one REST POST returns the season
  as JSON, one hit per performance, with `performanceDate` already naive
  Pacific-local — and Algolia's host is not behind the queue. 79 shows on
  first live run (Jul 23 → Jan 15) under a 180-day season-scale window
  (club-calendar 90 is too short for classical planning). Kept: Tessitura
  + Kentico hits (the latter are free community performances); dropped:
  `excludeFromCalendar`. Off-site dates (Stern Grove, Frost) ride under
  the presenter row, the Cal Performances model. If the embedded key
  rotates, the scraper 403s loudly; re-extract from the calendar page's
  inline `var settings` block.
- **San Francisco Philharmonic** (`sf_philharmonic`, itinerant presenter —
  Herbst, Wilsey Center Atrium; SF / classical) — Squarespace site whose
  whole 3-concert season lives in homepage nav "Buy Tickets - <date>"
  links into **City Box Office**. Date from the nav text, program title
  from the CBO page `<title>` (presenter prefix stripped), start time from
  CBO's server-rendered `GetTimeSlots.asp` fragment. No horizon window —
  a 3-concert org's furthest date is the point. A concert without a listed
  time slot is skipped until CBO lists it.

Both live-verified at build time; fixtures are trimmed real captures.
Remaining classical deferrals: SF Performances (403 bot-block) and SFCM
(Drupal, partial JSON-LD — second look before Playwright).

## Classical coverage tranche 1: Old First Concerts, Noontime Concerts (July 2026)

Planned as three classical presenters; shipped as one new scraper plus a
genre reclassification, because the pre-build audit ran into work that had
already landed. Cal Performances was audited before noticing it already
shipped in venue batch 5 tranche B; its venue-default genre is "eclectic"
(mixed classical/jazz/dance programming), so classical-genre filtering of
its shows is a per-show-override question, not a new-scraper question.
**Old First Concerts** turned out to be in the same boat — tranche B
shipped its scraper (WooCommerce products via homepage month-submenu
links; 7 live at this build too) — so its delta here is the venue-default
genre flip ``eclectic`` → ``classical``, which matches the room's actual
lean (classical/chamber series since 1970, some jazz and folk mixed in).

**"classical" is a new genre value**, and it needed zero frontend work:
the genre facet chips render from the venue data (a new value appears
automatically once seeded), and the badge/accent palettes deliberately
fall back to neutral for genres outside the styled four — classical rides
that fallback the same way blues and folk already do.

**Noontime Concerts** (Old St. Mary's Cathedral, 660 California St —
the weekly free Tuesday 12:30pm chamber series, 34+ years running) is the
new scraper, and it carries the tranche's gotcha as designed: the site
exposes a public ``concerts`` CPT at ``/wp-json/wp/v2/concerts``, but the
REST payload has **no performance date at all** — ``acf`` and ``meta``
come back empty, there's no content field, and the WP ``date`` is the
post's publish date. The scraper instead walks the server-rendered
``/upcoming-concerts/`` Concert Calendar: one ``div.concert-card`` per
concert with the real date in ``data-date="MM/DD/YYYY"`` plus
``data-title`` and a detail link (the concert-library archive reuses the
same markup for ~660 past shows, so the upcoming page is the only
forward-looking surface). Cards carry no clock time; the series-constant
12:30 start is applied. Non-Tuesday cards are skipped — those are the
monthly Sunday concerts at the SF Mint, a different room with no stated
time (a separate venue row if they ever matter). 2 shows live at build
(Aug 11, Aug 25) — the weekly cadence pauses over midsummer, so a sparse
July page is normal, not a scraper failure.

**Audited and deferred** for a future classical tranche: SF Symphony,
SF Opera, and SF Performances (Tessitura and/or JS-rendered calendars,
some bot-blocked — headless territory); SFCM (Drupal with partial
JSON-LD — worth a second look before reaching for Playwright). Follow-up
noted while here: ``normalize_genre`` has no classical vocabulary yet, so
per-show classical overrides (e.g. Cal Performances' "Recital"/"Orchestra
& Chamber Music" badges) fall through to venue defaults — that's the
per-show-override question above.

## Stanford Jazz Workshop: ad-hoc Peninsula coverage (July 2026)

Single-venue ad-hoc addition. stanfordjazz.org is WordPress with The Events
Calendar (Tribe) REST API exposed — same clean-JSON pattern as Mr. Tipple's /
Madrone / Dresher, built from that template. 12 festival shows live at build
(July–August window), entity-laden titles unescaped.

Modeling calls: **presenter-as-venue** per the Cal Performances precedent —
festival concerts land at Dinkelspiel Auditorium and Campbell Recital Hall,
the year-round **CoHo Jams** at the campus coffee house, all one umbrella
seed row (region Peninsula, genre jazz). CoHo Jams rows are tagged
`event_type="jam"` in the scraper (category `year-round-programs` + a
jam-word title) because ingest's conservative regex wouldn't catch the name;
the festival's ticketed "SJW All-Star Jam" closer stays a show. Tribe's
padded `end_date == start_date` is dropped rather than stored as a
zero-length end. Programming is seasonal (festival June–August, roughly
monthly jams otherwise) — near-empty off-season feeds are normal, per the
Mills Littlefield precedent. **Stanford Live** (Bing Concert Hall / Frost
Amphitheater, the Sep–Jun season) is a separate org and site, explicitly not
covered.

## Venue batch 5, tranche B: ten more from the sweep (July 2026)

The rest of the buildable greens, via a second (successful) three-agent
fan-out plus inline probes. Diego's priority note mid-batch — **Santa Cruz
is the lowest-priority region** — arrived with the SC agent already
building; its four venues shipped lean and land as recorded, with Bay Area
effort redirected to the remaining yellows (verdicts below).

Shipped (live counts at build): **Smiley's Saloon** (31, Bolinas server-
rendered cards), **The Lost Church** (17 — the WP page has no times, so
the scraper replays the PatronTicket/Salesforce box-office remoting API,
filtered to the SF room + Music tags), **Old First Concerts** (7, WooCommerce
products via month-submenu links with a weekday guard on year rollover),
**Little Lou's BBQ** (4, Simple Calendar widget with ISO datetimes + stated
ends; Pro Blues Jam typed jam; short widget horizon → nightly polling),
**Paramount Theatre** (7, carbonhouse + events_ajax lazy feed; movie
nights dropped), **Cal Performances** (3 now, season-long JSON-LD with
genre badges via the /calendar/ redirect; dance/theater dropped; possible
Greek Theatre cross-listings noted), and the four SC rooms: **Moe's Alley**
(35, TicketWeb popup-variant), **The Crepe Place** (97, Squarespace shared
core with flyer-title cleanup), **The Catalyst** (10, Rockhouse/Etix
cards), **Felton Music Hall** (34, Webflow cards + Tixr).

**Closed with dated evidence this pass:** The Big Easy Petaluma 429s even
at browser UA (IP-keyed, not UA-keyed — the Kuumbwa trick doesn't apply);
The Saloon's PDF calendar is a hand-lettered scan Vision garbles
(would ingest garbage names) and the old sfblues mirror is dead;
Sausalito Seahorse's calendar is a CalendarWiz embed currently serving
"Server busy" to everything including real browsers; Rio Theatre and
Sebastiani expose no Squarespace events collection at any obvious path
(deeper recon needed); Rancho Nicasio's Tribe rows are all-day with no
times anywhere first-party (unblock: the OvationTix API); Fox Theatre RWC
remains queued (ShoWare renders via JS — needs its API).

## Venue batch 5, tranche A: six from the internet-search sweep (July 2026)

A four-agent web sweep (SF / East Bay / Peninsula+South+North Bay / Santa
Cruz + creative long tail) surfaced ~20 verified-open, scrapably-green
venues foghorn lacked, plus a mortality list. The build fan-out hit the
session usage limit mid-flight, so tranche A shipped inline — the six
highest-value, cheapest-pattern venues:

- **The Dawn Club** (FiDi, jazz) — the revived trad/swing club; nightly
  jazz. First user of the new shared ``_squarespace_events`` core (the
  Piedmont/Lab collection-JSON pattern extracted into a helper; stated
  endDates flow through). 13 shows live.
- **Pier 23 Cafe** (Embarcadero, jazz) — shared core; Sunday BLUES JAM
  typed jam; mahjong/trivia filtered. 7 shows.
- **The Sound Room** (Uptown Oakland, jazz) — the sweep's biggest catch,
  "Home of Bay Area Jazz & Arts"; shared core + Eventbrite tickets;
  comedy/story-slam/illusion nights filtered. 24 shows.
- **Uptown Theatre Napa** (North Bay, rock) — Tribe REST (Dresher clone);
  comedy admixture dropped on title signal (unlabeled comedians pass —
  accepted). 16 shows.
- **Jazz Chez Hanny** (Portola, jazz) — the legendary Sunday house-concert
  salon; hand-maintained static homepage parsed as name/date/4PM/$25
  tuples. 4 shows.
- **Tom's Place** (South Berkeley, eclectic) — free-improv house series;
  hand-rolled static HTML over plain HTTP; **offsite presentations
  (SFPL/Gray Area/The Lab lines with street addresses) are skipped** —
  those venues are scraped directly; the page-stated 7:30 PM default is a
  stated time, not a fabrication. 3 shows (incl. a Lorin Benedict date).

**Tranche B queue** (all verified green 2026-07-18, endpoints known, not
yet built): Moe's Alley + The Crepe Place (TicketWeb "tw-" — check the
shared helper), The Catalyst (Etix), Rio Theatre + Sebastiani (Squarespace
core), Felton Music Hall (Tixr), Rancho Nicasio (Tribe — **agent salvage
note: its Tribe payload lacks start times**, needs detail-page times),
Smiley's Saloon (server-rendered /music/, NOT /upcoming-events/), Old
First Concerts (WP), Little Lou's BBQ (WP, "/calender/" misspelled), The
Lost Church SF (WP + comedy filtering), Fox Theatre RWC (**salvage note:
ShoWare renders via JS — needs its API**), Paramount (carbonhouse),
Cal Performances (WP presenter, music filter).

**Yellow/red sweep verdicts worth keeping:** The Big Easy Petaluma (WAF
429s; ~25-30 jazz/blues shows/mo — jackpot if the Kuumbwa browser-UA
approach works), The Saloon (monthly **PDF** calendar — the OCR layer may
apply), Sausalito Seahorse (EventON ajax probe), Ashkenaz + Jupiter
(JS-walled Squarespace), Ceremony + Mountain Winery (ticketing APIs),
Angelica's (thin first-party calendar), Bazaar Cafe (GCal iframe
suspected), Royal Cuckoo (nightly B3 jazz, NO website — Instagram only).
**Confirmed closed/dead, do not re-sweep:** Thee Parkside (July 5 2026!),
Blue Note Napa downtown (12/2025; Meritage Summer Sessions survive),
Michael's on Main (fire), Fenix, Mama Kin, Silo's, Golden Squirrel,
Birdland Jazzista, Amado's, Luggage Store new-music series (retired
12/2024), Active Music Series (2019), Terrapin Crossroads. All three
HopMonks share the same Eventim block.

## Followed-first display precedence (July 2026)

Shows at watched venues or with watchlist-matched performers now lead
every view: the top of each date group in the list, the leading slots in
week/month day cells (so the month grid's two visible headliners prefer
followed acts), and the far-left columns of the day grid (a column holding
any followed show sorts ahead of the earliest-set ordering).

Mechanics: the page computes a ``followedShowIds`` set server-side and the
views apply a stable followed-first sort — time order preserved within
each bucket. Matching mirrors the backend's **token-bag** semantics
(``lib/precedence.ts``), not exact string equality, so a "lisa mezzacappa"
follow floats any billing she appears inside — the same reason the
watchlist filter works on messy billings. No new visual chrome: the rows'
existing ✓ and ★ affordances are the explanation for the float.

## Stated end times: day-grid blocks stop guessing (July 2026)

Diego caught the day grid drawing every block at the nominal 90 minutes
even when the source states an end — Wyld Jam is explicitly 1:00–4:00.
The data model simply had no end column; now it does.

- **`ScrapedShow.end_local` → `shows.end_local_time` (nullable) → API.**
  Stored as the venue-local "HH:MM"; an end clock-time earlier than the
  start means past midnight ("9:30pm - 2:00am"). Additive column with the
  usual migration guard; upsert refreshes it nightly.
- **Eleven scrapers now emit stated ends** where the source publishes
  them: the Tribe family (Mr. Tipple's, Madrone, Natural Grocery Annex,
  Dresher, Kuumbwa — `end_date`), Wyldflowr (Viewcy `ends_at`), Mills
  (Trumba `endDateTime`), Meyhouse (Wix `endDate`), the two .ics feeds
  (Bird & Beckett, DNA Lounge — `DTEND`), and the three range parsers
  (Little Hill, Poor House Bistro, Make-Out Room), whose regexes were
  already matching "7-11pm" ends and discarding them.
- **DayGrid** uses the stated duration when present (falling back to the
  90-minute estimate), extends the grid's hour range to cover late stated
  ends past midnight, and keeps the no-overlap clamp against the venue's
  next set either way.

Sources with no published end (SeeTickets/TicketWeb cards, most HTML
listings) keep the estimate — absence stays honest, nothing is fabricated.

## Venue batch 4: Indexical, Meyhouse Jazz, Make-Out Room, Poor House Bistro (July 2026)

Four scrapers from the audit docket (two "easy", two "best effort" per
Diego), plus an OCR-layer upgrade. Also in this pass: **The New Parish
re-verified still-empty** (the pre-solved admin-ajax endpoint answers
``{"events":[]}`` as of 2026-07-18 — recheck again in a few weeks), and
**The Monkey House is fetch-blocked** (Wix 429s every request from this
IP even at browser UA after long cooldowns; the OCR pattern is ready if
the throttle passes — retry on a later pass, gently).

- **Indexical** (Tannery Arts Center, Santa Cruz — second Santa Cruz
  venue) — server-rendered Rails listing whose event slugs carry the date
  (``/events/2026-07-27-…``), so future pages are known before fetching;
  detail pages state "Doors at 6:30pm | Show at 7pm" (sometimes "Event
  at"), price or "FREE to Attend". Monthly synth-co-op *meetups* drop on
  slug signal; open mics stay (inference types them jams).
- **Meyhouse Jazz** (Downtown Palo Alto, jazz) — the SFJAZZ-designed
  listening room inside Meyhouse restaurant. The Wix surface looks
  JS-locked but server-renders everything needed: ``/event-list`` links +
  per-page **Wix Events scheduling JSON** (UTC start + timeZoneId) +
  og:title + stage address. Filtered to the Palo Alto stage (Sunnyvale /
  San Ramon exist); 5 PM / 8 PM seatings kept as separate shows (Yoshi's
  precedent); fullwidth-paren seating suffixes stripped from titles.
- **Make-Out Room** (Mission, eclectic) — the fleet's oddest fetch:
  HTTPS is broken (TLS handshake failure), so plain HTTP; the calendar is
  hand-written Weebly blog posts on the homepage with a ~4–5 day horizon
  (nightly polling IS the coverage model; the RSS mirror has empty
  bodies). Parser: date from the post header; blocks close on time-range
  lines (including as suffixes); multi-line billings join ("JAZZ" / "at
  the" / "MAKE OUT ROOM!"); "7pm show" overrides range starts; trailing
  SET LISTS (gated on time-only marker lines — the thing that separates
  them from Instagram-promo prose) become support, so the watchlist sees
  Lorin Benedict behind "JAZZ at the MAKE OUT ROOM!".
- **Poor House Bistro** (San Jose Little Italy, eclectic — new venue, not
  in BI) — the OCR pattern's second venue and first **month-grid** flyer.
  Two lessons for the pattern: (1) small flyers OCR measurably worse —
  both engines now upscale sub-1600px images 2× (this fixed "BLUFM-OCKERS"
  → "BLUES ROCKERS"); (2) **compute grid dates, don't read them** — day
  numbers merge into neighboring act text, so cell dates derive from the
  month's first weekday + weekday-header columns + anchor-row bands, with
  a majority sanity check against cleanly-read anchors that refuses a
  shifted grid outright. Cells split into (act, time-range) segments
  (two-slot Sundays work); CLOSED cells drop; the Wednesday "WILLIAM
  JOHNSTON TRIO HOST PHB JAZZ JAM & <brewery>" residency and THEME JAMs
  are explicitly typed jams. Known noise: a couple of garbled Sunday-cell
  names per month ride along verbatim.

Live at ship time: 2 / 13 / 8 / 8 shows respectively (Meyhouse counts both
seatings; MOR counts multiple events per night).

## Manual event-type correction — clickable jam badges (July 2026)

Mark Clifford's Standards Hang at Little Hill is a jam session, but nothing
in the billing says so — title inference can't know what only the user
knows. Diego asked for a way to tell foghorn directly.

- **Stored as a venue+billing rule, not a row edit.** The nightly upsert
  rewrites ``shows.event_type`` (``excluded.event_type``), so flipping the
  row would be clobbered within a day. Instead ``PUT
  /api/shows/{id}/event_type`` records the correction in
  ``event_type_overrides`` keyed ``(venue_id, headliner_canonical)`` —
  derived from the show the user clicked, but owned by the billing. That
  buys two properties for free: re-ingest can't undo it, and **recurring
  sessions stay corrected** — when Bay Improviser mints August's Standards
  Hang row, the same billing at the same venue resolves to jam with no
  further action. ``DELETE`` reverts to the inferred type.
- **Resolution at read time.** All show reads resolve
  ``COALESCE(override, shows.event_type)`` (one source of truth, no
  write-through duplication), and the ``?type=`` facet filters on the
  resolved value — corrections move shows between the Shows/Jam chips.
- **UI: the badge is the control.** The amber jam badge is now a button
  (click to unmark), and every non-jam row carries a faint dashed "jam?"
  chip (click to mark). Optimistic flip, revert on failure, soft refresh.
  Same single-tenant posture as the origin/genre correction endpoints —
  but this one earned a UI because it's a while-browsing gesture, not a
  data-cleanup task.

Adjacent to Phase 7.3 (user-defined tags): this is the second user-owned
per-show metadata surface after the watchlist, and the venue+billing rule
shape may be the right pattern for 7.3's recurring-event cases too.

## Pluggable OCR engines (July 2026)

Follow-up to the Little Hill OCR scraper, per Diego: future hosting or
open-sourcing must not be locked to Apple Vision. OCR is now a seam, not a
dependency.

- **`foghorn/ocr/`** defines the engine contract — a callable
  ``(image_bytes) -> list[OcrLine]`` in normalized bottom-left box space —
  plus ``get_engine()``: explicit name → ``FOGHORN_OCR_ENGINE`` env var →
  platform default (``apple_vision`` on macOS, ``rapidocr`` elsewhere).
  Scrapers import only the contract; the Little Hill parser didn't change
  shape at all.
- **Two real engines, both validated on the live July flyer.**
  ``apple_vision`` (moved from the scraper) remains the darwin default and
  quality bar. ``rapidocr`` (ONNX PP-OCR via ``rapidocr-onnxruntime``, the
  new ``rapidocr`` extra) runs anywhere with no system binaries — verdict
  from the side-by-side: all rows detected with correct geometry and it
  even reads "OoO" better than Vision, but **inter-word spaces are lost on
  this flyer's font** ("RainbowCityPark"), which degrades act-name
  fidelity and watchlist token matching. Structure survives; prefer Vision
  where available.
- **Parser hardening from the second engine's real output** (both engines'
  fixtures are checked in and tested): date cells without spaces
  ("WED7/1") and fullwidth commas ("(Greek，8pm") are normalized —
  RapidOCR's fixture parses to the identical 24-show/skip structure as
  Vision's.

Live-verified by running the same scraper under both engines
(``FOGHORN_OCR_ENGINE=…``): identical show structure, the documented name
degradation on rapidocr. A future engine (hosted OCR API, a better local
model) is one ~50-line module implementing ``recognize``.

## Little Hill Lounge via on-device OCR — the flyer-venue pattern (July 2026)

Little Hill (El Cerrito) publishes its calendar **only as a monthly flyer
JPEG** — the blocker on record since the venue-expansion sweep. Diego asked
whether a lightweight off-the-shelf OCR model could crack it; the answer
turned out to be sitting in the OS.

- **Apple Vision, not a model dependency.** The nightly scrape runs on a
  Mac, and macOS ships `VNRecognizeTextRequest` — no service, no API key,
  no weights to manage. On the real July flyer it read **all 30 calendar
  rows verbatim** (the only misreads: the stylized logo, which we ignore,
  and letter-O runs as zeros — "OOO" → "00O" — a glyph confusion that
  language correction can't fix and that we accept). The flyer helped: it's
  cleanly typeset, not hand-lettered — worth checking per venue before
  assuming "flyer" means "unreadable."
- **Layout parsing from bounding boxes.** Vision returns normalized boxes;
  `DAY M/D` lines anchor rows, description-column lines pair by nearest
  center-y (OCR emission order is NOT top-to-bottom reading order — a
  description can precede its date line), leftovers attach upward as
  continuation lines (multi-line bills). Comma bills split
  headliner/support; "w/" prefixes and unbalanced-parenthetical flyer
  typos are trimmed.
- **Guardrails.** The flyer year/month come from the image's WordPress
  upload path (`/uploads/YYYY/MM/`) rather than the clock, and rows whose
  month disagrees are dropped as misreads; rows without an explicit time
  are skipped, not fabricated (B&B convention); the blanket "ALL SHOWS
  $10" line is not propagated as per-event pricing; non-music rows
  (karaoke/bingo/movie/"OPEN FOR") drop on title signal. First live run:
  11 shows for the rest of July.
- **Platform coupling, contained.** `ocr_image` lazy-imports the pyobjc
  Vision/Quartz bridges (pyproject marks them `sys_platform == 'darwin'`);
  off-macOS the scraper raises a clear error that surfaces in
  `/api/health/scrape`, while the parser stays pure and is tested from the
  checked-in real OCR fixture on any platform (CI included). Slug matches
  the BI row → promoted out of quarantine (18 → 17).

The pattern generalizes: The Monkey House (Berkeley) — the audit's other
flyer-image venue — is now a candidate for the same treatment, with the
caveat that its flyers are designed art, not a typeset list; verify OCR
quality on real flyers first.

## Kuumbwa Jazz Center + the Santa Cruz region (July 2026)

Follow-through on the long-tail audit's biggest unclaimed prize, per Diego's
call to add the region rather than skip the venue.

- **Santa Cruz region.** ``"Santa Cruz"`` joined the Region literal
  (backend), the API's `_REGIONS`, and the frontend's region chip +
  venue-picker group ordering. The chip auto-activates the moment a
  Santa Cruz venue exists (the "(soon)" affordance handles the interim on
  empty fixtures/tests).
- **Kuumbwa Jazz Center** (Downtown Santa Cruz, jazz) — Tribe Events REST,
  46 shows in the 90-day window at ship time. **The trap worth remembering:
  a UA-keyed LiteSpeed cache.** For non-browser User-Agents the site serves
  one stale cached API response for *any* query string — `per_page`,
  `start_date`, and `page` are all silently ignored, which makes
  `next_rest_url` pagination loop forever on the same ten events and makes
  the API look param-deaf. A browser UA bypasses that cache tier entirely
  and the API behaves. The scraper uses a browser UA (documented exception
  to the polite `foghorn-scraper` string) plus an id-seen pagination guard
  so a cache regression degrades to a partial scrape, not a hang. Title
  conventions: `CANCELLED – …` rows drop, `RESCHEDULED: ` prefixes strip,
  master classes/workshops drop on signal. Slug matches the BI row →
  promoted out of quarantine (19 → 18 quarantined venues).

Two related verdicts from the same session, recorded so they don't recur:

- **Arc Gallery: scraper declined on data.** Diego initially called for an
  ICS scraper with a music filter, but the calendar's content killed the
  premise: of 156 events across Jan 2025–Jul 2026, exactly **2** were
  music, and the upcoming window (43 events through Oct 2027) contains
  zero — it's install/de-install logistics, receptions, figure drawing,
  reading series. A music-filtered scraper would emit ~1 show/year against
  real maintenance surface. Arc stays in the aggregator quarantine, where
  BI carries whatever music actually happens there.
- **Red Poppy Art House: dormant, watch-listed.** Not in foghorn and not
  even in BI's venue list. The site runs Tribe (endpoint answers validly)
  but publishes **zero events** — the events archive renders 2011-era
  imports. Nothing to scrape until they resume publishing; the endpoint is
  pre-solved for that day (deferred-list watch item).

## Long-tail audit + four scraper promotions: Dresher, The Lab, Gray Area, Mills Littlefield (July 2026)

A user-directed audit of all 25 Bay Improviser quarantine venues ("which of
these have a well-maintained, scrapable web presence the aggregator is
undercounting?"), then scrapers for the four Bay Area greens. BI was carrying
~1 upcoming show per venue where the venues' own calendars carried 7–12.

**Shipped scrapers** (each seeds a venue row whose slug matches the
BI-created row, flipping `source` aggregator→seed — the Wyldflowr promotion
mechanism):

- **Dresher Ensemble Studio** (West Oakland, eclectic) — WordPress Tribe
  Events REST, the Mr. Tipple's/Madrone pattern. Bills arrive as one title
  with literal `<br>` separators (first segment headliner, rest support);
  multi-night runs are one Tribe row per date. Also the home of the weekly
  **West Oakland Sound Series** (sfSound + New Performance Traditions), so
  a `VENUE_ALIASES` entry routes that BI series name here and the
  aggregator's duplicate guard defers to this scraper.
- **The Lab** (Mission, eclectic) — Squarespace `?format=json` collection
  (`/projects`), the Piedmont Piano pattern but trap-free: the payload
  pre-splits `upcoming` from `past`. Music carries a `Concert` category;
  Dice (`link.dice.fm`) anchors in the body give `ticket_url`.
- **Gray Area** (Mission, electronic) — no Tribe REST and no event post
  type; server-rendered `/events/` listing (redirects to `/visit/events/`)
  walked into per-event pages whose Yoast `@graph` JSON-LD holds a
  schema.org Event (ISO startDate with offset). The CJC
  listing-plus-detail-pages pattern. Slug prefilter drops the education
  program (courses/workshops/book club/talks) before fetching; Yoast's
  " - Gray Area" suffix and multi-night "Friday, July 17" date suffixes come
  off the name. **Cybersentics Book Club** is a Gray Area program — aliased
  to this venue.
- **Mills College Littlefield Concert Hall** (Oakland, eclectic) — the hall
  publishes nothing, but Mills Performing Arts feeds its site from a public
  Trumba/25Live JSON (`25livepub.collegenet.com`; .ics/.rss siblings exist).
  Rows carry an explicit `template: "Oakland - Music Event"` discriminator +
  a `location` naming Littlefield + a `canceled` flag, so filtering is
  data-driven, not heuristic. Descriptions yield Eventbrite `ticket_url` +
  "Tickets: $…" `price_text`. Seasonal Sep–Jun programming; near-empty
  summer feeds are normal.

**Audit verdicts worth keeping** (evidence-backed, 2026-07-17; the
remaining 21 venues):

- *Scrapable with real effort (yellow):* **Make-Out Room** — genuine Weebly
  RSS (`/2/feed`) but the site's TLS handshake is broken (plain-HTTP fetch
  only), titles are just dates with lineups in post bodies, ~4-day posting
  horizon. **Meyhouse Jazz** (Palo Alto) — the jazz program of Meyhouse
  restaurant (SFJazz-designed listening room); maintained server-rendered
  Wix pages, 5pm/8pm seating duplicates, multi-location (Sunnyvale, San
  Ramon) disambiguation needed. **Artists' Television Access** — live
  month-grid HTML + RSS but events post only days ahead (needs frequent
  polls, never a long horizon; WP REST auth-blocked). **The Monkey House**
  (Berkeley listening room) — actively programmed but the calendar is
  flyer images; homepage text blurbs allow partial extraction only.
  **Peacock Lounge** — current but hand-edited WordPress page, low volume.
  **Shapeshifters Cinema** — maintained static HTML, ~3 events, zero
  structure.
- *Santa Cruz (region-taxonomy decision needed before any build):*
  **Kuumbwa Jazz Center** — clean Tribe REST, **77 upcoming events**, the
  biggest single prize found; **Indexical** — easy server-rendered HTML with
  GCal-template links; **Santa Cruz Civic Auditorium** — active but both
  first-party hosts 403 plain fetches (headless territory).
- *Easy but low-value pending a product call:* **Arc Gallery** — public
  Google Calendar ICS (~38 future events) but music is a subset of gallery
  programming; needs a filter story.
- *Nothing to scrape (aggregator coverage is the right coverage):*
  **Little Hill Lounge** (re-verified: flyer JPEG, Tribe still uninstalled
  per the wp-json namespace list), **Berkeley Finnish Hall** + **Oakland
  Scottish Rite** (rental halls; promoters publish, the halls don't),
  **Spruce Street Concerts** (private Berkeley-hills house series, email
  RSVP), **Sculpture Studio @ Project Artaud** (private studio),
  **espace_étale** (an *online* weekly stream, arguably wants an ONLINE
  region tag), **Flip Flop Farms** (Pescadero farm; one-off festival
  rental), **Guitar Wars** (San Jose guitar shop, Instagram-only; the
  adjacent "Pete Be Center" may become the scrapable room later),
  **Temescal Arts Center** — site stale since Jan 2025, Instagram-only,
  and Yelp marks it CLOSED (June 2026) while BI still lists shows there:
  needs a human check.

**Post-merge data cleanup:** the two series' obsolete aggregator venue rows
(`west_oakland_sound_series`, `cybersentics_book_club_at_gray_area`) and
their shows were deleted from the canonical DB (backup taken) — their events
now live under the promoted venues via the aliases, deduped against the
scrapers by the aggregator ingest's duplicate guard.

## UI consolidation: one browsing surface + day time×venue grid + sticky date headers (July 2026)

A user-directed UX tightening pass (dogfooding, no ticket) with one structural
change and two view refinements.

- **The `/watchlist` and `/venues` pages folded into `/` as filters.** Both
  pages had become near-clones of the main page — same FilterBar, same
  ShowList — but *without* the List/Day/Week/Month view switcher, so the two
  "following" features were second-class exactly where they mattered most.
  The backend already treated them as filters (`?watchlist=true` /
  `?venue_watchlist=true`); now the UI does too. A **Watchlist (N)** chip
  joins the existing **My venues ★** chip in a "following" cluster in the
  FilterBar's quick-chip row, and each filter's management surface (the
  follow-by-name form + removable entry chips; the followed-venues row with
  unfollow ★s) renders inline under the filter bar only while its filter is
  active — the default calendar stays clean, and following now works in every
  view. The old routes remain as param-preserving `redirect()` stubs so
  bookmarks and shared links keep working; the nav slimmed to
  `Shows | Add event | Inbox` (the watchlist count moved from the nav onto
  the chip). VenuePicker's now-unused "follow" mode (only `/venues` used it)
  was removed. Lesson recorded: when a feature page duplicates the main
  surface minus capabilities, it wants to be a filter, not a page.
- **Day view became a time × venue grid** (`DayGrid.tsx`). The old day view
  rendered the same list as List view scoped to one day — near-zero marginal
  value. Now venues with shows that day form columns (ordered by earliest set
  time), an hour ruler runs down a sticky left axis, and each show is a block
  positioned at its start time, so an evening reads as one glance: what
  overlaps, what's early vs. late, what's bookable back-to-back. The data has
  no end times, so blocks get a nominal 90-minute length clamped against the
  venue's next set (no overlaps) with a legibility floor. Blocks carry a
  genre-hued left accent matched to the badge palette and link out to tickets
  (falling back to the source page). Busy nights scroll horizontally; the day
  view joined week/month at the wide page width.
- **Sticky date headers in List view.** The per-day headers now stick just
  below the sticky nav (translucent + backdrop-blur, matching the nav's
  treatment) so the date stays visible while scrolling a long window. The
  `showDateHeaders` prop died with the old day view, so ShowList always
  renders headers now.

E2e coverage moved with the features: the watchlist suite now exercises the
chip toggle, the redirects (bare + deep-linked param merging), and the inline
management panel; a new `day-grid.spec.ts` covers the grid's columns, hour
ruler, and ticket-link blocks.

## Wyldflowr Arts scraper + promotion out of aggregator quarantine (July 2026)

Wyldflowr Arts (809 37th St, North Oakland) — the nonprofit BIPOC-woman-owned
arts space founded by Dr. Nora Free and Dr. Tiffany Austin — is now a
first-class scraped venue. Diego flagged it as a favorite he was missing.

- **Source: the venue's Viewcy org API**, not its own site. Wyldflowr sells and
  lists through [Viewcy](https://www.viewcy.com) (a live-music ticketing
  platform) and embeds it on `/events` as a `viewcyembed.com` iframe. The
  embed's own JS revealed the endpoint — `www.viewcy.com/api/o/wyldflowrarts/courses`
  — public, unauthenticated, no Cloudflare, and `robots.txt` disallows only
  `/auth`, `/register`, `/manage`, `/ticket*`. Clean JSON beat parsing the DOM.
- **The trap worth remembering.** `wyldflowrarts.com/events?format=json` also
  answers 200 with a plausible Squarespace events collection — but it's a
  **stale leftover** whose newest item is 2025-08-24. The live calendar renders
  client-side from the iframe, so a plain HTTP fetch of the venue's own page
  sees nothing current, and paginating that collection reads as a *dormant
  venue* — which is exactly the wrong conclusion. Rendering the page in a
  browser is what surfaced the real source. If a Squarespace venue looks
  abandoned but the site is otherwise maintained, look for an embed.
- **Model.** Viewcy nests dated `events` under a `course` (its unit of
  programming), flattened here to one `ScrapedShow` per event. `starts_at` is a
  UTC instant, converted to naive venue-local (the date rolls back a day for
  evening shows — a naive truncation would file them late).
- **Non-music filter.** Items carry a `category_id` that today splits classes
  (359) from events (360) perfectly, but those ids are org-authored groupings
  the embed's JS never reads, so they'd churn if the venue reorganized. We
  filter on the self-describing signals instead — workshop-ish tags, then a
  narrow title check — erring toward inclusion for untagged named bookings, as
  Bird & Beckett does. Mike Monford's 8/30 master class + evening concert are
  separate courses, so "keep the concert, drop the workshop" falls out for free.
  `Wyld Jam` is tagged `jam-session`, which sets `event_type="jam"` explicitly —
  the ingest's jam-title regex would miss it (no "session"/"night"/genre word).
- **Promotion needed no migration.** Bay Improviser had auto-created
  `wyldflowr_arts` as a `source='aggregator'` quarantined row (venue 54) holding
  3 community-entered shows. `venues.upsert` overwrites `source` from the
  seed row, so adding the seed entry flips `aggregator` → `seed` on the next
  seed run. (Note: the ticket asked for `source='scraper'`; the enum is
  `seed | manual | aggregator` — `'seed'` is the first-class value.)
- **The aggregator rows deduped away entirely.** Ingest reported
  `created=9 updated=3`: all 3 Bay Improviser rows matched the natural key
  exactly (Super P's 7/30 19:30, David Boyce 8/8 14:00, Mike Monford 8/30 16:00
  — same times as Viewcy's ground truth), so the scraper's rows overwrote them
  in place with `source='scrape'`. No duplicates, no `DELETE` cleanup needed.
- 12 shows live (2026-07-16 → 09-04), all visible with the long-tail toggle off
  and nothing pinned. 10 fixture tests over the real 14-course slate.

## Mailing-list ingest, stage 1 (Phase 8, July 2026)

The channel for artists whose gigs never reach a scrapeable surface (Dillon
Vado announces exclusively by mailing list). Deterministic — no LLM — with a
**review queue as the write gate**: emails parse into `pending_events`
drafts, and nothing enters `shows` until approved in the new `/inbox` UI.

- **Mail in, two ways:** an IMAP poller (`make mail-poll`; stdlib imaplib,
  read-only, Message-ID-deduped; `FOGHORN_IMAP_*` env, Gmail-label folder
  default "foghorn"; exits with a hint when unconfigured) — and a
  paste-an-email form on /inbox (`POST /api/inbox/ingest`), which makes the
  feature usable with zero configuration.
- **Rules parser** (pure, injected `today`): artist from a hand-maintained
  `mail_senders` map (managed in the UI), venue by scanning for known venue
  names, date/time regexes resolved to the next future occurrence.
  Unparseable emails still queue as raw text with the artist prefilled.
- **/inbox** ("Inbox (N)" in the nav): editable draft cards over the raw
  email, an amber token-match **possible-duplicate warning** (email-approved
  and venue-scraped billings won't collapse on the natural key — the warning
  is the stage-1 answer), Approve (creates the event through the manual-entry
  path, provenance `manual://email/<message_id>`) / Reject. Approved and
  rejected rows are kept as an audit trail.
- Verified end-to-end in a cold-start browser run, which also caught and
  fixed an approve-with-blanked-field bug (client now validates; the API 422
  remains the backstop). 31 new tests.

**Stage 2 (LLM extraction for emails the rules fumble) stays parked** on the
same enrichment-tier decision as 7.4's LLM stage.

## Search + venue-UX arc (July 2026)

Dogfooding fixes from tracking real artists, shipped as small PRs (#39,
#41–#45):

- **Token-prefix search** — "mezz" now matches "mezzacappa" while typing;
  watchlist matching stays whole-token for precision.
- **Follow a performer by name** on /watchlist — a bare "Lisa Mezzacappa"
  entry tracks the person across every billing shape; previously the only
  entry point was the '+' on a venue's verbatim billing string (which, for a
  multi-artist bill, tracks only that exact billing).
- **First-class venue UX**: venue names everywhere link to that venue's
  calendar (/?venues=slug); a "My venues ★" quick chip filters any view to
  followed venues; the 37-checkbox grid was replaced by VenuePicker
  (search-as-you-type, region groups, followed-first with ★s, removable
  selected chips — empty honestly means "all venues"), reused in follow mode
  on /venues; pins soft-refresh the surrounding server-rendered feed; event
  rows gained a "details" link to the event's own page alongside "tickets".

## Bay Improviser aggregator ingest (July 2026)

The one aggregator the May spike green-lit, shipped under the decided
quarantine-with-flag posture. A new **aggregator tier** distinct from
per-venue scrapers: `AGGREGATOR_SOURCES` runs after the venue scrapers in
every scrape (nightly + `make scrape`), recording an `aggregator:<source>`
slice in the run. Bay Improviser's calendar embeds a Google-Calendar link
per event (title / UTC start / free-text location) — parsed, converted to
Pacific, all-day entries skipped.

**Venue resolution:** exact canonical match (leading-"the" stripped) →
token-subset match either direction ("Bird & Beckett" ⊆ "Bird & Beckett
Books and Records") → a small alias map ("The Jazzschool" →
california_jazz_conservatory) → else auto-create a quarantined
`venues.source='aggregator'` row. **Duplicate guard:** community titles are
free-text blobs, so before ingesting at a *tracked* venue, any same-venue
same-date show whose headliner token-matches the blob marks it a duplicate —
the venue's scraper is authoritative. First live run: 49 events → 33
ingested, 16 correctly skipped as duplicates, 20 new quarantined venues
(Berkeley Finnish Hall, Temescal Arts Center, Artists' Television Access…)
— and **Little Hill Lounge**, unscrapeable directly (flyer-JPEG calendar),
is now covered through the aggregator.

**Quarantine semantics** (in the shows filter SQL): aggregator-venue shows
are hidden unless the "Long tail" toggle is on (`?long_tail=true`, a chip
that appears once aggregator venues exist), the venue is pinned (a ★
promotes it into the main UI everywhere), the venue is explicitly selected,
or the performer-watchlist filter is active — the watchlist always sees
through the quarantine, so a followed artist's gig at an untracked space
surfaces regardless. `/api/venues` now returns `source` so the picker groups
long-tail venues separately and genre chips ignore them.

## Venue watchlist (Phase 9, July 2026)

Follow venues the way the watchlist follows performers. `watched_venues`
(slug PK, single-tenant, mirroring the performer watchlist's contract),
`GET/POST/DELETE /api/venues/watchlist` (POST 404s unknown slugs), and
`?venue_watchlist=true` on `/api/shows` — empty watchlist matches nothing,
and the filter AND-stacks with everything else. Frontend: a ★ pin next to
venue names on show rows across all pages, and a `/venues` page ("Venues" in
the nav): followed venues as an unpin chip row, their upcoming shows through
the shared FilterBar/ShowList, and a collapsed all-venues grid for following
more (open by default when the list is empty). Follow-ons deliberately left:
digest inclusion of watched-venue shows, and the pin-promotes-quarantined-
venue interaction (waits for Bay Improviser ingest to exist).

## Venue batch 3: Club Deluxe + Club Fox; New Parish blocked (July 2026)

**Club Deluxe** (Haight, jazz) — server-rendered Simple Calendar (simcal)
list with epoch data-start attrs and covers embedded in titles; 46 shows
live (the best nightly-jazz add left in SF; publishes ~2 months out).
**Club Fox** (Redwood City, eclectic) — hand-authored homepage show blocks
with Eventbrite links; 14 shows incl. the free Music on the Square series;
the most drift-prone scraper in the house by construction. 37 venues total.

**The New Parish — blocked, with the pipeline pre-solved:** its TicketWeb
event-discovery widget was successfully reverse-engineered (admin-ajax
`get_events_for_calendar` + page nonce), but the venue's TicketWeb inventory
is currently *empty* — the API answers "No events found", TicketWeb's own
venue pages show no events, and aggregators agree. Likely a ticketing
migration. Re-sweep in a few weeks; the endpoint (or TicketWeb's
`venue/{id}/dateSummary/{date}.html` fragment API) is ready when inventory
returns.

## Venue batch 2: six more rooms (July 2026)

The sweep's easy-leftovers batch, shipped through the normal branch/PR loop:
**Bimbo's 365 Club** (North Beach; tw-/TicketWeb template, dark-in-July so 9
shows is real), **Neck of the Woods** (Inner Richmond; tw- on the homepage,
slash-separated bills split, signup-popup duplicates deduped), **August
Hall** (Union Square; tw- "list2" — times only exist on per-event pages, so
scrape fetches ~1 small page per show; "– Moved To …" title annotations
resolved: stripped when moved *here*, dropped when moved *away* since the
destination venue's scraper carries the show), **The Warfield** (Mid-Market;
carbonhouse/AEG static blocks + the platform's events_ajax lazy-load feed,
AXS links), **Thee Stork Club** (Uptown Oakland; SeeTickets, Rickshaw flavor,
per-event genre flows into the override layer; off-site sister-venue cards
dropped by venue line), **The UC Theatre** (Downtown Berkeley; static Webflow
with per-event genre, doors, and prices). 126 shows on the first live run,
zero errors; the tw- shared helper grew month-name dates, a price fallback,
and a time_lookup hook (existing venue tests unchanged). 35 venues total.

Remaining from the sweep list: Club Deluxe, Club Fox (Redwood City), The New
Parish (TicketWeb widget API), the Ticketmaster Discovery API spike
(Fillmore/Regency), and the North Bay region value (Mystic/Sweetwater/
HopMonk).

## Layered genre resolution + performer-genre bootstrap (July 2026)

Genre moved from a pure venue attribute to a three-layer resolution chain:
**per-show override → headliner's performer-level genre → venue default** —
in the `?genre=` filter SQL and the API's resolved `genre` field alike.

- **Phase 7.2 (per-show override).** The SeeTickets scrapers were parsing
  per-card genre to drop comedy and discarding it; it now threads into
  `ScrapedShow.genre` and normalizes to the coarse vocabulary at ingest
  ("Rock / Indie"→rock, "Other Content"→None). 92 shows picked up overrides
  on the first re-scrape — Wolfmother at eclectic-default GAMH files under
  rock, Valerie June (soul) at rock-default Chapel under funk. Manual entries
  keep unmapped genres verbatim.
- **Title-derived genre + wider jam patterns.** When neither source nor venue
  says anything useful, an unambiguous genre word in the title fills the gap
  (word-boundary matched, single-bucket only, curated venue leans never
  second-guessed; B3/Hammond reads as jazz). Jam inference widened to
  plurals, open mics, and organ sessions: 9 → 35 tagged jams.
- **Phase 7.4 stage 1 (deterministic performer genre).** `performers.genre`
  + `genre_source` with a unanimous-evidence bootstrap (`make tag-genres`)
  over per-show overrides, venue leans, and performer-name keywords; mixed
  evidence stays untagged. First run: 353/1,368 performers. Manual
  corrections via `PUT /api/performers/{canonical}/genre` are permanent.
  **The LLM stage for the remaining ~75% is deliberately deferred** — an
  open decision about accepting an LLM dependency in the enrichment tier
  (never ingest-of-record or serving); this deterministic layer is its
  validation baseline if it proceeds.
- **"Eclectic" demoted to honest absence**: no badge, no filter chip — it
  resolves from a mixed-booking venue's default and says nothing about the
  show. Every visible genre badge now carries signal.

## Calendar views + UI polish arc (July 2026)

The reading surface grew up alongside the data:

- **Day / Week / Month views** (`?view=` + `?anchor=`, URL-driven like every
  filter, which all apply across views). Day = the list scoped to one date
  with prev/Today/next; Week = Mon–Sun columns (stacked on mobile); Month = a
  classic grid, two headliners + "+N more" per cell, each cell linking into
  Day view. Calendar views derive their window from the anchor, so the
  list's date controls hide there.
- **Teal accent system** in `lib/ui.ts` — one token file for chip/input/link/
  button styles (collapsed five copy-pasted chipClass definitions), sticky
  translucent nav, tinted filter card, filled genre badges (outline-only read
  as gray at 10px), semantic badge colors (emerald local / amber jam / sky
  added-by-you) kept distinct from the accent.
- **Usability fixes from dogfooding:** the 26-venue checklist collapsed
  behind a summary disclosure ("Venues · all 29") with a responsive grid;
  mobile tucks advanced filters behind a "More filters" toggle (six shows
  visible on the first screen, up from zero); date inputs hold drafts and
  commit on blur — a native date input fires `change` per segment, so the
  old commit-per-change navigated mid-edit and snapped the field back, and
  the min/max cross-constraints blocked moving a range forward; the double
  clear-× on the search bar (WebKit's native control next to ours — the
  hide-it CSS gets stripped by the build minifier, so the input is now
  `type="text"` + `role="searchbox"`).

## Manual events + jam sessions (July 2026)

Two features prompted by a coverage gap: following two real artists (Lisa
Mezzacappa, Dillon Vado) showed that part of the local scene — house
concerts, one-off spaces, Instagram-only venues, festival one-offs — will
never be reachable by scrapers, and that jam sessions are a distinct thing a
player plans around.

**Manual events** (`POST /api/events`, `/add` in the UI, "Add event" in the
nav). A manual event rides the exact scraped-ingest path — same
canonicalization and natural-key dedup, so double entry is idempotent — but
is stamped `shows.source='manual'`: deletable through the API (scraped rows
refuse deletion since the next refresh would resurrect them) and badged
"added by you" with a remove affordance in the list. The venue is an existing
slug or a free-text new name; unknown names create `venues.source='manual'`
rows that appear in `/api/venues` and every filter with no scraper attached.
Provenance is preserved via an optional source link (flyer URL, IG post);
`manual://user-entry` otherwise.

**Jam sessions** (`shows.event_type`, `?type=show|jam`, Shows/Jam-sessions
chips, amber "jam" badge). Tagging precedence: explicit scraper tag > the
manual form's checkbox > a deliberately narrow ingest-time title heuristic
("jam session" / "open jam" / "jam night" / "<genre> jam") that can't misfire
on band names (Pearl Jam tribute stays a show — regression-tested). The
heuristic alone surfaced 9 real July jams already in the scraped data (Boom
Boom Room's funk jam, Ocean Ale House's weekly jazz jam, The Back Room's
singers session, Madrone's Saturday jam).

Both features are single-tenant/no-auth like the watchlist. ShowView now
carries `id`, `source`, and `event_type`.

## Performer origin tagging v1: local/touring (July 2026)

The most mission-aligned facet — "show me local acts to support" — shipped as
performer-level tags, since venues mix (Yoshi's books local trios between
tours; big rooms put local openers under touring headliners). No scraped
source publishes this, so v1 is **inference + correction**: a conservative
heuristic bootstrap (`make tag-origins`, idempotent, safe after every scrape)
scores each performer from evidence already in the DB — recurrence spread
over weeks (consecutive-night touring runs deliberately don't count),
multi-venue presence, venue booking priors (small nightly rooms ≈ local;
Fox/Greek *headliners* ≈ touring; mixed rooms contribute nothing), and
Ticketmaster/AXS headline slots — and only tags past a threshold, leaving
everything else unknown. `PUT /api/performers/{canonical}/origin` records
manual corrections as permanent (`origin_source='manual'`; the heuristic
never overwrites them, and a stale heuristic tag clears when its evidence
fades rather than fossilizing).

`GET /api/shows?origin=local|touring` uses any-performer semantics (matching
the watchlist): a touring headliner with a local opener matches `local`,
because the opener is why a support-local user would go. Frontend: "Local
acts"/"Touring" chips labeled "(likely)" that render only when tagged
performers exist in the result set, and a subtle "local" badge on tagged
names — touring gets no badge so unknown never reads as "not local".

First live bootstrap over the 26-venue catalog: **153 local / 29 touring /
1,144 unknown (86% deliberately untagged)**; spot check: touring 10/10,
local ~9/10. Recurrence evidence compounds as scrape history accumulates
(persisted shows outlive their dates), so coverage grows by re-running the
CLI — and the deterministic scorer doubles as the validation baseline for a
future Phase 7.4 LLM pass. "regional" (Bay-based but touring) deferred until
the two-way split proves too coarse.

## Venue expansion batch: 23 new scrapers + genre facet (July 2026)

A single feature-branch push (ad-hoc, user-directed — no per-venue tickets)
that grew foghorn from 3 scraped venues to 26 and shipped the Phase 7.1 genre
facet the new cross-genre diversity finally made meaningful. Built by parallel
coding agents (one per 1–2 venues) in an isolated worktree, with central
integration (registry, seed, docs) and a full-gate + live-scrape verification
pass at each merge point. Full 26-venue live scrape at ship time: **1,192
shows, zero errors** (SF 871 / East Bay 295 / Peninsula 26), idempotent on
re-run.

**New venues and their data sources** — the scraper-interface flexibility the
plan called for got exercised hard; almost every venue needed a different
source shape:

- **Black Cat** (SF, jazz) — Turntable Tickets performance API (JSON).
- **Ocean Ale House** (SF, eclectic) — the schedule TSV on GitHub that the
  client-rendered site itself fetches (`aspyrx/oah-content/events.tsv`);
  no-year dates roll forward across New Year.
- **Boom Boom Room** (SF, funk) — server-rendered rhp-events HTML with month
  separators; doors + show times parsed.
- **Madrone Art Bar** (SF, eclectic) — WordPress Tribe Events REST API (same
  pattern as Mr. Tipple's). Known gap: recurring nights entered as all-day
  Tribe events (~30/mo) carry no start time and are skipped.
- **Bottom of the Hill** (SF, rock) — the venue's famous hand-maintained
  static `calendar.html` (HTML 4.01 table, ISO-8859-1 with no charset header —
  fetcher pins encoding); bills in top-billing order, doors/cover/stubmatic
  links.
- **Rickshaw Stop** (SF, rock) — SeeTickets white-label calendar: server-
  rendered cards + nonce'd admin-ajax pagination (nonce fetched fresh each
  run); headliner/support pre-split; non-music genres dropped.
- **Kilowatt** (SF, rock) — Dice.fm events API via the public widget key in
  the site's DiceEventListWidget config; fee-inclusive prices in cents.
- **The Knockout** (SF, rock) — Squarespace calendar-collection
  `GetItemsByMonth` JSON (the older `/calendar` collection is stale 2023 test
  data — a trap for future re-scrapes); no ticket/price/doors published.
- **Yoshi's** (Oakland, jazz) — the fullCalendar JSON feed behind the venue
  calendar (one entry per *set*, so 7:30/9:30 shows land separately — better
  than the HTML, which collapses them), prices joined from the HTML page
  best-effort. Biggest single venue: 125 shows.
- **California Jazz Conservatory** (Berkeley, jazz) — server-rendered
  `concerts.jazzschool.org` listing + per-event pages for times (classes never
  appear on that subdomain; movie nights dropped). VBO ticket widget means no
  static ticket/price.
- **Ivy Room** (Albany, rock) — Venuepilot public GraphQL API (`accountIds`
  from `window.venuepilotSettings`); the Squarespace site is a JS shell.
- **924 Gilman** (Berkeley, rock) — the collective's server-rendered
  ShowSlinger ticketing listing (the Wix calendar is client-rendered with the
  Wix Events app disabled). Unticketed shows outside ShowSlinger won't appear.
- **El Cerrito Natural Grocery Annex** (El Cerrito, jazz) — company-wide Tribe
  REST API filtered to events at the Annex venue record; "The Annex Sessions:"
  prefix stripped. First venue to activate the **East Bay region chip**.

A second wave, targeted by a scrapability sweep of ~36 remaining venues,
added ten more (two shared-template parser families did the heavy lifting):

- **The Independent** + **Cafe du Nord** (SF, rock) — one shared
  `_ticketweb_calendar` helper for the TicketWeb "tw-" WordPress template.
  Cafe du Nord's hidden per-event dialogs supply dates/doors/prices; Swedish
  American Hall shows bill under cafe_du_nord.
- **Great American Music Hall** (eclectic) + **The Chapel** (rock) — the
  SeeTickets white-label platform Rickshaw Stop established, in two markup
  flavors; sports watch parties and "Private Event" hold cards dropped.
- **Fox Theater Oakland** + **Greek Theatre Berkeley** (East Bay, rock) — one
  shared `_ape_listing` helper for their common APE template.
- **DNA Lounge** (SF, electronic) — the venue's self-published **.ics feed**,
  the cleanest source in the batch. First "electronic" genre venue.
- **Cornerstone Berkeley** (rock) — server-rendered JSON-LD + Tixr; startDate
  is date-only so times come from adjacent card markup (skips loudly if the
  markup shifts).
- **The Back Room** (Berkeley, eclectic listening room) — Humanitix JSON-LD
  merged with the public tRPC events endpoint behind the "Load more" button.
- **Guild Theatre** (Menlo Park, eclectic) — homepage JSON-LD + card times.
  **First Peninsula venue** — activates the third region chip.

Sweep verdicts worth keeping (see the deferred list for blocked venues):
Freight & Salvage and The Midway sit behind Cloudflare; The Fillmore is a
Live Nation JS shell (a **Ticketmaster Discovery API spike** would cover it
and Regency Ballroom); El Rio is JS-only; Eli's Mile High/Golden Bull have
dead sites; Starline Social Club appears closed. Still-easy leftovers for a
future wave: The UC Theatre, Bimbo's 365, Neck of the Woods, The Warfield,
August Hall (all TicketWeb/static families), Club Deluxe, Club Fox (Redwood
City), Thee Stork Club (SeeTickets), The New Parish (TicketWeb widget API).
North Bay (Mystic Theatre — SeeTickets, Sweetwater, HopMonk) needs a "North
Bay" region enum value first.

**Blocked (no scrapeable calendar exists):**

- **For The Record** (SF Cow Hollow hi-fi listening bar — *not* the Oakland
  guess): one-page Squarespace site, all programming Instagram-only.
- **Little Hill Lounge** (El Cerrito): calendar is a monthly flyer **JPEG** on
  a one-page WordPress site; a former Tribe install was removed. Bandsintown
  has it but 403s plain HTTP. Would need OCR or a headless browser.

**Genre facet (Phase 7.1)** shipped alongside: `venues.genre` (TEXT, nullable)
with an additive-column migration guard in `init_schema` (the first schema
change against pre-existing DBs — `CREATE TABLE IF NOT EXISTS` skips existing
tables, so there's now a `_add_column_if_missing` PRAGMA check), threaded
through repo/API (`?genre=`, case-insensitive, AND-stacks with the other
filters) and both venue payloads. Frontend `GenreFilter` chip row renders from
the distinct genres in `/api/venues` (data-driven like the region chips;
hidden below two genres). Current values: jazz ×8, rock ×12, eclectic ×5, electronic, funk.
Distribution at ship: jazz 455 / rock 441 / eclectic 213 / electronic 68 / funk 15.

**Ingest fix surfaced by the full live run:** venues sometimes bill the same
act twice (headliner repeated in the support list, or "TBA" filling several
slots), violating the `show_performers (show_id, performer_id)` PK.
`_build_bill` now dedupes by performer, earliest billing position wins —
regression-tested. This was invisible with 3 venues and immediate with 16.

Tests: 128 → 394 (every scraper has a trimmed-real-fixture suite with a
pinned `today`). The venues-endpoint and seed tests now derive expectations
from `SEED_VENUES` + `REGISTERED_SCRAPERS` instead of a hardcoded four-venue
list, so future venue adds don't touch them.

## Aggregator evaluation spike (May 2026)

Time-boxed research spike ([#29](https://github.com/diegoSQK/foghorn/issues/29))
evaluating whether third-party **aggregators** could feed foghorn's ingest
pipeline and short-cut the per-venue-scraper grind ahead of a Phase 5+ re-scope.
Five candidates scored against a fixed 8-point rubric (data shape, coverage,
genre, freshness, dedup, access, ToS, verdict). Output is memos only — no
production code, no `PROJECT_PLAN.md` change (the re-scope is the PM thread's
follow-on). Per-candidate detail: [`docs/spikes/aggregator-evaluation/`](spikes/aggregator-evaluation/);
synthesis + the open question: [`RECOMMENDATION.md`](spikes/aggregator-evaluation/RECOMMENDATION.md).

Headline findings:

- **One "in": Bay Improviser** ([memo](spikes/aggregator-evaluation/bay-improviser.md)) — the only source that's genuinely ingestible *and* on-target for the jazz/new-creative wheelhouse: robots-permissive HTML calendar with per-event iCal/gCal structured fields, surfacing dozens of DIY/creative rooms per-venue scrapers will never reach. Caveat: community-entered free text, so it needs venue-name aliasing + UTC→local conversion + a **fuzzy secondary dedup pass** (exact natural-key dedup won't catch its free-text headliner blobs / one-off improv-ensemble names).
- **Strongest signal — aggregator ingest does NOT replace per-venue scraping; it can only narrowly augment it.** Recommended re-shape: **Augment** (keep Phase 5 per-venue as the backbone + add Bay Improviser as one additive source). Phase 6 (LLM-assisted per-venue) stays the real scaling lever, not aggregators.
- **Biggest surprise** — the two clean *global* APIs that were supposed to define "the easy path" (Songkick, Bandsintown) are both **closed to a small unlicensed aggregator**: no obtainable key/`app_id`, ToS that ban scraping, edge-level bot walls (Songkick 406 / Bandsintown Cloudflare 403) — *and* their coverage skews to touring acts at big rooms, exactly away from foghorn's small jazz rooms (Songkick shows Bird & Beckett with 0 upcoming).
- **Cleanest API — DoTheBay's** undocumented `events.json` ([memo](spikes/aggregator-evaluation/dothebay.md)): no auth, no anti-bot, ~1:1 with `ScrapedShow`, 239 music shows / ~87 venues in a sample week. But verdict is **Maybe→Skip**: its ToS bars scraping + restricts use to personal/non-commercial. Engineering-ready; gated on a *permission/feed* conversation, not code.
- **Most concerning ToS posture** — a tie: Songkick (§9.8 explicit "no robots/scrapers/data-mine", `ClaudeBot Disallow: /`, paid partner-only API) and Bandsintown (bars commercial use *and* redistribution *and* scraping the very public pages that would fill the gap). What's Poppin is simply **not feasible** (a YouTube talk show; no web-readable calendar exists).

Two live discovery POCs landed in `backend/scripts/` (`spike_aggregator_bay_improviser.py`, `spike_aggregator_dothebay.py`), each marked `# SPIKE — not production` and **not** registered in `REGISTERED_SCRAPERS`. Both run clean against live sources (Bay Improviser: 52 events parsed with UTC→PT conversion; DoTheBay: 17 music events with correct Pacific offset). **Open question for the PM thread before tickets are filed:** auto-accept aggregator-discovered venues into the DB, or maintain a curated venue allow-list? (Shapes the Bay Improviser ticket and interacts with the Phase 3.2 region/neighborhood facets — see RECOMMENDATION.md.)

## Watchlist digest endpoint (Phase 4.2, May 2026)

A read-only `GET /api/watchlist/digest` — the next-N upcoming watchlist matches,
chronological — for a future cron/email/push "what's coming up for you" consumer
(delivery itself stays deferred). Closes #27.

**Almost pure reuse of 4.1.** The endpoint runs `build_show_views(...,
watchlist=True)` over `[today, today + days]` (the exact `?watchlist=true`
filter + a today-anchored window), then the *only* new logic computes
`watchlist_matches` per row: which watched `display_name`(s) hit, via the same
`matches_token_bag`. A show can match more than one (a bill with two watched
names), so it's a list. Response: `{generated_at, matches: [...]}` where each
match is a `/api/shows` row **plus** `watchlist_matches`. Ordered by `start_utc`;
`limit` applied after match + ordering. Empty watchlist → `{generated_at,
matches: []}` (200, not 503 — nothing wrong, just nothing to send).

**Shape held up after dogfooding 4.1** — the ticket flagged it might want
reshaping, but reusing the filter + adding the matched-names field was exactly
right; no deviation. Params `days` (default 14) and `limit` (default 20) are
bounded (`ge=1`); out-of-range values 422 rather than silently clamping.

**No frontend, no new schema or match logic** — purely the new endpoint on the
existing `api/watchlist.py`. Tests (`api/test_watchlist_digest_endpoint.py`):
ordering + window filtering, the `watchlist_matches` field (incl. a
two-watched-names overlap), `days` widening, `limit` capping, and both
empty-watchlist and no-upcoming-matches → empty. Anchored to `date.today()` (the
digest uses the real clock, unlike the param-driven endpoints) so they're
date-independent. Verified live against the real DB.

**Release signal (PM thread):** with Phase 3 (#19/#20/#21) and Phase 4 (#26/#27)
both complete, this is the **v0.2.0 release-cut point** per PROJECT_PLAN
"Suggested sequencing". Per `RELEASE_PROCESS.md` the cut is a PM-thread ritual —
*not* done in this PR; surfaced for the PM thread.

## Watchlist data model, UI, and token-based matching (Phase 4.1, May 2026)

Diego's original "find shows where my friends are playing" ask. Closes #26. A
single-tenant watchlist of performers, a dedicated `/watchlist` view, add/remove
affordances on every show card — and the performer-match logic upgraded to
token-bag and shared between this and 3.3's search.

**Token-bag matching is now the canonical performer match
(`repo/performer_match.py`).** A query matches a performer iff every whitespace
token of the (canonicalized) query is a whole token of the performer's canonical
name. So "joshua redman", "redman joshua", and "Redman, Joshua" all match
"joshua redman quartet"; "redm" does **not** match "redman" (whole tokens, not
character substrings). This replaces 3.3's one-directional substring match —
**3.3's `?performer_query=` was refactored to use it too** (one matcher, same
UX in search and watchlist), and 3.3's tests gained a reordering case that the
old substring match would have failed. `matches_token_bag` is the pure function;
`token_match_sql` builds the parameterized `(' '||name||' ') LIKE '% tok %'`
predicate (OR across bags, AND within). Tokens are pre-canonicalized to
`[a-z0-9 ]`, so they carry no `LIKE` wildcards and need no escaping. FTS5/trigram
fuzzy matching stays deferred (PROJECT_PLAN Phase 7).

**Schema + repo.** `watchlist(canonical_name PK, display_name, added_at, notes)`
— `canonical_name` (canonicalized `display_name`) is both match key and PK; no
`user_id` (single-tenant per AGENTS.md — that's a future migration, not pre-paid
now). `repo/watchlist.py` add/list/remove: **canonicalize-on-add**, and re-adding
the same canonical never overwrites the original `display_name`/`added_at` (it
can update `notes`).

**Two-level matching — deliberate.** The `+`/`✓` button on a show card reflects
**exact** canonical membership (is *this* performer on the list), while the
`?watchlist=true` filter uses **token-bag** (surface every show where any
performer matches any watched name). So watching "Vince Lateano" surfaces "Vince
Lateano Trio" shows in `/watchlist`, but that Trio's `+` button stays a `+`
unless you add it specifically. This is correct, if subtle — documented here so
a future reader doesn't "fix" it.

**`?watchlist=true` on `/api/shows`** loads the watchlist, turns each entry into
a token bag, and matches via the shared predicate, stacking (AND) with all other
filters. **Empty watchlist → `[]`** (surfaces the empty state, doesn't flood
with everything) — both API and the `/watchlist` page handle this (the page
shows a CTA to add performers from `/`, not an empty FilterBar).

**Watchlist CRUD (`api/watchlist.py`).** `GET/POST/DELETE /api/watchlist` —
POST canonicalizes the display name (422 if it canonicalizes to nothing), DELETE
by canonical name (404 if absent, 204 on success).

**CORS added.** The add/remove buttons are client components that call the API
cross-origin (frontend `:3000` → backend `:8000`), so `api/__init__.py` gained
`CORSMiddleware`. Local-first + no auth, so it defaults permissive
(`allow_origins=["*"]`); `FOGHORN_CORS_ORIGINS` tightens it when the app is ever
deployed publicly. (Server-component fetches are server-side and never needed
CORS — this is purely for the new client mutations.)

**Frontend.** Filter/show rendering was extracted into a shared `ShowList`
(used by `/` and `/watchlist`) and `lib/api.ts` (shared base/types/`getJSON`).
`AddToWatchlistButton` (client, optimistic +/✓ toggle, reverts on failure) sits
on every performer; the server passes each a server-computed `initiallyOn`.
`/watchlist` reuses `FilterBar` — which (with `PerformerSearch`) was made
route-aware via `usePathname()` so filters stay on `/watchlist` instead of
bouncing to `/`. `WatchlistChips` (client) removes entries and `router.refresh()`es
so the matches + chips + nav count re-render. The nav lives in `layout.tsx`
(async, server-fetches the count) → `Watchlist (N)`; the count updates on
navigation (optimistic card adds catch up on the next nav, per the ticket).

**FE gotcha:** the `/watchlist` split — shows are server-fetched, but the
watchlist is client-mutated — is reconciled with `router.refresh()` (chip
removal) and optimistic local state (card buttons). No client store; the server
is the source of truth, the client just nudges it and re-reads.

Tests (122 green under mypy `strict`): `repo/test_performer_match.py` (token
cases incl. reorder, partial-token-false, accents), `repo/test_repo_watchlist.py`
(add/list/remove, idempotency, display preservation), `api/test_watchlist_endpoint.py`
(CRUD + 404 + canonicalize + 422), `api/test_shows_watchlist_filter.py`
(`?watchlist=true` matches, empty→[], stacks), and 3.3's
`test_shows_performer_filter.py` updated for token behavior. Live-verified the
full UI: empty CTA → add → `/watchlist` shows token-matched shows + chips + nav
count, and the exact-performer `✓` state on `/`.

**Frontend e2e:** the Playwright framework (#30) landed in parallel and is
merged in here; its five specs are kept green against this PR's UI changes (the
new nav + the `+`/`✓` buttons). The watchlist UI doesn't have its *own* specs
yet — a natural follow-up now that the framework exists.

## Frontend e2e test framework — Playwright (May 2026)

Stands up the frontend component-test framework that 3.1 / 3.2 / 3.3 each
flagged as missing (the frontend had only `tsc` / ESLint / `next build` — no
way to assert click-through behavior). Closes #28; resolves the open flag in
those three SHIPPED entries. Five smoke specs prove the framework; subsequent
UI tickets add specs as they touch the surface (the framework is the
deliverable, not coverage).

- **Playwright, not React Testing Library.** The gap that kept getting flagged
  is *interaction* behavior — debounce, chip/toggle states, URL updates on
  click — across a mostly-server-component app with a few client islands
  (`FilterBar`, `PerformerSearch`, `LocationFilter`). Playwright drives a real
  Chromium against a production build, so it covers the SSR + hydration +
  interaction loop RTL-with-jsdom can miss. Chromium only for now (Firefox /
  WebKit deferred).

- **Mock the backend with a real process, not `page.route()`.** The ticket
  suggested `page.route()` interception, but `app/page.tsx` is an async
  *server* component — it fetches `/api/shows` and `/api/venues` from the Next
  server process, which `page.route()` (browser-only) can't intercept. Instead
  a ~30-line Node mock (`frontend/tests/mock-api/server.mjs`) serves fixture
  JSON, and the app is built with `NEXT_PUBLIC_API_BASE_URL` pointed at it (via
  `playwright.config.ts`'s `webServer` env). Same intent as the recommendation
  — isolated, fast, no Python / DB — implemented to match the app's SSR shape.
  Specs assert UI/URL state, not backend filtering (that's the pytest suite's
  job), so the mock returns a static list regardless of query params.

- **Built production app, port 3100.** `webServer` runs `npm run build && npm
  run start` (what the gate already validates; closer to prod than `dev`) on
  3100, so a developer's `npm run dev` on 3000 can keep running alongside.

- **Opt-in target, separate CI job — not in `make gate`.** Playwright is
  slower and needs a browser binary, so it's `make frontend-test` (installs
  Chromium if missing, then runs the specs), plus a `frontend-test` job in
  `gate.yml` parallel to `gate` (both required). `make gate` is unchanged and
  still ~13s: the specs + `playwright.config.ts` are excluded from the app's
  `tsconfig` and `eslint` config, so the fast gate never compiles or lints them
  — Playwright type-checks and runs them itself.

The five specs (`frontend/tests/`): the `Tonight` quick-chip date range, the
debounced performer search → URL, the SF region chip toggle + disabled "(soon)"
regions, and a deep-linked filter URL reflected in the controls. The
watchlist-button spec the ticket mentioned was skipped — Phase 4.1 hadn't
landed on `main` when this shipped (it was in flight in a sibling worktree);
the next UI ticket adds it. How to write a spec, the fixture/mock pattern, and
how to run locally are documented in `frontend/tests/README.md`.

## Late filter now starts at 9pm — no time-of-day gap (May 2026)

Small follow-up to Phase 3.1's time-of-day chips. As shipped, `Late` was
`start_local_time >= 22:00` and `Early` was `< 21:00`, leaving a dead band:
shows starting 9:00–9:59pm matched *neither* chip (≈10% of the calendar). Per
user request, `Late` now starts at **21:00**, so Early (`< 21:00`) and Late
(`>= 21:00`) are exact complements — every show is one or the other.

One-line change to the `repo/shows.py` time-of-day clause (22:00 → 21:00), the
chip relabeled `Late (10pm+)` → `Late (9pm+)`, and the `test_time_of_day_late`
expectation updated (now matches the 21:30 set too) with a new partition test
asserting `early + late == all`. Deviates from #19's ticketed gap, intentionally
— the gap was more confusing than useful in practice.

## Free-text performer search (Phase 3.3, May 2026)

Type a name, find every upcoming show with that performer on the bill. Closes
#20. Almost entirely wiring — the matching was built in Phase 1.2 and just
hadn't been exposed.

**Reused 1.2's matching, didn't reinvent it.** `?performer_query=` on
`GET /api/shows` canonicalizes the input with the *same* `canonicalize()` the
ingest pipeline uses, then sets `ShowFilters.performer_canonical_substring` —
the field, repo clause (`shows.list`), and normalization all shipped in 1.2.
So "Joshua Redman" finds "joshua redman quartet" (substring after canon), the
existing `EXISTS` join matches **headliner or support**, and accent/case fall
out for free (NFKD strip). Phase 4's watchlist will call `shows.list` the same
way — no parallel matching implementation to drift.

**Canonicalize on input.** The query is normalized server-side before matching,
so the client sends raw text and the API does the right thing. A query that's
empty after canonicalization (whitespace or punctuation only) is treated as
**no filter**, not "match nothing" — verified against `""`, `"   "`, and
`"!!!"`.

**Search box (`PerformerSearch.tsx`).** Its own client component — composed into
`FilterBar` with one import + one JSX line — deliberately, to keep the merge
surface with #21 (region filter) to a single "keep both" line, same playbook as
the Phase 2.2 sibling scrapers. It holds the input in local `useState`
(transient typing), debounces a `?performer_query=` push ~300ms after the user
pauses (merging with the other params, not clobbering them), seeds its initial
value from `useSearchParams()`, resyncs when the URL changes externally (Clear
filters / back button), and has a clear `×`. New backend tests live in a
dedicated `tests/api/test_shows_performer_filter.py` (not the shared endpoint
test) for the same anti-conflict reason.

**No new edge cases.** 1.2's matching held up — headliner+support coverage and
accent-insensitivity worked first try; nothing needed fixing. Substring (not
token/FTS) means a reordered query like "redman joshua" won't match "joshua
redman quartet"; that's the documented v0.2.0 tradeoff, FTS5 deferred until it
bites (the watchlist is the likely forcing function).

Tests: 7 in `test_shows_performer_filter.py` (headliner/support match, no-match
empty, empty/whitespace/punctuation = no filter, accent-insensitive, stacks
with venue + date window). 87 green under mypy `strict`. Verified live against
the real DB: "lateano" → 4 Vince Lateano shows, "quartet" → 46, and
`?performer_query=quartet&venues=mr_tipples` correctly stacks.

**Frontend test gap (still open, per 3.1):** no component-test framework, so
`PerformerSearch`'s debounce/clear/resync is verified by build + live exercise,
not an automated test. Same future ticket 3.1 flagged.

## Region and neighborhood filter (Phase 3.2, May 2026)

The second Phase 3 filter dimension, built on 3.1's URL-as-state framework.
Closes #21. Adds `?region=` and `?neighborhood=` to `GET /api/shows` plus a
region chip group and a region-scoped neighborhood dropdown on the frontend.

- **Backend.** `?region=SF` matches the venue's `region`; `?neighborhood=`
  matches the venue's `neighborhood` case-insensitively (`COLLATE NOCASE`,
  exact — neighborhoods are short distinct strings, no fuzzy match needed). Both
  stack as ANDs with the existing date / venue / time-of-day / performer
  filters. `repo.shows.list` already joined `venues` and filtered `region`
  (added speculatively in an earlier phase); this wires `neighborhood` into the
  same query and threads both params through `ShowFilters` and the endpoint.
  Unknown `region` values are ignored (narrowed to the `Region` literal) rather
  than 400, mirroring `time_of_day`.
- **No seed changes needed.** The four-venue seed already carries `region="SF"`
  and correct neighborhoods (Hayes Valley — SFJAZZ + Mr. Tipple's; North Beach —
  Keys; Glen Park — Bird & Beckett). Verified, left as-is.
- **Frontend.** A single `LocationFilter.tsx` (co-locating the region chips and
  the neighborhood select) composes into `FilterBar` with one import + one JSX
  line — deliberately small to keep the merge with the sibling 3.3 search ticket
  trivial. All four regions render; only regions with scraped venues are
  interactive (derived from `/api/venues`), the rest greyed with a "(soon)"
  affordance so the Phase 5 expansion is visible. Region is **single-select**
  (re-click clears). The neighborhood dropdown appears only when a region is
  active and lists that region's neighborhoods; changing/clearing the region
  drops the neighborhood param (it's region-scoped).
- **Region/neighborhood vs. venue checkboxes: independent.** They AND together
  in the backend rather than cascading — a contradictory combination just yields
  the honest empty state. Simpler than auto-toggling checkboxes, and the URL
  stays a faithful record of exactly what was asked.

Mostly framework-complete until Phase 5 brings non-SF venues: today every venue
is SF, so region doesn't discriminate and only neighborhood meaningfully
narrows. The moment an East Bay / Peninsula / South Bay venue ships a scraper,
its region chip activates and the filter just works.

Tests: `tests/api/test_shows_region_filter.py` (its own file, to avoid conflict
with 3.3's tests) covers region SF / East Bay / unknown, neighborhood exact +
case-insensitive, combined, and stacking; `tests/test_repo_shows.py` gains a
neighborhood repo case. Verified live over HTTP (`region=SF` → all,
`East Bay` → `[]`, `neighborhood=Hayes Valley` → Mr. Tipple's,
`region=SF&neighborhood=North Beach` → Keys). Full `make gate` green.

**Worktree note.** Built in an isolated `git worktree` alongside the active 3.3
performer-search work; both touch `FilterBar.tsx`, `api/shows.py`, and
`page.tsx` additively, so the second of #20 / #21 to merge resolves a small
"keep both" conflict.

## Date and venue filters, URL-driven framework (Phase 3.1, May 2026)

The first Phase 3 ticket and the one that sets the pattern: the calendar is now
filterable by date range, venue, and time of day, with all filter state living
in the URL. Closes #19. Builds on v0.1.0; 3.2 (region) and 3.3 (performer
search) plug into this framework.

**URL is the single source of truth.** `app/page.tsx` is an `async` server
component reading `searchParams` (`?from=&to=&venues=&time_of_day=`), building
the `/api/shows` query, fetching, and rendering. Filters are shareable,
bookmarkable, and back-button-correct. The client `FilterBar` derives every
control's state from `useSearchParams()` on each render and writes changes via
`router.push` — **no local filter state**, so URL and UI can't drift. This is
the contract 3.2/3.3 inherit: add a param, read it server-side, add a control
that pushes it.

**Native date inputs, no picker library.** Two `<input type="date">` (with
`min`/`max` cross-bounding) on apply-on-change — selecting a complete date
navigates immediately; native inputs don't fire per-keystroke, so no debounce
needed. Skipped `react-day-picker` et al.: a dependency + bundle weight for a
two-field range the platform already gives us. Revisit if we need range-drag or
multi-month UX.

**`?venues=` (multi-value).** Comma-separated slugs
(`?venues=bird_and_beckett,keys_jazz_bistro`) parsed into
`ShowFilters.venue_slugs`; unknown slugs simply don't match (mixed valid/invalid
filters to the valid). The legacy singular `?venue=` still works. The frontend
omits the param entirely when all (or zero) venue checkboxes are selected,
keeping the default URL clean and dodging the empty-set footgun (zero
checked = all).

**`GET /api/venues`** returns the venue-filter options — `slug`/`name`/
`neighborhood`/`region`. It's filtered to `REGISTERED_SCRAPERS`, so seeded-but-
deferred **SFJAZZ is excluded** (no scraper, never any shows → no dead
checkbox). This couples the venues endpoint to the scraper registry on purpose:
"venues foghorn tracks" is exactly the registry.

**Time-of-day is server-side.** `Early` (`start_local_time` < 21:00) / `Late`
(>= 22:00) are a `?time_of_day=` param → `ShowFilters.time_of_day` → a SQL
clause (lexical compare works since `HH:MM` is zero-padded 24h). Chosen over
client-side post-filtering for consistency with the other filters and so the
URL fully determines the result set (cache-friendly, shareable). Unknown values
are ignored, not 400. Note the deliberate 21:00–21:59 gap between Early and
Late — matches the ticket's definition.

Backend tests (`api/test_shows_endpoint.py` extended, `api/test_venues_endpoint.py`
new) cover `?venues=` (single/multi/unknown/mixed), legacy `?venue=`,
`time_of_day` early/late + ignored-bogus, filter stacking, and that
`/api/venues` lists exactly the three scraped venues. 80 tests green under mypy
`strict`.

**Frontend testing gap (flagged per ticket).** The frontend still has no unit/
component test framework — only `tsc`/`eslint`/`next build`. The
URL→fetch→render path was verified by a live SSR check (filtered URLs render
the right venues/times), but `FilterBar`'s click-through (chip toggles,
checkbox→URL) isn't covered by an automated test. Standing up Playwright/RTL is
its own ticket; didn't introduce one here.

## Daily refresh scheduler and scrape-health endpoint (Phase 2.3, May 2026)

Phase 2's last piece: refreshes now happen on their own (nightly 04:00 PT) and
there's a surface to answer "did last night's run work?" Closes #8. With this,
Phase 2 is complete — open the page in the morning and all three jazz venues
are current.

**`BackgroundScheduler`, not `AsyncIOScheduler`.** The scrape job is synchronous
and blocking (httpx fetches + SQLite writes). `BackgroundScheduler` runs it on a
worker thread, off the FastAPI event loop, so the API stays responsive during a
refresh. Each run opens its **own** SQLite connection inside that thread, which
satisfies sqlite3's `check_same_thread` guard (the app's request connections are
separate and short-lived). An `AsyncIOScheduler` would have run the blocking job
on the event loop — wrong fit.

**One unit of work, two callers.** `scheduler/runner.py:run_scrape(conn,
scrapers=…)` runs every registered scraper through ingest, captures a per-venue
result (`created` / `updated` / `errors`), and records one run. Both the nightly
job *and* `make scrape` call it, so a manual refresh lands a `scrape_runs` row
and shows in `/api/health/scrape` exactly like a scheduled one (the old
bespoke loop in `cli/scrape.py` is gone). A per-venue failure — scraper raises,
or ingest reports errors — is captured in that venue's `errors` and never
propagates: one bad venue can't crash the run or kill the scheduler thread.

**Schema + trim.** Two additive tables: `scrape_runs(id, started_at,
finished_at)` and `scrape_run_venues(scrape_run_id, venue_slug, started_at,
finished_at, created, updated, errors_json)` — errors are stored as a JSON array
in `errors_json`. `repo/scrape_runs.record_run` inserts the run + child rows
then trims to the most recent 30 (`DELETE … ORDER BY id DESC LIMIT -1 OFFSET
30`), deleting child rows first so no orphans accumulate.

**`GET /api/health/scrape`** (`api/health.py`) returns the latest run's
`last_run_at` / `last_run_finished_at` + a per-venue breakdown (`slug`,
timestamps, counts, `errors`). Returns **503 `{"error":
"no_scrape_runs_yet"}`** when no run exists yet — deliberately distinct from "ran
but a venue failed" (200 with that venue's `errors` populated), so an ops poller
can tell "never ran" from "ran badly."

**Test-environment guard.** The scheduler is gated behind
`FOGHORN_DISABLE_SCHEDULER`; `start_scheduler()` returns `None` when it's set.
`tests/conftest.py` sets it at import so no pytest run (including the
`TestClient`-driven API tests, which exercise the lifespan) ever starts a
background thread or fires cron. The app lifespan starts the scheduler on
startup and `shutdown(wait=False)`s it on exit.

Tests (7 new, all green under mypy `strict`): `scheduler/test_runner.py`
(success + raising scraper isolation, persistence/readback, unseeded-venue
error), `scheduler/test_trim.py` (32 inserts trim to 30 keeping newest; explicit
trim leaves no orphan child rows), `api/test_health_scrape.py` (the 503 no-runs
case + latest-run shape with a populated `errors`). Live: `make scrape` recorded
a run across all three venues (59 / 36 / 106), and startup registered the job
with `next_run_time` at the next 04:00 PT.

**Deps note.** `apscheduler` (already pinned since Phase 1.1) ships no `py.typed`,
so it joined the mypy `ignore_missing_imports` override alongside
`recurring_ical_events`.

**Release signal (for the PM thread):** Phase 2.1 (#6), 2.2 (#5, #7), and 2.3
(#8) are all shipped — this is the **v0.1.0 release-cut point** per
`docs/PROJECT_PLAN.md` → "Suggested sequencing." Per `RELEASE_PROCESS.md` the
cut is a PM-thread ritual, so it is *not* done in this PR — surfaced for the PM
thread to run.

## Mr. Tipple's scraper via the Tribe Events API (May 2026)

Second of the three Phase 2.2 sibling scrapers (closes #7). Adds Mr. Tipple's
Recording Studio (39 Fell St, Hayes Valley) behind the registry the 2.1 pilot
established — a third distinct data-source pattern.

**Domain fix.** The #7 ticket and the Phase 1.2 seed both had the site as
`mrtipples.com`, which is **NXDOMAIN**. The live site is `mrtipplessf.com`
(found by probing variants after the seeded domain failed to resolve). The
seed's `website_url` and `calendar_url` for `mr_tipples` are corrected here.
*Same lesson as the SFJAZZ re-pilot: probe before trusting a seeded URL.*

**Data source: The Events Calendar (Tribe) REST API.** Mr. Tipple's is
WordPress running the Tribe "The Events Calendar" plugin, which exposes a clean
JSON API at `/wp-json/tribe/events/v1/events` — richer than the iCal feeds used
elsewhere. Each event carries `title`, `start_date` (venue-local
`YYYY-MM-DD HH:MM:SS`), `timezone`, the event `url`, a `website` (the OpenTable
reservation link), and `cost`. So this scraper fills `ticket_url` (OpenTable)
and `price_text` (`cost`, e.g. "$15 – $30") that Bird & Beckett's calendar
couldn't. `source_url` is the Tribe event permalink.

**Parsing (`scrapers/mr_tipples.py`).** Same fetch/parse split as B&B.
`fetch_events(today, window_days, client=)` pages the REST API across the next
~90 days via `next_rest_url` (and stops if Tribe 404s past the last page); the
`client` is injectable for mock-transport tests. `parse_events` is pure: it
HTML-unescapes Tribe's entity-laden text (`&#8217;`, `&amp;`), keeps times as
naive venue-local (ingest re-applies the tz), and skips `all_day` entries,
`hide_from_listings` events, and **closure markers** the venue posts as calendar
entries ("Closed", "Closed for Private Event"). No recurrence expansion needed
(Tribe returns concrete instances) and no music/non-music filter (it's a pure
jazz room) beyond the closure filter.

Tests (6, in `scrapers/test_mr_tipples.py`): a saved API-response fixture
(`fixtures/mr_tipples_2026_05.json`) drives `parse_events` deterministically
(entity decoding, accents, ticket/price mapping, free-event nulls, and the
all-day / hidden / closed exclusions); two `httpx.MockTransport` tests cover
pagination and the 404-past-last-page stop. Live: `make scrape` ingested 106
shows, idempotent on re-run.

**Gotcha.** Mr. Tipple's runs early + late sets, which appear as same-title
events at different start times — distinct natural keys, so both persist (this
is correct: they're separate performances).

**Concurrency note.** Built alongside #5 (Keys Jazz Bistro), shipped concurrently
by another agent — which moved to an isolated `git worktree` to stop clobbering
the shared tree (#14). Both register a scraper in `scrapers/__init__.py`; this
branch merged `main` and kept all three venues in `REGISTERED_SCRAPERS`.

## Keys Jazz Bistro scraper (Phase 2.2a, May 2026)

Second venue, and the first HTML scraper — Bird & Beckett (the pilot) reads an
`.ics` feed. Closes #5. Follows the scraper-author pattern the
[Phase 2.1 pilot](#phase-21-end-to-end-pilot-via-bird-and-beckett-may-2026)
established — isolated `fetch_html`, a pure `today`-injected `parse_html`, a
registry entry, a fixture test — so this entry records only what's
Keys-specific.

- **Source: `/upcoming-shows/`, not `/event-calendar/`.** Keys runs WordPress
  with the "simple-events" plugin, which renders both. `/event-calendar/` has
  machine-readable `<time datetime>` but shows one month at a time (including
  past days) and duplicates a desktop grid + a mobile list. `/upcoming-shows/`
  is a forward-looking WP Query Loop (`ul.wp-block-post-template`) that starts
  at today, needs no pagination, and lists every upcoming show as a structured
  `<li>`. Cleaner on every axis, so the scraper targets it.
- **Plain `httpx` + `bs4`; no `playwright`.** The show list is in the
  server-rendered HTML. (SFJAZZ — the original 2.1 target — was dropped for a
  Cloudflare challenge; Keys has no such wall.)
- **Dates are free text** (`Saturday, May 23, 2026 @ 10:30pm`) in a bare `<p>`.
  The parser scans `<p>` elements — not the whole `<li>` text — so a show's
  description paragraph or the ticket link's `aria-label` date can't be
  mis-read. A weekday-anchored regex splits date + time; the weekday is not
  trusted (it isn't validated against the date).
- **Per-show provenance**: `source_url` is each show's own `/event/<slug>/`
  page; `ticket_url` is the WooCommerce "Get Tickets" add-to-cart link when
  present, else `None`. The listing carries no doors time or price → both
  `None`.

Verified live: `python -m foghorn.scrapers.keys_jazz_bistro` returns 36 shows
(May 23 → Jun 24); two `make scrape` runs report `created=36` then
`updated=36, errors=0` — idempotent on the natural key. The fixture test drives
`parse_html` from a trimmed real snapshot covering the edge cases (multi-show
day, minutes in the time, curly quotes, a missing ticket link, an out-of-window
event). Full `make gate` green.

**Worktree note.** Built in an isolated `git worktree` because another agent was
shipping Mr. Tipple's (#7) in the main working tree at the same time, and one
shared tree was clobbering both. The sibling 2.2 PRs each touch the registry
(`scrapers/__init__.py`), the seed (`seed_venues.py`), and these docs, so expect
a small conflict when the second of the two lands — resolve by keeping both
venues' entries.

## Phase 2.1 end-to-end pilot via Bird and Beckett (May 2026)

The first venue end-to-end: scrape → ingest → `GET /api/shows` → a rendered
frontend list. Closes #6 (Bird & Beckett scraper, 2.2b). Also lands the Phase
2.1 infrastructure — scraper registry, `make scrape`, the API endpoint, the
frontend page, and the run targets — that the remaining 2.2 siblings build on.

**Re-pilot: SFJAZZ → Bird & Beckett.** #4 picked SFJAZZ as the pilot for being
"largest / most-structured / lowest scraper risk." Dogfooding falsified that:
SFJAZZ sits behind a **Cloudflare managed challenge** that 403s every simple
HTTP client (the polite `foghorn-scraper` UA and a browser UA alike), and the
robots.txt sitemap host 404s. Bypassing Cloudflare is explicitly out of scope,
and a headless browser often doesn't beat a managed challenge anyway. Of the
four jazz venues, Bird & Beckett was the cleanest reachable source, so #4 was
**dropped** and the pilot re-homed here. SFJAZZ can return later as a fresh
ticket if we take on a browser/alternative-source approach. *Lesson for the
remaining venues: probe reachability before assuming a site is scrapable.*

**Data source: a public Google Calendar `.ics`.** Bird & Beckett is WordPress
with no events plugin or custom post type — its event "posts" carry the date in
free-text titles (fragile). But its `/events` page embeds a public Google
Calendar, whose `.ics` export (`.../ical/<id>/public/basic.ics`) is a clean,
current, structured feed (3600+ historical VEVENTs; ~100 upcoming). The scraper
reads that. `venues.calendar_url` for Bird & Beckett points at the human
`/events` page (also the per-show `source_url`); the `.ics` URL is a constant in
the scraper module.

**Parsing (`scrapers/bird_and_beckett.py`).** `fetch_ics()` (httpx, polite UA,
follow redirects) is split from a pure `parse_ics(ics_text, today, window_days)`
so the parser is deterministic and fixture-testable without network. Parsing
uses `icalendar` + `recurring-ical-events`: `recurring_ical_events.of(cal)
.between(today, today+90d)` expands recurring series (the venue runs ~14 active
monthly residencies — Vince Lateano, Scott Foster, etc.) into concrete dated
instances, handling `RECURRENCE-ID` overrides and `EXDATE`. Each timed event
becomes a `ScrapedShow` (SUMMARY → headliner; no support/ticket/price/doors —
the calendar doesn't carry them, and B&B takes phone reservations). All-day
(`VALUE=DATE`) entries are skipped. Expanded instances come back tz-aware (PT or
UTC); we convert to the venue tz and drop tzinfo to get naive local time, which
ingest re-applies the tz to. A **conservative non-music heuristic** drops events
whose title carries strong literary signals (poetry/reading/lecture/…); it errs
toward inclusion per the ticket, so some literary events still leak (e.g. a
small-press release) — refining it is future work.

**Registry + CLI.** `REGISTERED_SCRAPERS` (`scrapers/__init__.py`) maps slug →
`scrape`. `foghorn.cli.scrape` (`make scrape`) seeds venues, runs each scraper
through `ingest_scraped_shows`, prints per-venue `created/updated/errors`, and
exits non-zero on any failure.

**API (`api/shows.py`, `api/__init__.py`).** `GET /api/shows?venue=&from=&to=`
(defaults today..+30d, inclusive on `start_local_date`), ordered by `start_utc`.
Response rows carry venue (slug/name/neighborhood/region), local date/time,
doors, headliner + support as `{display, canonical}`, ticket_url, price_text,
source_url — see `backend/README.md` § API Surface for the shape (the reference
for future scraper authors). The app (`foghorn.api:app`) seeds venues in its
lifespan. Endpoint is sync and opens a SQLite connection per request (cheap, and
keeps each request single-threaded so the default `check_same_thread` guard
holds).

**Frontend (`frontend/app/page.tsx`).** Server component fetching `/api/shows`
(`cache: "no-store"`) from `NEXT_PUBLIC_API_BASE_URL` (default
`http://localhost:8000`), rendering shows grouped by local date with friendly
date/time formatting and a ticket link when present. Renders a clear "Backend
not reachable — `make backend-run`" panel when the fetch fails. Intentionally
bare; Phase 3 dresses it up.

**Deps + config.** Added `uvicorn[standard]==0.47.0` (the run target),
`icalendar==7.1.2`, `recurring-ical-events==3.8.2` to `backend/pyproject.toml`,
plus a mypy `ignore_missing_imports` override for `recurring_ical_events` (no
`py.typed`; icalendar/httpx/bs4 ship types). `db.connect()` now reads
`FOGHORN_DB_PATH` at call time (was import time) so tests/ops can repoint the DB
after import. Makefile gained `scrape`, `backend-run`, `frontend-run`.

Tests (49 total green under mypy `strict`): `scrapers/test_bird_and_beckett.py`
drives `parse_ics` against a curated fixture (`fixtures/bird_and_beckett_sample
.ics`) with a pinned `today` — covering TZID vs UTC times, non-music exclusion,
all-day skip, weekly-recurrence expansion, accents, and windowing.
`test_ingest_e2e_bird_and_beckett.py` runs the fixture through ingest (counts,
tz→UTC round-trip, display-name preservation, idempotent re-ingest).
`api/test_shows_endpoint.py` points the app at a tmp DB via `FOGHORN_DB_PATH`
and drives `GET /api/shows` with `TestClient` (ordering, shape, filters).
Verified live too: `make scrape` ingested 59 shows, and a real
`uvicorn`+`next start` run rendered them grouped by date in the SSR'd HTML.

**Gotchas.** (1) UTC-stored events near midnight render a day earlier in local
time (e.g. a show at 03:00Z shows as the prior evening PT) — correct, just
worth knowing. (2) No `ticket_url`/`price` from this calendar (phone
reservations). (3) The non-music heuristic is imperfect by design.

**Bookkeeping.** Closes #6; #4 (SFJAZZ) was dropped (closed) with the Cloudflare
rationale. The 2.2 siblings #5 (Keys) and #7 (Mr. Tipple's) remain — their
tickets say "depends on #4," now moot: the registry/ingest/API/frontend infra
they need ships here. A PM-thread pass should re-point those references and
reconcile the "Next.js 15" doc mentions (create-next-app installed Next 16).

## Data model and ingest scaffolding (Phase 1.2, May 2026)

The data-model spine every Phase 2.x scraper plugs into: the SQLite schema, the
typed repository layer, the ingest pipeline, and the four-venue seed. No
scraping yet — that's Phase 2. Closes #3.

**Schema** (`repo/schema.py`, bootstrapped via `CREATE TABLE IF NOT EXISTS` on
every `db.connect()`). Four tables: `venues`, `performers`, `shows`,
`show_performers` (the headliner+support join, with `role` and `position`).
No migrations framework — the schema is pre-feature and additive-only for now;
AGENTS.md's "add migrations when evolution gets painful" still holds.

**Natural key, split across two columns.** AGENTS.md specifies the show natural
key as `(venue_id, local_start_datetime, headliner_canonical)`. The schema
stores the local datetime as two columns it already needs for display and
filtering — `start_local_date` (`YYYY-MM-DD`) and `start_local_time` (`HH:MM`)
— so the UNIQUE constraint is `(venue_id, start_local_date, start_local_time,
headliner_canonical)`. Same identity, no redundant combined column. `shows.upsert`
keys on this: re-running a scraper refreshes `scraped_at`/`ticket_url`/`price_text`
(plus `start_utc`/`doors`/`source_url`) and rewrites the bill, never duplicating.
The bill is replaced wholesale (DELETE + re-INSERT of `show_performers`) so a
re-scrape that drops or reorders support acts converges instead of accumulating
stale links.

**Why both `start_utc` and `start_local_*` are stored.** `start_utc` (always
normalized to `+00:00`) is the single sortable instant for `ORDER BY` across
venues and any future multi-tz world; the local date/time are what the venue
published and what the natural key dedups on. Deriving one from the other on
every read would be lossy and tz-fragile, so both are persisted. The ingest
pipeline applies the venue's IANA tz (via stdlib `zoneinfo`) to the scraper's
*naive* local datetime to compute `start_utc` — e.g. 8pm `America/Los_Angeles`
on 2026-06-01 → `2026-06-02T03:00:00+00:00` (PDT, UTC-7).

**Canonicalization** (`ingest.pipeline.canonicalize`). NFKD-decompose, drop
combining marks (`é`→`e`), lowercase, replace every non-alphanumeric char with a
space, collapse whitespace. Punctuation becomes a *separator*, not deleted, so
`"Earth, Wind & Fire"` → `"earth wind fire"` (not `"earthwind fire"`). Uses
`str.isalnum()` so it's unicode-aware rather than ASCII-only. Performers are
stored with both `display_name` (verbatim, never overwritten on conflict) and
`canonical_name` (unique) per the AGENTS.md display-vs-search split; the
watchlist (Phase 4) and free-text search (Phase 3.3) match on canonical.

**Repo layer is conn-injected, returns Pydantic.** Every repo function takes a
`sqlite3.Connection` as its first arg (no global/singleton connection), which
makes tests trivial (a per-test tmp-file DB fixture in `conftest.py`) and keeps
the Postgres-swap seam clean. `repo/db.py` centralizes connection setup
(`Row` factory, `PRAGMA foreign_keys = ON`, schema bootstrap) and the default
DB path (`FOGHORN_DB_PATH` env override). `shows.list` shadows the builtin to
read as `shows.list(conn, filters)`; annotations use `builtins.list` to dodge
the shadow.

**Models** (`foghorn/models.py`). All cross-layer shapes live in one module so
repo/ingest/scrapers/api agree without importing each other: `Venue`,
`Performer`, `ShowPerformer`, `Show`, `ScrapedShow` (frozen — the scraper
contract), `ShowFilters`, `IngestResult`. `Region`/`Role` are `Literal`s so
seeds and ingest are validated at construction rather than writing typos.
`IngestResult.errors` is a `list[str]` (one message per failed show) rather than
a bare count, so Phase 2.1's `make scrape` and 2.3's scrape-health endpoint can
surface *what* failed.

**Seed.** `repo/seed_venues.py` upserts the four jazz venues; idempotent via
upsert-on-slug (so the "seed only if empty" guard is unnecessary — re-running
converges either way). Each `calendar_url` is a `TBD` placeholder set by the
per-venue Phase 2.x scraper ticket. The "seed on app startup" hook lands with
the FastAPI app in Phase 2.1; for now `seed()` is callable directly /
`python -m foghorn.repo.seed_venues`.

Tests (32, all green under mypy `strict`): `test_canonicalize.py` (accents,
punctuation-as-separator, idempotence), `test_repo_venues.py` and
`test_repo_shows.py` (upsert idempotency, bill replacement, every `list` filter
combination + `start_utc` ordering), `test_seed_venues.py` (four venues,
idempotent), and `test_ingest_pipeline.py` (the new/duplicate/same-headliner-
different-time count matrix, tz→UTC math, display-name preservation, performer
reuse across shows, and per-show error isolation via a bad-tz venue). A shared
`conn`/`venue` fixture pair in `tests/conftest.py` gives each test a fresh DB.

**API-surface note for scraper authors:** filling in `backend/README.md` §
Data Model documented the schema, the natural-key dedup, and the
`ingest_scraped_shows(conn, venue, scraped) -> IngestResult` entry point a
Phase 2.x scraper hands its output to. § Storage gained the connection-handling
and repo-primitive details.

## Repo skeleton and CI gate (Phase 1.1, May 2026)

First code to land in foghorn — the two-package monorepo skeleton, the
lint/type/test gate, and CI. No application logic; this is the structure that
Phase 1.2 (data model) and Phase 2 (scrapers) fill in. Closes #2.

**Backend** (`backend/`). Python 3.11+, `src/` layout with `foghorn` as the
import root and empty-but-present `scrapers/`, `ingest/`, `repo/`, `api/`
subpackages. `pyproject.toml` uses hatchling and pins runtime deps (fastapi,
httpx, beautifulsoup4, apscheduler, pydantic v2) and dev deps (pytest, ruff,
mypy) to the exact versions resolved at scaffold time. APScheduler is held on
the 3.x line — 4.x is a different API. mypy runs in `strict` mode; one smoke
test (`tests/test_smoke.py`) imports all four subpackages so the gate has
something real to run.

**Storage decision: stdlib `sqlite3`, not SQLAlchemy.** The ticket left this to
the implementer. foghorn is single-user / local-first through Phase 5, the
query surface is small (filtered `SELECT`s plus upsert-on-natural-key for
idempotent scraper re-runs), and a hand-written SQL layer in `repo/` keeps the
dependency surface minimal and the DB trivially inspectable with any `sqlite3`
client. The repo layer (Phase 1.2) will wrap `sqlite3` behind typed functions
returning Pydantic models, so callers never touch raw rows or `Any`. If hosting
later forces Postgres, `repo/` is the single seam to swap. Documented in
`backend/README.md` § Storage.

**Frontend** (`frontend/`). `create-next-app` with TypeScript + Tailwind +
App Router (no `src/` dir, `@/*` import alias). The demo page is stripped to a
"foghorn — coming soon" placeholder and the layout metadata set to foghorn.
Added a `typecheck` script (`tsc --noEmit`) because the gate calls
`npm run typecheck` and create-next-app doesn't generate one.

**Gate + CI.** Root `Makefile`: `make gate` runs the backend half
(`ruff check . && mypy src && pytest`) then the frontend half
(`npm run typecheck && npm run lint && npm run build`), stopping at the first
non-zero exit; `make backend-gate` / `make frontend-gate` run the halves
individually; `make install` installs both. The backend targets assume the
project's tools are on PATH (an activated venv locally, or the CI runner's
setup-python environment after `make install`). `.github/workflows/gate.yml`
runs `make install && make gate` on ubuntu-latest with Python 3.11 + Node 20,
caching pip and npm. Root `.gitignore` covers Python, Node, and the
`*.db`/`*.sqlite*` files Phase 1.2 will start writing.

**Notes / gotchas (some for the PM thread):**

- **`create-next-app@latest` now installs Next.js 16 (16.2.6) + React
  19.2.4**, not Next 15. AGENTS.md, README, and PROJECT_PLAN still say
  "Next.js 15"; the ticket said use `@latest`, so 16 is what shipped. Those doc
  references should be reconciled (PM-thread territory). Next 16 uses Turbopack
  for `next build` by default and carries breaking changes vs. 15 — future
  frontend work should consult the bundled docs in `node_modules/next/dist/docs`.
- **Removed the `frontend/AGENTS.md` + `frontend/CLAUDE.md` stubs** that
  create-next-app now generates. The repo's model is one authoritative root
  `AGENTS.md`; a competing nested `AGENTS.md` is a footgun about which doc is
  canonical. The one useful nugget from the stub is preserved above (Next 16
  breaking changes / bundled docs).
- Filled the leftover `{{PROJECT_NAME}}` placeholder in this file's header
  while adding this entry. `docs/CHANGELOG.md` still carries the same
  placeholder, left for the PM thread / first release cut.
- mypy `strict` is on with no per-module overrides yet. A forward-looking
  `ignore_missing_imports` override for bs4/apscheduler produced an "unused
  section" note (nothing imports them yet), so it was omitted; Phase 2.x adds
  it when those libraries are actually imported.

Acceptance verified locally: `make install` and `make gate` both run clean on
the skeleton (backend ruff/mypy/pytest green; frontend typecheck/lint/build
green), and the four subpackages import cleanly. CI on the PR is the remaining
check.
