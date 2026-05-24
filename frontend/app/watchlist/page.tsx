// /watchlist — shows where any performer matches a watched name. Same
// URL-driven filter framework as /, with ?watchlist=true added to the query and
// a removable "Your watchlist" chip row on top. Empty watchlist shows a CTA.

import Link from "next/link";
import { Suspense } from "react";

import FilterBar from "../FilterBar";
import ShowList from "../ShowList";
import WatchlistChips from "../WatchlistChips";
import {
  getJSON,
  type ShowView,
  type VenueOption,
  type WatchlistEntry,
} from "../lib/api";
import { addDaysISO, todayISO } from "../lib/dates";

const DEFAULT_WINDOW_DAYS = 14;

function first(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

export default async function WatchlistPage({
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

  const query = new URLSearchParams({ from, to, watchlist: "true" });
  if (venues) query.set("venues", venues);
  if (timeOfDay === "early" || timeOfDay === "late") {
    query.set("time_of_day", timeOfDay);
  }
  if (performerQuery) query.set("performer_query", performerQuery);
  if (region) query.set("region", region);
  if (neighborhood) query.set("neighborhood", neighborhood);

  const [shows, allVenues, watchlist] = await Promise.all([
    getJSON<ShowView[]>(`/api/shows?${query.toString()}`),
    getJSON<VenueOption[]>(`/api/venues`),
    getJSON<WatchlistEntry[]>(`/api/watchlist`),
  ]);
  const entries = watchlist ?? [];
  const watchlistCanon = new Set(entries.map((entry) => entry.canonical_name));

  return (
    <main className="mx-auto w-full max-w-2xl flex-1 px-6 py-10">
      <header className="mb-6">
        <h1 className="text-3xl font-semibold tracking-tight">Watchlist</h1>
        <p className="text-sm text-zinc-500 dark:text-zinc-400">
          Upcoming shows with performers you follow
        </p>
      </header>

      {shows === null || watchlist === null ? (
        <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200">
          Backend not reachable. Start it with{" "}
          <code className="font-mono">make backend-run</code>, then refresh.
        </div>
      ) : entries.length === 0 ? (
        <p className="text-zinc-500 dark:text-zinc-400">
          Your watchlist is empty. Add performers from the{" "}
          <Link href="/" className="underline hover:no-underline">
            main page
          </Link>{" "}
          to follow them.
        </p>
      ) : (
        <>
          <WatchlistChips entries={entries} />
          <Suspense fallback={null}>
            <FilterBar venues={allVenues ?? []} />
          </Suspense>
          {shows.length === 0 ? (
            <p className="text-zinc-500 dark:text-zinc-400">
              No watchlist matches in this window.
            </p>
          ) : (
            <ShowList shows={shows} watchlistCanon={watchlistCanon} />
          )}
        </>
      )}
    </main>
  );
}
