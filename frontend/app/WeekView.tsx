// Week view: seven day columns on desktop, stacked day sections on mobile.
// Cards are deliberately compact (time + headliner + venue); each day header
// links into the day view for the full detail.

import Link from "next/link";

import type { ShowView } from "./lib/api";
import { addDaysISO, todayISO } from "./lib/dates";

function shortTime(hhmm: string): string {
  const [hour, minute] = hhmm.split(":").map(Number);
  const period = hour >= 12 ? "p" : "a";
  const hour12 = hour % 12 || 12;
  return minute === 0 ? `${hour12}${period}` : `${hour12}:${String(minute).padStart(2, "0")}${period}`;
}

function dayLabel(iso: string): string {
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(year, month - 1, day).toLocaleDateString("en-US", {
    weekday: "short",
    month: "numeric",
    day: "numeric",
  });
}

export default function WeekView({
  shows,
  weekStart,
  dayHref,
}: {
  shows: ShowView[];
  weekStart: string; // Monday, YYYY-MM-DD
  dayHref: (dateISO: string) => string;
}) {
  const days = Array.from({ length: 7 }, (_, i) => addDaysISO(weekStart, i));
  const byDate = new Map<string, ShowView[]>(days.map((d) => [d, []]));
  for (const show of shows) byDate.get(show.start_local_date)?.push(show);
  const today = todayISO();

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-7 lg:gap-2">
      {days.map((date) => {
        const dayShows = byDate.get(date) ?? [];
        const isToday = date === today;
        return (
          <section
            key={date}
            className={`rounded-lg border p-2 ${
              isToday
                ? "border-teal-600/50 bg-teal-50/50 dark:border-teal-400/40 dark:bg-teal-950/30"
                : "border-zinc-200 dark:border-zinc-800"
            }`}
          >
            <Link
              href={dayHref(date)}
              className={`mb-2 block text-xs font-semibold uppercase tracking-wide hover:underline ${
                isToday
                  ? "text-teal-800 dark:text-teal-300"
                  : "text-zinc-500 dark:text-zinc-400"
              }`}
            >
              {dayLabel(date)}
            </Link>
            {dayShows.length === 0 ? (
              <p className="text-xs text-zinc-400 dark:text-zinc-600">—</p>
            ) : (
              <ul className="flex flex-col gap-1.5">
                {dayShows.map((show) => (
                  <li key={show.id} className="text-xs leading-snug">
                    <span className="tabular-nums text-zinc-400 dark:text-zinc-500">
                      {shortTime(show.start_local_time)}
                    </span>{" "}
                    <span className="font-medium" title={show.headliner.display}>
                      {show.headliner.display}
                    </span>
                    <span className="block truncate text-zinc-500 dark:text-zinc-400">
                      {show.venue.name}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        );
      })}
    </div>
  );
}
