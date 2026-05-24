// Minimal Phase 2.1 list view: a flat, date-grouped list of upcoming shows
// fetched from the backend. Intentionally bare — Phase 3 adds filters/search UI.

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

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function getShows(): Promise<ShowView[] | null> {
  try {
    const res = await fetch(`${API_BASE}/api/shows`, { cache: "no-store" });
    if (!res.ok) return null;
    return (await res.json()) as ShowView[];
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

export default async function Home() {
  const shows = await getShows();

  return (
    <main className="mx-auto w-full max-w-2xl flex-1 px-6 py-10">
      <header className="mb-8">
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
      ) : shows.length === 0 ? (
        <p className="text-zinc-500 dark:text-zinc-400">
          No upcoming shows. Run <code className="font-mono">make scrape</code>{" "}
          to populate the calendar.
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
    </main>
  );
}
