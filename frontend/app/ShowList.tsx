// Date-grouped show list, shared by `/` and `/watchlist`. Server component;
// each performer name carries a client add/remove button whose initial state
// comes from the server-computed `watchlistCanon` set.

import AddToWatchlistButton from "./AddToWatchlistButton";
import RemoveEventButton from "./RemoveEventButton";
import type { ShowView } from "./lib/api";

// Subtle inline badge for heuristically/hand-tagged local acts. Touring gets
// no badge — local is the tag worth surfacing, and unknown must not read as
// "not local".
function LocalBadge({ origin }: { origin: "local" | "touring" | null }) {
  if (origin !== "local") return null;
  return (
    <span
      className="ml-1 rounded-full border border-emerald-300 px-1.5 py-px align-middle text-[10px] font-medium uppercase tracking-wide text-emerald-700 dark:border-emerald-800 dark:text-emerald-400"
      title="Likely a local act (inferred from gigging patterns)"
    >
      local
    </span>
  );
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

export default function ShowList({
  shows,
  watchlistCanon,
}: {
  shows: ShowView[];
  watchlistCanon: Set<string>;
}) {
  return (
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
                    <LocalBadge origin={show.headliner.origin} />
                    <AddToWatchlistButton
                      displayName={show.headliner.display}
                      canonicalName={show.headliner.canonical}
                      initiallyOn={watchlistCanon.has(show.headliner.canonical)}
                    />
                    {show.source === "manual" && (
                      <>
                        <span
                          className="ml-1 rounded-full border border-sky-300 px-1.5 py-px align-middle text-[10px] font-medium uppercase tracking-wide text-sky-700 dark:border-sky-800 dark:text-sky-400"
                          title="You added this event manually"
                        >
                          added by you
                        </span>
                        <RemoveEventButton showId={show.id} />
                      </>
                    )}
                  </span>
                  <span className="shrink-0 text-sm tabular-nums text-zinc-500 dark:text-zinc-400">
                    {formatTime(show.start_local_time)}
                  </span>
                </div>
                {show.support.length > 0 && (
                  <p className="text-sm text-zinc-500 dark:text-zinc-400">
                    with{" "}
                    {show.support.map((performer, j) => (
                      <span key={performer.canonical}>
                        {j > 0 ? ", " : ""}
                        {performer.display}
                        <LocalBadge origin={performer.origin} />
                        <AddToWatchlistButton
                          displayName={performer.display}
                          canonicalName={performer.canonical}
                          initiallyOn={watchlistCanon.has(performer.canonical)}
                        />
                      </span>
                    ))}
                  </p>
                )}
                <p className="text-sm text-zinc-500 dark:text-zinc-400">
                  {show.venue.name}
                  {show.venue.neighborhood ? ` · ${show.venue.neighborhood}` : ""}
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
  );
}
