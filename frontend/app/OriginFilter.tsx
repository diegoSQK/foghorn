"use client";

// Local/touring filter chips (performer-origin tagging v1). Same URL-as-state
// pattern as the region/genre chips. Origin tags are inferred (heuristic) or
// hand-set and cover only part of the catalog, so the labels say "acts" and
// the parent only renders this when tagged performers actually exist in the
// current result set (or the filter is already active) — no dead chips on an
// untagged DB.

import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { facetHas, toggleFacet } from "./lib/facets";
import { chipClass } from "./lib/ui";

const OPTIONS = [
  { value: "local", label: "Local acts" },
  { value: "touring", label: "Touring" },
] as const;

export default function OriginFilter() {
  const router = useRouter();
  const params = useSearchParams();
  const pathname = usePathname();

  const activeParam = params.get("origin");

  function toggleOrigin(value: string): void {
    const next = new URLSearchParams(params.toString());
    const updated = toggleFacet(activeParam, value);
    if (updated === null) next.delete("origin");
    else next.set("origin", updated);
    const query = next.toString();
    router.push(query ? `${pathname}?${query}` : pathname);
  }

  return (
    <fieldset className="flex flex-col gap-3">
      <legend className="mb-1 text-xs text-zinc-500 dark:text-zinc-400">
        Origin{" "}
        <span title="Inferred from gigging patterns; may be incomplete">
          (likely)
        </span>
      </legend>
      <div className="flex flex-wrap gap-2">
        {OPTIONS.map(({ value, label }) => (
          <button
            key={value}
            type="button"
            aria-pressed={facetHas(activeParam, value)}
            onClick={() => toggleOrigin(value)}
            className={chipClass(facetHas(activeParam, value))}
          >
            {label}
          </button>
        ))}
      </div>
    </fieldset>
  );
}
