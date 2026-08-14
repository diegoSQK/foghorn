"use client";

// Event-type filter chips: shows vs jam sessions (?type=). Same URL-as-state
// pattern as the region/genre/origin chips. Default (no chip active) is every
// type, comedy included.

import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { facetHas, toggleFacet } from "./lib/facets";
import { chipClass } from "./lib/ui";

const OPTIONS = [
  { value: "show", label: "Shows" },
  { value: "jam", label: "Jam sessions" },
  // Non-music bookings a music venue takes between gigs — stand-up, mostly.
  // Ingested rather than dropped so a busy Friday at the Masonic is visible,
  // and filterable so it needn't be.
  { value: "comedy", label: "Comedy" },
] as const;

export default function TypeFilter() {
  const router = useRouter();
  const params = useSearchParams();
  const pathname = usePathname();

  const activeParam = params.get("type");

  function toggleType(value: string): void {
    const next = new URLSearchParams(params.toString());
    const updated = toggleFacet(activeParam, value);
    if (updated === null) next.delete("type");
    else next.set("type", updated);
    const query = next.toString();
    router.push(query ? `${pathname}?${query}` : pathname);
  }

  return (
    <fieldset className="flex flex-col gap-3">
      <legend className="mb-1 text-xs text-zinc-500 dark:text-zinc-400">
        Type
      </legend>
      <div className="flex flex-wrap gap-2">
        {OPTIONS.map(({ value, label }) => (
          <button
            key={value}
            type="button"
            aria-pressed={facetHas(activeParam, value)}
            onClick={() => toggleType(value)}
            className={chipClass(facetHas(activeParam, value))}
          >
            {label}
          </button>
        ))}
      </div>
    </fieldset>
  );
}
