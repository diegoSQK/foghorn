// Show calendar (/). A server component whose state lives entirely in the
// URL search params: it parses them, fetches the filtered shows + venues +
// watchlist, and renders the URL-driven <FilterBar> over one of four views —
// the default date-grouped list, or day/week/month calendar views (?view=)
// whose date window derives from ?anchor= instead of from/to.

import { Suspense } from "react";

import CalendarNav from "./CalendarNav";
import FilterBar from "./FilterBar";
import MonthView from "./MonthView";
import ShowList from "./ShowList";
import ViewSwitcher from "./ViewSwitcher";
import WeekView from "./WeekView";
import {
  getJSON,
  type ShowView,
  type VenueOption,
  type WatchlistEntry,
} from "./lib/api";
import {
  addDaysISO,
  isISODate,
  monthBoundsISO,
  mondayOfISO,
  todayISO,
} from "./lib/dates";

const DEFAULT_WINDOW_DAYS = 14;

function first(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

function longDate(iso: string): string {
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(year, month - 1, day).toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
  });
}

function monthTitle(iso: string): string {
  const [year, month] = iso.split("-").map(Number);
  return new Date(year, month - 1, 1).toLocaleDateString("en-US", {
    month: "long",
    year: "numeric",
  });
}

export default async function Home({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const sp = await searchParams;
  const today = todayISO();

  const rawView = first(sp.view);
  const view =
    rawView === "day" || rawView === "week" || rawView === "month"
      ? rawView
      : "list";
  const anchorParam = first(sp.anchor);
  const anchor = isISODate(anchorParam) ? anchorParam : today;

  // The view defines the fetch window: list uses explicit from/to, the
  // calendar views derive theirs from the anchor date.
  let from: string;
  let to: string;
  if (view === "day") {
    from = anchor;
    to = anchor;
  } else if (view === "week") {
    from = mondayOfISO(anchor);
    to = addDaysISO(from, 6);
  } else if (view === "month") {
    ({ from, to } = monthBoundsISO(anchor));
  } else {
    from = first(sp.from) ?? today;
    to = first(sp.to) ?? addDaysISO(today, DEFAULT_WINDOW_DAYS);
  }

  const venues = first(sp.venues);
  const timeOfDay = first(sp.time_of_day);
  const performerQuery = first(sp.performer_query);
  const region = first(sp.region);
  const neighborhood = first(sp.neighborhood);
  const genre = first(sp.genre);
  const origin = first(sp.origin);
  const type = first(sp.type);

  const query = new URLSearchParams({ from, to });
  if (venues) query.set("venues", venues);
  if (timeOfDay === "early" || timeOfDay === "late") {
    query.set("time_of_day", timeOfDay);
  }
  if (performerQuery) query.set("performer_query", performerQuery);
  if (region) query.set("region", region);
  if (neighborhood) query.set("neighborhood", neighborhood);
  if (genre) query.set("genre", genre);
  if (origin === "local" || origin === "touring") query.set("origin", origin);
  if (type === "show" || type === "jam") query.set("type", type);

  const [shows, allVenues, watchlist] = await Promise.all([
    getJSON<ShowView[]>(`/api/shows?${query.toString()}`),
    getJSON<VenueOption[]>(`/api/venues`),
    getJSON<WatchlistEntry[]>(`/api/watchlist`),
  ]);
  const watchlistCanon = new Set(
    (watchlist ?? []).map((entry) => entry.canonical_name),
  );

  // Hrefs for the calendar navigation — plain links that preserve every
  // other filter and swap the anchor (or the whole view for day cells).
  function hrefWith(updates: Record<string, string | null>): string {
    const next = new URLSearchParams();
    for (const [key, value] of Object.entries(sp)) {
      const v = first(value);
      if (v !== undefined) next.set(key, v);
    }
    for (const [key, value] of Object.entries(updates)) {
      if (value === null) next.delete(key);
      else next.set(key, value);
    }
    const q = next.toString();
    return q ? `/?${q}` : "/";
  }
  const dayHref = (date: string) => hrefWith({ view: "day", anchor: date });

  const wide = view === "week" || view === "month";

  return (
    <main
      className={`mx-auto w-full flex-1 px-6 py-10 ${wide ? "max-w-5xl" : "max-w-2xl"}`}
    >
      <header className="mb-6">
        <h1 className="text-3xl font-semibold tracking-tight">
          foghorn<span className="text-teal-600 dark:text-teal-400">.</span>
        </h1>
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
            <ViewSwitcher />
          </Suspense>
          <Suspense fallback={null}>
            <FilterBar
              venues={allVenues ?? []}
              showDateControls={view === "list"}
              showOriginFilter={
                Boolean(origin) ||
                shows.some(
                  (s) =>
                    s.headliner.origin !== null ||
                    s.support.some((p) => p.origin !== null),
                )
              }
            />
          </Suspense>

          {view === "day" && (
            <CalendarNav
              title={longDate(anchor)}
              prevHref={hrefWith({ anchor: addDaysISO(anchor, -1) })}
              todayHref={hrefWith({ anchor: null })}
              nextHref={hrefWith({ anchor: addDaysISO(anchor, 1) })}
            />
          )}
          {view === "week" && (
            <CalendarNav
              title={`Week of ${longDate(from)}`}
              prevHref={hrefWith({ anchor: addDaysISO(from, -7) })}
              todayHref={hrefWith({ anchor: null })}
              nextHref={hrefWith({ anchor: addDaysISO(from, 7) })}
            />
          )}
          {view === "month" && (
            <CalendarNav
              title={monthTitle(from)}
              prevHref={hrefWith({ anchor: addDaysISO(from, -1) })}
              todayHref={hrefWith({ anchor: null })}
              nextHref={hrefWith({ anchor: addDaysISO(to, 1) })}
            />
          )}

          {view === "week" ? (
            <WeekView shows={shows} weekStart={from} dayHref={dayHref} />
          ) : view === "month" ? (
            <MonthView
              shows={shows}
              monthStart={from}
              monthEnd={to}
              dayHref={dayHref}
            />
          ) : shows.length === 0 ? (
            <p className="text-zinc-500 dark:text-zinc-400">
              {performerQuery
                ? `No shows matching “${performerQuery}” in this window. Try widening the date range or clearing other filters.`
                : view === "day"
                  ? "No shows on this day match the filters."
                  : "No shows match these filters. Try widening the date range or clearing filters."}
            </p>
          ) : (
            <ShowList
              shows={shows}
              watchlistCanon={watchlistCanon}
              showDateHeaders={view !== "day"}
            />
          )}
        </>
      )}
    </main>
  );
}
