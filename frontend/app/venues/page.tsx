// /venues — the venue watchlist (Phase 9): upcoming shows at followed venues.
// Same URL-driven filter framework as / and /watchlist, with
// ?venue_watchlist=true added to the query. Every venue row here carries a
// ★ toggle; unfollowed venues can be followed from the full list below.

import { Suspense } from "react";

import FilterBar from "../FilterBar";
import PinVenueButton from "../PinVenueButton";
import VenuePicker from "../VenuePicker";
import ShowList from "../ShowList";
import {
  getJSON,
  type ShowView,
  type VenueOption,
  type WatchedVenueEntry,
  type WatchlistEntry,
} from "../lib/api";
import { addDaysISO, todayISO } from "../lib/dates";

const DEFAULT_WINDOW_DAYS = 14;

function first(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

export default async function VenuesPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const sp = await searchParams;
  const today = todayISO();
  const from = first(sp.from) ?? today;
  const to = first(sp.to) ?? addDaysISO(today, DEFAULT_WINDOW_DAYS);
  const timeOfDay = first(sp.time_of_day);
  const performerQuery = first(sp.performer_query);
  const genre = first(sp.genre);
  const type = first(sp.type);
  const longTail = first(sp.long_tail) === "true";

  const query = new URLSearchParams({ from, to, venue_watchlist: "true" });
  if (timeOfDay === "early" || timeOfDay === "late") {
    query.set("time_of_day", timeOfDay);
  }
  if (performerQuery) query.set("performer_query", performerQuery);
  if (genre) query.set("genre", genre);
  if (type === "show" || type === "jam") query.set("type", type);
  if (longTail) query.set("long_tail", "true");

  const [shows, allVenues, watched, watchlist] = await Promise.all([
    getJSON<ShowView[]>(`/api/shows?${query.toString()}`),
    getJSON<VenueOption[]>(`/api/venues`),
    getJSON<WatchedVenueEntry[]>(`/api/venues/watchlist`),
    getJSON<WatchlistEntry[]>(`/api/watchlist`),
  ]);
  const watchedSlugs = new Set((watched ?? []).map((e) => e.venue_slug));
  const watchlistCanon = new Set(
    (watchlist ?? []).map((entry) => entry.canonical_name),
  );

  return (
    <main className="mx-auto w-full max-w-2xl flex-1 px-6 py-10">
      <header className="mb-6">
        <h1 className="text-3xl font-semibold tracking-tight">Venues</h1>
        <p className="text-sm text-zinc-500 dark:text-zinc-400">
          Upcoming shows at venues you follow
        </p>
      </header>

      {shows === null || watched === null ? (
        <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200">
          Backend not reachable. Start it with{" "}
          <code className="font-mono">make backend-run</code>, then refresh.
        </div>
      ) : (
        <>
          {watched.length > 0 && (
            <div className="mb-4 flex flex-wrap gap-x-4 gap-y-1 text-sm text-zinc-700 dark:text-zinc-300">
              {watched.map((e) => (
                <span key={e.venue_slug}>
                  {e.name}
                  <PinVenueButton venueSlug={e.venue_slug} initiallyOn />
                </span>
              ))}
            </div>
          )}

          <details className="mb-6" open={watched.length === 0}>
            <summary className="cursor-pointer select-none text-xs text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200">
              All venues{" "}
              <span className="text-zinc-400 dark:text-zinc-500">
                · follow more
              </span>
            </summary>
            <div className="mt-2">
              <VenuePicker
                venues={allVenues ?? []}
                watchedVenueSlugs={watchedSlugs}
                mode="follow"
              />
            </div>
          </details>

          {watched.length === 0 ? (
            <p className="mb-6 text-zinc-500 dark:text-zinc-400">
              You aren&apos;t following any venues yet — star some below.
            </p>
          ) : (
            <>
              <Suspense fallback={null}>
                <FilterBar
                  venues={allVenues ?? []}
                  watchedVenueSlugs={watchedSlugs}
                />
              </Suspense>
              {shows.length === 0 ? (
                <p className="text-zinc-500 dark:text-zinc-400">
                  No shows at followed venues in this window.
                </p>
              ) : (
                <ShowList
                  shows={shows}
                  watchlistCanon={watchlistCanon}
                  watchedVenueSlugs={watchedSlugs}
                />
              )}
            </>
          )}

        </>
      )}
    </main>
  );
}
