"use client";

// URL-driven filter controls. The URL search params are the single source of
// truth: every control derives its state from `useSearchParams()` on each
// render and writes changes back via `router.push`. No local filter state — so
// the URL, the UI, the back button, and shared links stay in lockstep. Phase
// 3.2 (region) and 3.3 (performer search) plug into this same pattern.

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import GenreFilter from "./GenreFilter";
import LocationFilter from "./LocationFilter";
import OriginFilter from "./OriginFilter";
import PerformerSearch from "./PerformerSearch";
import TypeFilter from "./TypeFilter";
import type { VenueOption } from "./lib/api";
import { addDaysISO, thisWeekend, todayISO } from "./lib/dates";
import { chipClass, inputClass } from "./lib/ui";

export default function FilterBar({
  venues,
  showOriginFilter = false,
  showDateControls = true,
}: {
  venues: VenueOption[];
  // Origin tags cover only part of the catalog; the server component sets
  // this when tagged performers exist in the result (or ?origin= is active).
  showOriginFilter?: boolean;
  // The day/week/month views derive their own window from ?anchor=, so the
  // list's quick date chips + from/to inputs hide there.
  showDateControls?: boolean;
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

  // The date inputs hold local drafts and commit on blur/Enter rather than
  // navigating on every change event. A native date input fires `change` for
  // each segment as you type (month, day, every year digit), so committing
  // per-change navigates mid-edit — the refetch re-renders the controlled
  // input and snaps it back before the date is finished. Drafts re-sync when
  // the URL changes from outside (quick chips, back button, shared links).
  const [draftFrom, setDraftFrom] = useState(from);
  const [draftTo, setDraftTo] = useState(to);
  useEffect(() => setDraftFrom(from), [from]);
  useEffect(() => setDraftTo(to), [to]);

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
    navigate({ from: draftFrom, to: draftFrom > to ? draftFrom : to });
  }

  function commitTo(): void {
    if (!isSaneDate(draftTo)) {
      setDraftTo(to);
      return;
    }
    navigate({ from: draftTo < from ? draftTo : from, to: draftTo });
  }

  function blurOnEnter(e: React.KeyboardEvent<HTMLInputElement>): void {
    if (e.key === "Enter") e.currentTarget.blur(); // blur commits
  }

  // Mobile: everything below the search + quick chips collapses behind a
  // "More filters" toggle so shows aren't pushed two screens down. Desktop
  // (sm+) always shows the full panel; this state only matters under sm.
  const [moreOpen, setMoreOpen] = useState(false);
  const advancedActive =
    ["region", "neighborhood", "genre", "origin", "type", "venues"].filter(
      (k) => params.get(k),
    ).length + (params.get("from") || params.get("to") ? 1 : 0);

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

      {/* 26 venues is too many to show unfolded — collapse behind a summary
          that still reports the constraint. Auto-opens when a shared URL
          arrives with a venue filter so the state is never hidden. */}
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
        <div className="mt-2 grid grid-cols-1 gap-x-4 gap-y-1.5 sm:grid-cols-2 md:grid-cols-3">
          {venues.map((venue) => (
            <label
              key={venue.slug}
              className="flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300"
            >
              <input
                type="checkbox"
                checked={venueChecked(venue.slug)}
                onChange={() => toggleVenue(venue.slug)}
                className="h-4 w-4 shrink-0"
              />
              <span className="truncate" title={venue.name}>
                {venue.name}
              </span>
            </label>
          ))}
        </div>
        {selected !== null && (
          <button
            type="button"
            onClick={() => navigate({ venues: null })}
            className="mt-2 text-xs text-teal-700 underline decoration-teal-700/40 underline-offset-2 hover:decoration-teal-700 dark:text-teal-400 dark:decoration-teal-400/40"
          >
            Show all venues
          </button>
        )}
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
