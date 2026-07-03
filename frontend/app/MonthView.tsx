// Month view: a classic calendar grid. With ~40 shows on a busy night the
// cells can't list bills, so each cell shows the first couple of headliners
// plus a "+N more" — and the whole cell links into the day view. On small
// screens the cells collapse to a date + count.

import Link from "next/link";

import type { ShowView } from "./lib/api";
import { addDaysISO, mondayOfISO, todayISO } from "./lib/dates";

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export default function MonthView({
  shows,
  monthStart, // YYYY-MM-01
  monthEnd, // YYYY-MM-<last>
  dayHref,
}: {
  shows: ShowView[];
  monthStart: string;
  monthEnd: string;
  dayHref: (dateISO: string) => string;
}) {
  const byDate = new Map<string, ShowView[]>();
  for (const show of shows) {
    const bucket = byDate.get(show.start_local_date) ?? [];
    bucket.push(show);
    byDate.set(show.start_local_date, bucket);
  }

  // Grid runs from the Monday on/before the 1st through the Sunday on/after
  // the last day.
  const cells: string[] = [];
  for (let d = mondayOfISO(monthStart); cells.length < 42; d = addDaysISO(d, 1)) {
    cells.push(d);
    if (d >= monthEnd && cells.length % 7 === 0) break;
  }
  const today = todayISO();

  return (
    <div>
      <div className="mb-1 grid grid-cols-7 gap-px text-center text-[11px] font-semibold uppercase tracking-wide text-zinc-400 dark:text-zinc-500">
        {WEEKDAYS.map((d) => (
          <div key={d}>{d}</div>
        ))}
      </div>
      <div className="grid grid-cols-7 gap-px overflow-hidden rounded-lg border border-zinc-200 bg-zinc-200 dark:border-zinc-800 dark:bg-zinc-800">
        {cells.map((date) => {
          const inMonth = date >= monthStart && date <= monthEnd;
          const dayShows = byDate.get(date) ?? [];
          const isToday = date === today;
          return (
            <Link
              key={date}
              href={dayHref(date)}
              className={`min-h-16 p-1 text-left align-top transition-colors sm:min-h-24 sm:p-1.5 ${
                inMonth
                  ? "bg-white hover:bg-teal-50/60 dark:bg-zinc-950 dark:hover:bg-teal-950/30"
                  : "bg-zinc-50 text-zinc-400 hover:bg-teal-50/40 dark:bg-zinc-900/60 dark:text-zinc-600"
              }`}
            >
              <div className="flex items-baseline justify-between">
                <span
                  className={`text-xs font-semibold ${
                    isToday
                      ? "rounded-full bg-teal-700 px-1.5 text-white dark:bg-teal-500 dark:text-zinc-950"
                      : ""
                  }`}
                >
                  {Number(date.slice(8))}
                </span>
                {dayShows.length > 0 && (
                  <span className="text-[10px] tabular-nums text-teal-700 sm:hidden dark:text-teal-400">
                    {dayShows.length}
                  </span>
                )}
              </div>
              {dayShows.length > 0 && (
                <div className="mt-0.5 hidden sm:block">
                  {dayShows.slice(0, 2).map((show) => (
                    <p
                      key={show.id}
                      className="truncate text-[11px] leading-tight text-zinc-600 dark:text-zinc-300"
                      title={show.headliner.display}
                    >
                      {show.headliner.display}
                    </p>
                  ))}
                  {dayShows.length > 2 && (
                    <p className="text-[11px] font-medium text-teal-700 dark:text-teal-400">
                      +{dayShows.length - 2} more
                    </p>
                  )}
                </div>
              )}
            </Link>
          );
        })}
      </div>
    </div>
  );
}
