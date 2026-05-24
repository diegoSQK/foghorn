// Phase 3.1 show list: a server component whose filter state lives entirely in
// the URL search params. It parses ?from/?to/?venues/?time_of_day, fetches the
// filtered shows + the venue list, and renders the URL-driven <FilterBar> over
// a date-grouped list. Client-side interactivity is confined to FilterBar.

import { Suspense } from "react";

import FilterBar from "./FilterBar";
import { addDaysISO, todayISO } from "./lib/dates";

type PerformerView = { display: string; canonical: string };

type ShowView = {
  venue: {
    slug: string;
    name: string;
    neighborhood: string | null;
    region: string | null;
  };
  start_local_date: string;
  start_local_time: string;
  doors_local_time: string | null;
  headliner: PerformerView;
  support: PerformerView[];
  ticket_url: string | null;
  price_text: string | null;
  source_url: string;
};

type VenueOption = {
  slug: string;
  name: string;
  neighborhood: string | null;
  region: string | null;
};

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

const DEFAULT_WINDOW_DAYS = 14;

function first(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

async function getJSON<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

function formatDate(isoDate: string): string {
  const [year, month, day] = isoDate.split("-").map(Number);
  const date = new Date(year, month - 1, day); // local — no tz shift
  return date.toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
  });
}

function formatTime(hhmm: string): string {
  const [hour, minute] = hhmm.split(":").map(Number);
  const period = hour >= 12 ? "PM" : "AM";
  const hour12 = hour % 12 || 12;
  return `${hour12}:${minute.toString().padStart(2, "0")} ${period}`;
}

function groupByDate(shows: ShowView[]): [string, ShowView[]][] {
  const groups = new Map<string, ShowView[]>();
  for (const show of shows) {
    const bucket = groups.get(show.start_local_date) ?? [];
    bucket.push(show);
    groups.set(show.start_local_date, bucket);
  }
  return [...groups.entries()];
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

  const query = new URLSearchParams({ from, to });
  if (venues) query.set("venues", venues);
  if (timeOfDay === "early" || timeOfDay === "late") {
    query.set("time_of_day", timeOfDay);
  }
  if (performerQuery) query.set("performer_query", performerQuery);

  const [shows, allVenues] = await Promise.all([
    getJSON<ShowView[]>(`/api/shows?${query.toString()}`),
    getJSON<VenueOption[]>(`/api/venues`),
  ]);

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
            <div className="flex flex-col gap-8">
              {groupByDate(shows).map(([date, dayShows]) => (
                <section key={date}>
                  <h2 className="mb-3 border-b border-zinc-200 pb-1 text-sm font-semibold uppercase tracking-wide text-zinc-500 dark:border-zinc-800 dark:text-zinc-400">
                    {formatDate(date)}
                  </h2>
                  <ul className="flex flex-col gap-4">
                    {dayShows.map((show, i) => (
                      <li key={`${date}-${show.start_local_time}-${i}`}>
                        <div className="flex items-baseline justify-between gap-4">
                          <span className="font-medium">
                            {show.headliner.display}
                          </span>
                          <span className="shrink-0 text-sm tabular-nums text-zinc-500 dark:text-zinc-400">
                            {formatTime(show.start_local_time)}
                          </span>
                        </div>
                        {show.support.length > 0 && (
                          <p className="text-sm text-zinc-500 dark:text-zinc-400">
                            with {show.support.map((s) => s.display).join(", ")}
                          </p>
                        )}
                        <p className="text-sm text-zinc-500 dark:text-zinc-400">
                          {show.venue.name}
                          {show.venue.neighborhood
                            ? ` · ${show.venue.neighborhood}`
                            : ""}
                          {show.price_text ? ` · ${show.price_text}` : ""}
                          {show.ticket_url ? (
                            <>
                              {" · "}
                              <a
                                href={show.ticket_url}
                                className="underline hover:no-underline"
                                target="_blank"
                                rel="noreferrer"
                              >
                                tickets
                              </a>
                            </>
                          ) : null}
                        </p>
                      </li>
                    ))}
                  </ul>
                </section>
              ))}
            </div>
          )}
        </>
      )}
    </main>
  );
}
