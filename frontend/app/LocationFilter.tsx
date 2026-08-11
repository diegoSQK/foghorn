"use client";

// Phase 3.2 location filters: a multi-select region chip group plus a
// region-scoped, multi-select neighborhood picker. Lives in its own file so composing it
// into FilterBar.tsx is one import + one JSX line (keeps the merge surface with
// the sibling Phase 3.3 search ticket trivial). Same URL-as-state pattern as
// FilterBar: every control derives from useSearchParams() and writes via
// router.push.

import { useRouter, useSearchParams } from "next/navigation";

import { facetHas, facetValues, toggleFacet } from "./lib/facets";
import {
  chipClass as accentChipClass,
  disabledChipClass,
  inputClass,
  removableChipClass,
} from "./lib/ui";

// All regions render; only those with scraped venues are interactive. The
// rest show a "soon" affordance so the planned Phase 5 expansion is visible.
const REGIONS = ["SF", "East Bay", "North Bay", "Peninsula", "South Bay", "Santa Cruz"] as const;

export type VenueOption = {
  slug: string;
  name: string;
  neighborhood?: string | null;
  region?: string | null;
};

function chipClass(active: boolean, hasData: boolean): string {
  return hasData ? accentChipClass(active) : disabledChipClass;
}

export default function LocationFilter({ venues }: { venues: VenueOption[] }) {
  const router = useRouter();
  const params = useSearchParams();

  const regionParam = params.get("region");
  const neighborhoodParam = params.get("neighborhood");
  const selectedRegions = facetValues(regionParam);
  const regionsWithData = new Set(
    venues.map((v) => v.region).filter((r): r is string => Boolean(r)),
  );

  function navigate(updates: Record<string, string | null>): void {
    const next = new URLSearchParams(params.toString());
    for (const [key, value] of Object.entries(updates)) {
      if (value === null || value === "") next.delete(key);
      else next.set(key, value);
    }
    const query = next.toString();
    router.push(query ? `/?${query}` : "/");
  }

  // Neighborhoods offered by the selected regions (scraped venues only, since
  // /api/venues is already filtered to those). Unioned across regions, so
  // picking SF + East Bay offers both sets.
  function neighborhoodsFor(regions: string[]): string[] {
    if (regions.length === 0) return [];
    const inScope = new Set(regions);
    return [
      ...new Set(
        venues
          .filter((v) => v.region && inScope.has(v.region) && v.neighborhood)
          .map((v) => v.neighborhood as string),
      ),
    ].sort();
  }

  const neighborhoods = neighborhoodsFor(selectedRegions);
  const selectedNeighborhoods = facetValues(neighborhoodParam);

  function toggleRegion(region: string): void {
    const nextRegionParam = toggleFacet(regionParam, region);
    // Neighborhoods are scoped to their region, so deselecting one has to drop
    // its neighborhoods — but only those. Previously any region change cleared
    // the neighborhood outright, which with multi-select would throw away a
    // still-valid selection every time you added a second region.
    const stillValid = new Set(neighborhoodsFor(facetValues(nextRegionParam)));
    const keptNeighborhoods = facetValues(neighborhoodParam).filter((n) =>
      stillValid.has(n),
    );
    navigate({
      region: nextRegionParam,
      neighborhood: keptNeighborhoods.length ? keptNeighborhoods.join(",") : null,
    });
  }

  function toggleNeighborhood(neighborhood: string): void {
    navigate({ neighborhood: toggleFacet(neighborhoodParam, neighborhood) });
  }

  return (
    <fieldset className="flex flex-col gap-3">
      <legend className="mb-1 text-xs text-zinc-500 dark:text-zinc-400">
        Region
      </legend>
      <div className="flex flex-wrap gap-2">
        {REGIONS.map((region) => {
          const hasData = regionsWithData.has(region);
          return (
            <button
              key={region}
              type="button"
              disabled={!hasData}
              aria-pressed={hasData ? facetHas(regionParam, region) : undefined}
              onClick={hasData ? () => toggleRegion(region) : undefined}
              className={chipClass(facetHas(regionParam, region), hasData)}
              title={hasData ? undefined : "Coming soon"}
            >
              {region}
              {!hasData && " (soon)"}
            </button>
          );
        })}
      </div>

      {/* Neighborhood is multi-select too, but 23 of them in SF alone (34 with
          East Bay) is far too many for a chip row — it would bury the shows.
          So it keeps a picker and renders selections as removable pills, the
          same shape the venue picker uses for the same reason. */}
      {neighborhoods.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <span className="text-xs text-zinc-500 dark:text-zinc-400">
            Neighborhood
          </span>
          {selectedNeighborhoods.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5">
              {selectedNeighborhoods.map((n) => (
                <button
                  key={n}
                  type="button"
                  onClick={() => toggleNeighborhood(n)}
                  aria-label={`Remove neighborhood ${n}`}
                  className={removableChipClass}
                >
                  {n} ×
                </button>
              ))}
            </div>
          )}
          <select
            // Always reads "add one" — the current selection lives in the
            // pills above, so the control never shows a stale single value.
            value=""
            onChange={(e) => {
              if (e.target.value) toggleNeighborhood(e.target.value);
            }}
            aria-label="Add neighborhood filter"
            className={`${inputClass} max-w-xs`}
          >
            <option value="">
              {selectedNeighborhoods.length > 0
                ? "Add another neighborhood…"
                : "All neighborhoods"}
            </option>
            {neighborhoods
              .filter((n) => !selectedNeighborhoods.includes(n))
              .map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
          </select>
        </div>
      )}
    </fieldset>
  );
}
