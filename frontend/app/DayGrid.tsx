// Day view: a time × venue grid. Venues with shows that day become columns
// (ordered by earliest set time), a time ruler runs down the sticky left
// edge, and each show renders as a block at its start time — so one evening
// reads as a single glance (what overlaps what, early vs. late) instead of
// duplicating the list view. Busy nights scroll horizontally.

import Link from "next/link";

import type { ShowView } from "./lib/api";
import { genreAccentClass } from "./lib/ui";

const HOUR_PX = 64;
// Blocks use the source's stated end time when one exists (many venues
// publish "7-11pm" ranges); otherwise this nominal set length. Either way
// the height clamps so back-to-back sets at one venue never overlap.
const DEFAULT_SET_MINUTES = 90;
const MIN_BLOCK_PX = 34;

function minutesOf(hhmm: string): number {
  const [hour, minute] = hhmm.split(":").map(Number);
  return hour * 60 + minute;
}

function formatTime(hhmm: string): string {
  const [hour, minute] = hhmm.split(":").map(Number);
  const period = hour >= 12 ? "PM" : "AM";
  const hour12 = hour % 12 || 12;
  return minute === 0
    ? `${hour12} ${period}`
    : `${hour12}:${String(minute).padStart(2, "0")} ${period}`;
}

function hourLabel(hour: number): string {
  const h = hour % 24;
  const period = h >= 12 && h < 24 ? "PM" : "AM";
  return `${h % 12 || 12} ${period}`;
}

type VenueColumn = {
  venue: ShowView["venue"];
  shows: ShowView[]; // sorted by start time
};

export default function DayGrid({ shows }: { shows: ShowView[] }) {
  const bySlug = new Map<string, VenueColumn>();
  for (const show of shows) {
    const column = bySlug.get(show.venue.slug) ?? { venue: show.venue, shows: [] };
    column.shows.push(show);
    bySlug.set(show.venue.slug, column);
  }
  const columns = [...bySlug.values()];
  for (const column of columns) {
    column.shows.sort((a, b) =>
      a.start_local_time.localeCompare(b.start_local_time),
    );
  }
  columns.sort(
    (a, b) =>
      a.shows[0].start_local_time.localeCompare(b.shows[0].start_local_time) ||
      a.venue.name.localeCompare(b.venue.name),
  );

  // A stated end earlier than its start crosses midnight ("9:30pm-2am").
  const endMinutesOf = (s: ShowView): number | null => {
    if (!s.end_local_time) return null;
    const end = minutesOf(s.end_local_time);
    return end <= minutesOf(s.start_local_time) ? end + 24 * 60 : end;
  };
  const starts = shows.map((s) => minutesOf(s.start_local_time));
  const blockEnds = shows.map(
    (s) => endMinutesOf(s) ?? minutesOf(s.start_local_time) + DEFAULT_SET_MINUTES,
  );
  const startHour = Math.floor(Math.min(...starts) / 60);
  const endHour = Math.ceil(Math.max(...blockEnds) / 60);
  const rangeStartMin = startHour * 60;
  const bodyHeight = (endHour - startHour) * HOUR_PX;
  const hours = Array.from(
    { length: endHour - startHour },
    (_, i) => startHour + i,
  );

  const topOf = (show: ShowView) =>
    ((minutesOf(show.start_local_time) - rangeStartMin) / 60) * HOUR_PX;

  return (
    <div className="overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-800">
      <div
        className="grid min-w-max"
        style={{
          gridTemplateColumns: `3rem repeat(${columns.length}, minmax(9.5rem, 1fr))`,
        }}
      >
        {/* Header row: ruler corner + one venue heading per column. */}
        <div className="sticky left-0 z-[2] border-b border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950" />
        {columns.map(({ venue }) => (
          <div
            key={venue.slug}
            className="border-b border-l border-zinc-200 px-2 py-2 dark:border-zinc-800"
          >
            <Link
              href={`/?venues=${venue.slug}`}
              className="block truncate text-xs font-semibold text-zinc-700 hover:text-teal-700 hover:underline dark:text-zinc-300 dark:hover:text-teal-300"
              title={venue.name}
            >
              {venue.name}
            </Link>
            {venue.neighborhood && (
              <p className="truncate text-[10px] text-zinc-400 dark:text-zinc-500">
                {venue.neighborhood}
              </p>
            )}
          </div>
        ))}

        {/* Body row: the hour ruler, then one relative canvas per venue with
            hour gridlines behind absolutely-positioned show blocks. */}
        <div
          className="sticky left-0 z-[2] bg-white dark:bg-zinc-950"
          style={{ height: bodyHeight }}
        >
          {hours.map((hour) => (
            <span
              key={hour}
              className="absolute right-1.5 text-[10px] tabular-nums text-zinc-400 dark:text-zinc-500"
              style={{ top: (hour - startHour) * HOUR_PX + 2 }}
            >
              {hourLabel(hour)}
            </span>
          ))}
        </div>
        {columns.map((column) => (
          <div
            key={column.venue.slug}
            className="relative border-l border-zinc-200 dark:border-zinc-800"
            style={{ height: bodyHeight }}
          >
            {hours.map((hour) => (
              <div
                key={hour}
                aria-hidden="true"
                className="absolute inset-x-0 border-t border-zinc-100 dark:border-zinc-900"
                style={{ top: (hour - startHour) * HOUR_PX }}
              />
            ))}
            {column.shows.map((show, i) => {
              const top = topOf(show);
              // Stated end when the source published one, else the nominal
              // length; either way the height clamps against the next
              // *later* set at this venue (a same-start sibling shares the
              // row instead — see below).
              const stated = endMinutesOf(show);
              const naturalPx = stated
                ? ((stated - minutesOf(show.start_local_time)) / 60) * HOUR_PX
                : (DEFAULT_SET_MINUTES / 60) * HOUR_PX;
              const nextLater = column.shows.find((s) => topOf(s) > top);
              const room = nextLater ? topOf(nextLater) - top - 4 : Infinity;
              const height = Math.max(
                MIN_BLOCK_PX,
                Math.min(naturalPx, room),
              );
              // Same-start shows split the column width — venues do post two
              // simultaneous listings, and a straight overlay renders one
              // bill on top of the other.
              const siblings = column.shows.filter(
                (s) => s.start_local_time === show.start_local_time,
              );
              const lane = siblings.indexOf(show);
              const laneCount = siblings.length;
              const bill = [
                show.headliner.display,
                ...show.support.map((p) => p.display),
              ].join(" · ");
              const href =
                show.ticket_url ??
                (show.source_url.startsWith("manual://")
                  ? null
                  : show.source_url);
              const blockClass = `absolute overflow-hidden rounded-md border-l-2 bg-teal-50/80 px-1.5 py-1 dark:bg-teal-950/40 ${genreAccentClass(show.genre)}`;
              const content = (
                <>
                  <p className="text-[10px] tabular-nums leading-tight text-zinc-500 dark:text-zinc-400">
                    {formatTime(show.start_local_time)}
                  </p>
                  <p className="truncate text-xs font-medium leading-tight text-zinc-800 dark:text-zinc-200">
                    {show.headliner.display}
                  </p>
                  {show.support.length > 0 && (
                    <p className="truncate text-[10px] leading-tight text-zinc-500 dark:text-zinc-400">
                      with {show.support.map((p) => p.display).join(", ")}
                    </p>
                  )}
                </>
              );
              const style = {
                top,
                height,
                left: `calc(${(lane * 100) / laneCount}% + 4px)`,
                width: `calc(${100 / laneCount}% - 8px)`,
              };
              const key = `${show.start_local_time}-${i}`;
              return href ? (
                <a
                  key={key}
                  href={href}
                  target="_blank"
                  rel="noreferrer"
                  title={`${formatTime(show.start_local_time)} — ${bill}`}
                  className={`${blockClass} transition-colors hover:bg-teal-100/90 dark:hover:bg-teal-900/50`}
                  style={style}
                >
                  {content}
                </a>
              ) : (
                <div
                  key={key}
                  title={`${formatTime(show.start_local_time)} — ${bill}`}
                  className={blockClass}
                  style={style}
                >
                  {content}
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}
