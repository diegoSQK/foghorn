"use client";

// Phase 7.1 genre filter: a single-select chip group over the venue-default
// genres present in the scraped venue set. Same URL-as-state pattern as the
// region chips (LocationFilter): state derives from useSearchParams(), writes
// go through router.push. Chips render from data, so a new genre value in the
// venue seed appears here without a frontend change; with fewer than two
// distinct genres the group hides entirely (a one-chip filter is noise).

import { usePathname, useRouter, useSearchParams } from "next/navigation";

import type { VenueOption } from "./lib/api";

function chipClass(active: boolean): string {
  return `rounded-full border px-3 py-1 text-sm capitalize transition-colors ${
    active
      ? "border-zinc-900 bg-zinc-900 text-white dark:border-zinc-100 dark:bg-zinc-100 dark:text-zinc-900"
      : "border-zinc-300 text-zinc-700 hover:border-zinc-500 dark:border-zinc-700 dark:text-zinc-300"
  }`;
}

export default function GenreFilter({ venues }: { venues: VenueOption[] }) {
  const router = useRouter();
  const params = useSearchParams();
  const pathname = usePathname();

  const activeGenre = params.get("genre");
  const genres = [
    ...new Set(
      venues.map((v) => v.genre).filter((g): g is string => Boolean(g)),
    ),
  ].sort();

  if (genres.length < 2) return null;

  function selectGenre(genre: string): void {
    const next = new URLSearchParams(params.toString());
    if (activeGenre === genre) next.delete("genre");
    else next.set("genre", genre);
    const query = next.toString();
    router.push(query ? `${pathname}?${query}` : pathname);
  }

  return (
    <fieldset className="flex flex-col gap-3">
      <legend className="mb-1 text-xs text-zinc-500 dark:text-zinc-400">
        Genre
      </legend>
      <div className="flex flex-wrap gap-2">
        {genres.map((genre) => (
          <button
            key={genre}
            type="button"
            aria-pressed={activeGenre === genre}
            onClick={() => selectGenre(genre)}
            className={chipClass(activeGenre === genre)}
          >
            {genre}
          </button>
        ))}
      </div>
    </fieldset>
  );
}
