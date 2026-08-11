"use client";

// Phase 7.1 genre filter: a multi-select chip group over the venue-default
// genres present in the scraped venue set. Same URL-as-state pattern as the
// region chips (LocationFilter): state derives from useSearchParams(), writes
// go through router.push. Chips render from data, so a new genre value in the
// venue seed appears here without a frontend change; with fewer than two
// distinct genres the group hides entirely (a one-chip filter is noise).

import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { facetHas, toggleFacet } from "./lib/facets";
import { chipClass } from "./lib/ui";

import type { VenueOption } from "./lib/api";

export default function GenreFilter({ venues }: { venues: VenueOption[] }) {
  const router = useRouter();
  const params = useSearchParams();
  const pathname = usePathname();

  const genreParam = params.get("genre");
  // "eclectic" is a venue's admission of no lean — filtering by it answers
  // no real question, so it gets no chip (the URL param still works).
  const genres = [
    ...new Set(
      venues
        .filter((v) => v.source !== "aggregator") // quarantined: no chip noise
        .map((v) => v.genre)
        .filter((g): g is string => Boolean(g) && g !== "eclectic"),
    ),
  ].sort();

  if (genres.length < 2) return null;

  // Multi-select: selecting jazz and funk means "jazz or funk". A show has
  // one resolved genre, so an intersection would always be empty.
  function toggleGenre(genre: string): void {
    const next = new URLSearchParams(params.toString());
    const value = toggleFacet(genreParam, genre);
    if (value === null) next.delete("genre");
    else next.set("genre", value);
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
            aria-pressed={facetHas(genreParam, genre)}
            onClick={() => toggleGenre(genre)}
            className={chipClass(facetHas(genreParam, genre))}
          >
            {genre}
          </button>
        ))}
      </div>
    </fieldset>
  );
}
