// Show list (/). A server component whose filter state lives entirely in the
// URL search params: it parses them, fetches the filtered shows + venues +
// watchlist, and renders the URL-driven <FilterBar> over a <ShowList> (shared
// with /watchlist). The watchlist set drives each performer's add/remove "+".

import { Suspense } from "react";

import FilterBar from "./FilterBar";
import ShowList from "./ShowList";
import {
  getJSON,
  type ShowView,
  type VenueOption,
  type WatchlistEntry,
} from "./lib/api";
import { addDaysISO, todayISO } from "./lib/dates";

const DEFAULT_WINDOW_DAYS = 14;

function first(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

export default async function Home({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const sp = await searchParams;
  const today = todayISO();
  const from = first(sp.from) ?? today;
  const to = first(sp.to) ?? addDaysISO(today, DEFAULT_WINDOW_DAYS);
  const venues = first(sp.venues);
  const timeOfDay = first(sp.time_of_day);
  const performerQuery = first(sp.performer_query);
  const region = first(sp.region);
  const neighborhood = first(sp.neighborhood);
  const genre = first(sp.genre);

  const query = new URLSearchParams({ from, to });
  if (venues) query.set("venues", venues);
  if (timeOfDay === "early" || timeOfDay === "late") {
    query.set("time_of_day", timeOfDay);
  }
  if (performerQuery) query.set("performer_query", performerQuery);
  if (region) query.set("region", region);
  if (neighborhood) query.set("neighborhood", neighborhood);
  if (genre) query.set("genre", genre);

  const [shows, allVenues, watchlist] = await Promise.all([
    getJSON<ShowView[]>(`/api/shows?${query.toString()}`),
    getJSON<VenueOption[]>(`/api/venues`),
    getJSON<WatchlistEntry[]>(`/api/watchlist`),
  ]);
  const watchlistCanon = new Set(
    (watchlist ?? []).map((entry) => entry.canonical_name),
  );

  return (
    <main className="mx-auto w-full max-w-2xl flex-1 px-6 py-10">
      <header className="mb-6">
        <h1 className="text-3xl font-semibold tracking-tight">foghorn</h1>
        <p className="text-sm text-zinc-500 dark:text-zinc-400">
          Upcoming Bay Area jazz &amp; music shows
        </p>
      </header>

      {shows === null ? (
        <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200">
          Backend not reachable. Start it with{" "}
          <code className="font-mono">make backend-run</code>, then refresh.
        </div>
      ) : (
        <>
          <Suspense fallback={null}>
            <FilterBar venues={allVenues ?? []} />
          </Suspense>

          {shows.length === 0 ? (
            <p className="text-zinc-500 dark:text-zinc-400">
              {performerQuery
                ? `No shows matching “${performerQuery}” in this window. Try widening the date range or clearing other filters.`
                : "No shows match these filters. Try widening the date range or clearing filters."}
            </p>
          ) : (
            <ShowList shows={shows} watchlistCanon={watchlistCanon} />
          )}
        </>
      )}
    </main>
  );
}
