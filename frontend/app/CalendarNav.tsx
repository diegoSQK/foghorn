// Prev / Today / Next navigation for the day/week/month views. Pure links —
// the server page computes the step size, so this stays a server component
// and back/forward + shared URLs keep working.

import Link from "next/link";

const navLink =
  "rounded-full border border-zinc-300 px-3 py-1 text-sm text-zinc-700 transition-colors hover:border-teal-600 hover:text-teal-700 dark:border-zinc-700 dark:text-zinc-300 dark:hover:border-teal-400 dark:hover:text-teal-300";

export default function CalendarNav({
  title,
  prevHref,
  todayHref,
  nextHref,
}: {
  title: string;
  prevHref: string;
  todayHref: string;
  nextHref: string;
}) {
  return (
    <div className="mb-4 flex items-center justify-between gap-3">
      <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
      <div className="flex gap-2">
        <Link href={prevHref} className={navLink} aria-label="Previous">
          ‹
        </Link>
        <Link href={todayHref} className={navLink}>
          Today
        </Link>
        <Link href={nextHref} className={navLink} aria-label="Next">
          ›
        </Link>
      </div>
    </div>
  );
}
