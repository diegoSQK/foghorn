"use client";

// URL-driven filter controls. The URL search params are the single source of
// truth: every control derives its state from `useSearchParams()` on each
// render and writes changes back via `router.push`. No local filter state — so
// the URL, the UI, the back button, and shared links stay in lockstep. Phase
// 3.2 (region) and 3.3 (performer search) plug into this same pattern.

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import GenreFilter from "./GenreFilter";
import LocationFilter from "./LocationFilter";
import OriginFilter from "./OriginFilter";
import PerformerSearch from "./PerformerSearch";
import type { VenueOption } from "./lib/api";
import { addDaysISO, thisWeekend, todayISO } from "./lib/dates";

function chipClass(active: boolean): string {
  return `rounded-full border px-3 py-1 text-sm transition-colors ${
    active
      ? "border-zinc-900 bg-zinc-900 text-white dark:border-zinc-100 dark:bg-zinc-100 dark:text-zinc-900"
      : "border-zinc-300 text-zinc-700 hover:border-zinc-500 dark:border-zinc-700 dark:text-zinc-300"
  }`;
}

const inputClass =
  "rounded-md border border-zinc-300 bg-transparent px-2 py-1 text-sm text-zinc-900 dark:border-zinc-700 dark:text-zinc-100";

export default function FilterBar({
  venues,
  showOriginFilter = false,
}: {
  venues: VenueOption[];
  // Origin tags cover only part of the catalog; the server component sets
  // this when tagged performers exist in the result (or ?origin= is active).
  showOriginFilter?: boolean;
}) {
  const router = useRouter();
  const params = useSearchParams();
  const pathname = usePathname(); // keep filters on the current route (/ or /watchlist)

  const today = todayISO();
  const from = params.get("from") ?? today;
  const to = params.get("to") ?? addDaysISO(today, 14);
  const time = params.get("time_of_day");
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

  function setRange(active: boolean, range: { from: string; to: string }): void {
    navigate(active ? { from: null, to: null } : range);
  }

  function venueChecked(slug: string): boolean {
    return selected === null || selected.has(slug);
  }

  function toggleVenue(slug: string): void {
    const base = selected ?? new Set(venues.map((v) => v.slug));
    const next = new Set(base);
    if (next.has(slug)) next.delete(slug);
    else next.add(slug);
    // All or none selected collapses to the clean "all venues" default.
    const all = next.size === 0 || next.size === venues.length;
    navigate({ venues: all ? null : [...next].join(",") });
  }

  return (
    <section className="mb-8 flex flex-col gap-4 rounded-lg border border-zinc-200 p-4 dark:border-zinc-800">
      <PerformerSearch />
      <div className="flex flex-wrap items-center gap-2">
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
        <span
          className="mx-1 hidden h-4 w-px bg-zinc-300 sm:inline-block dark:bg-zinc-700"
          aria-hidden="true"
        />
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
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-xs text-zinc-500 dark:text-zinc-400">
          From
          <input
            type="date"
            value={from}
            max={to}
            onChange={(e) => navigate({ from: e.target.value || null })}
            className={inputClass}
          />
        </label>
        <label className="flex flex-col gap-1 text-xs text-zinc-500 dark:text-zinc-400">
          To
          <input
            type="date"
            value={to}
            min={from}
            onChange={(e) => navigate({ to: e.target.value || null })}
            className={inputClass}
          />
        </label>
      </div>

      <LocationFilter venues={venues} />

      <GenreFilter venues={venues} />

      {showOriginFilter && <OriginFilter />}

      <fieldset className="flex flex-wrap gap-x-4 gap-y-2">
        <legend className="mb-1 text-xs text-zinc-500 dark:text-zinc-400">
          Venues
        </legend>
        {venues.map((venue) => (
          <label
            key={venue.slug}
            className="flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300"
          >
            <input
              type="checkbox"
              checked={venueChecked(venue.slug)}
              onChange={() => toggleVenue(venue.slug)}
              className="h-4 w-4"
            />
            {venue.name}
          </label>
        ))}
      </fieldset>

      {params.toString().length > 0 && (
        <div>
          <Link
            href={pathname}
            className="text-sm text-zinc-500 underline hover:no-underline dark:text-zinc-400"
          >
            Clear filters
          </Link>
        </div>
      )}
    </section>
  );
}
