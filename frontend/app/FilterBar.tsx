"use client";

// URL-driven filter controls. The URL search params are the single source of
// truth: every control derives its state from `useSearchParams()` on each
// render and writes changes back via `router.push`. No local filter state — so
// the URL, the UI, the back button, and shared links stay in lockstep. Phase
// 3.2 (region) and 3.3 (performer search) plug into this same pattern.

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import GenreFilter from "./GenreFilter";
import LocationFilter from "./LocationFilter";
import OriginFilter from "./OriginFilter";
import PerformerSearch from "./PerformerSearch";
import TypeFilter from "./TypeFilter";
import VenuePicker from "./VenuePicker";
import type { VenueOption } from "./lib/api";
import { addDaysISO, thisWeekend, todayISO } from "./lib/dates";
import { facetValues } from "./lib/facets";
import { chipClass, inputClass } from "./lib/ui";

export default function FilterBar({
  venues,
  watchedVenueSlugs,
  signedIn = true,
  watchlistCount = 0,
  showOriginFilter = false,
  showDateControls = true,
  showMyVenuesChip = false,
}: {
  venues: VenueOption[];
  // Followed venues (venue watchlist): sorts the picker and drives its ★s.
  watchedVenueSlugs?: Set<string>;
  // Anonymous visitors don't get the personal chips (watchlist / my venues)
  // or the picker's pin affordances — those require an account.
  signedIn?: boolean;
  // Performer-watchlist size, shown on the Watchlist chip. The chip renders
  // even at 0 — it's the feature's entry point now that /watchlist is gone.
  watchlistCount?: number;
  // Origin tags cover only part of the catalog; the server component sets
  // this when tagged performers exist in the result (or ?origin= is active).
  showOriginFilter?: boolean;
  // The day/week/month views derive their own window from ?anchor=, so the
  // list's quick date chips + from/to inputs hide there.
  showDateControls?: boolean;
  // "My venues" quick chip (?venue_watchlist=true); enabled when the venue
  // watchlist is non-empty.
  showMyVenuesChip?: boolean;
}) {
  const router = useRouter();
  const params = useSearchParams();
  const pathname = usePathname();

  const today = todayISO();
  const from = params.get("from") ?? today;
  const to = params.get("to") ?? addDaysISO(today, 14);
  // ?to=all lifts the upper bound (every ingested show from `from` onward).
  // The native date input can't hold "all", so it renders empty in that mode.
  const allUpcoming = to === "all";
  const toInput = allUpcoming ? "" : to;
  const time = params.get("time_of_day");
  const watchlistOn = params.get("watchlist") === "true";
  const myVenues = params.get("venue_watchlist") === "true";
  const venuesParam = params.get("venues");
  const selected = venuesParam
    ? new Set(venuesParam.split(",").filter(Boolean))
    : null; // null = no constraint (all venues)

  function navigate(updates: Record<string, string | null>): void {
    const next = new URLSearchParams(params.toString());
    for (const [key, value] of Object.entries(updates)) {
      if (value === null || value === "") next.delete(key);
      else next.set(key, value);
    }
    const query = next.toString();
    router.push(query ? `${pathname}?${query}` : pathname);
  }

  const weekend = thisWeekend();
  const isTonight = from === today && to === today;
  const isWeekend = from === weekend.from && to === weekend.to;
  const isNext7 = from === today && to === addDaysISO(today, 7);

  // The date inputs hold local drafts and commit on blur/Enter rather than
  // navigating on every change event. A native date input fires `change` for
  // each segment as you type (month, day, every year digit), so committing
  // per-change navigates mid-edit — the refetch re-renders the controlled
  // input and snaps it back before the date is finished. Drafts re-sync when
  // the URL changes from outside (quick chips, back button, shared links)
  // via render-time reconciliation (the React "adjusting state during
  // render" pattern — no effect, no cascading-render lint).
  const [draftFrom, setDraftFrom] = useState(from);
  const [draftTo, setDraftTo] = useState(toInput);
  const [prevRange, setPrevRange] = useState({ from, to: toInput });
  if (prevRange.from !== from || prevRange.to !== toInput) {
    setPrevRange({ from, to: toInput });
    setDraftFrom(from);
    setDraftTo(toInput);
  }

  // Complete, plausible date. Typing a year digit-by-digit passes through
  // "0002-…"/"0020-…" as technically valid dates; don't commit those.
  function isSaneDate(value: string): boolean {
    return /^\d{4}-\d{2}-\d{2}$/.test(value) && value >= "2000-01-01";
  }

  // Committing one end drags the other along instead of blocking (min/max
  // constraints made it impossible to move a range forward: "from" couldn't
  // pass the current "to").
  function commitFrom(): void {
    if (!isSaneDate(draftFrom)) {
      setDraftFrom(from);
      return;
    }
    // In all-upcoming mode the upper bound stays lifted; only `from` moves.
    navigate({
      from: draftFrom,
      to: allUpcoming ? "all" : draftFrom > to ? draftFrom : to,
    });
  }

  function commitTo(): void {
    if (!isSaneDate(draftTo)) {
      setDraftTo(toInput);
      return;
    }
    // Committing a concrete end date exits all-upcoming mode naturally.
    navigate({ from: draftTo < from ? draftTo : from, to: draftTo });
  }

  function blurOnEnter(e: React.KeyboardEvent<HTMLInputElement>): void {
    if (e.key === "Enter") e.currentTarget.blur(); // blur commits
  }

  // Mobile: everything below the search + quick chips collapses behind a
  // "More filters" toggle so shows aren't pushed two screens down. Desktop
  // (sm+) always shows the full panel; this state only matters under sm.
  const [moreOpen, setMoreOpen] = useState(false);
  // How many selections are hidden behind the toggle. Two things made the old
  // count read as arbitrary:
  //
  //  - it counted *params*, not selections, so picking three genres said "1";
  //  - it counted `venue_watchlist`, whose "My venues ★" chip is in the
  //    always-visible row above — so it reported something you could already
  //    see, and reported it as hidden.
  //
  // Now it counts individual selections, and only for controls that actually
  // live inside the collapsed panel. A date range stays one (it's one range,
  // and its inputs are in here).
  const advancedActive =
    ["region", "neighborhood", "genre", "origin", "type", "venues"].reduce(
      (total, key) => total + facetValues(params.get(key)).length,
      0,
    ) +
    (params.get("long_tail") ? 1 : 0) +
    (params.get("from") || params.get("to") ? 1 : 0);

  function setRange(active: boolean, range: { from: string; to: string }): void {
    navigate(active ? { from: null, to: null } : range);
  }



  return (
    <section className="mb-8 flex flex-col gap-4 rounded-xl border border-zinc-200 bg-zinc-50/60 p-4 dark:border-zinc-800 dark:bg-zinc-900/40">
      <PerformerSearch />
      <div className="flex flex-wrap items-center gap-2">
        {showDateControls && (
          <>
            <button
              type="button"
              className={chipClass(isTonight)}
              onClick={() => setRange(isTonight, { from: today, to: today })}
            >
              Tonight
            </button>
            <button
              type="button"
              className={chipClass(isWeekend)}
              onClick={() => setRange(isWeekend, weekend)}
            >
              This weekend
            </button>
            <button
              type="button"
              className={chipClass(isNext7)}
              onClick={() =>
                setRange(isNext7, { from: today, to: addDaysISO(today, 7) })
              }
            >
              Next 7 days
            </button>
            <button
              type="button"
              className={chipClass(allUpcoming)}
              title="Every ingested show from today onward — no end date"
              onClick={() =>
                navigate(
                  allUpcoming ? { to: null } : { from: null, to: "all" },
                )
              }
            >
              All upcoming
            </button>
            <span
              className="mx-1 hidden h-4 w-px bg-zinc-300 sm:inline-block dark:bg-zinc-700"
              aria-hidden="true"
            />
          </>
        )}
        <button
          type="button"
          className={chipClass(time === "early")}
          onClick={() =>
            navigate({ time_of_day: time === "early" ? null : "early" })
          }
        >
          Early (before 9pm)
        </button>
        <button
          type="button"
          className={chipClass(time === "late")}
          onClick={() =>
            navigate({ time_of_day: time === "late" ? null : "late" })
          }
        >
          Late (9pm+)
        </button>
        {/* The "following" cluster: performer watchlist + followed venues.
            These were standalone pages; now they're filters on the one
            calendar, so every view (list/day/week/month) works with them. */}
        <span
          className="mx-1 hidden h-4 w-px bg-zinc-300 sm:inline-block dark:bg-zinc-700"
          aria-hidden="true"
        />
        {signedIn && (
          <button
            type="button"
            className={chipClass(watchlistOn)}
            title="Only shows where a performer you follow is on the bill"
            onClick={() => navigate({ watchlist: watchlistOn ? null : "true" })}
          >
            Watchlist{watchlistCount > 0 ? ` (${watchlistCount})` : ""}
          </button>
        )}
        {signedIn && showMyVenuesChip && (
          <button
            type="button"
            className={chipClass(myVenues)}
            title="Only shows at venues you follow (★)"
            onClick={() =>
              navigate({ venue_watchlist: myVenues ? null : "true" })
            }
          >
            My venues ★
          </button>
        )}
        {/* The community-listed switch used to sit here as a "Long tail" chip.
            It moved into VenuePicker: every chip in this row narrows the
            results, that one widened them, and it decides which venues exist
            rather than which shows match. Same `long_tail` URL param. */}
      </div>

      <button
        type="button"
        className="self-start text-sm text-teal-700 underline decoration-teal-700/40 underline-offset-2 hover:decoration-teal-700 sm:hidden dark:text-teal-400 dark:decoration-teal-400/40"
        aria-expanded={moreOpen}
        onClick={() => setMoreOpen((v) => !v)}
      >
        {moreOpen ? "Fewer filters" : "More filters"}
        {!moreOpen && advancedActive > 0 ? ` (${advancedActive} active)` : ""}
      </button>

      <div
        className={`${moreOpen ? "flex" : "hidden"} flex-col gap-4 sm:flex`}
      >
      {showDateControls && (
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-xs text-zinc-500 dark:text-zinc-400">
          From
          <input
            type="date"
            value={draftFrom}
            onChange={(e) => setDraftFrom(e.target.value)}
            onBlur={commitFrom}
            onKeyDown={blurOnEnter}
            className={inputClass}
          />
        </label>
        <label className="flex flex-col gap-1 text-xs text-zinc-500 dark:text-zinc-400">
          To
          <input
            type="date"
            value={draftTo}
            onChange={(e) => setDraftTo(e.target.value)}
            onBlur={commitTo}
            onKeyDown={blurOnEnter}
            className={inputClass}
          />
        </label>
      </div>
      )}

      <LocationFilter venues={venues} />

      <GenreFilter venues={venues} />

      <TypeFilter />

      {showOriginFilter && <OriginFilter />}

      {/* Venue picker (first-class venue UX): search, region groups,
          followed-first with ★s, honest selected-chip state. Auto-opens when
          a shared URL arrives with a venue filter. */}
      <details open={selected !== null} className="group">
        <summary className="cursor-pointer select-none text-xs text-zinc-500 marker:text-zinc-400 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200">
          Venues{" "}
          <span className="text-zinc-400 dark:text-zinc-500">
            ·{" "}
            {selected === null
              ? `all ${venues.length}`
              : `${selected.size} of ${venues.length}`}
          </span>
        </summary>
        <div className="mt-2">
          <VenuePicker
            venues={venues}
            watchedVenueSlugs={watchedVenueSlugs ?? new Set()}
            showPins={signedIn}
          />
        </div>
      </details>
      </div>

      {params.toString().length > 0 && (
        <div>
          <Link
            href={pathname}
            className="text-sm text-teal-700 underline decoration-teal-700/40 underline-offset-2 hover:decoration-teal-700 dark:text-teal-400 dark:decoration-teal-400/40"
          >
            Clear filters
          </Link>
        </div>
      )}
    </section>
  );
}
