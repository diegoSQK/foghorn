"use client";

// Phase 3.2 location filters: a single-select region chip group plus a
// region-scoped neighborhood dropdown. Lives in its own file so composing it
// into FilterBar.tsx is one import + one JSX line (keeps the merge surface with
// the sibling Phase 3.3 search ticket trivial). Same URL-as-state pattern as
// FilterBar: every control derives from useSearchParams() and writes via
// router.push.

import { useRouter, useSearchParams } from "next/navigation";

// All four regions render; only those with scraped venues are interactive. The
// rest show a "soon" affordance so the planned Phase 5 expansion is visible.
const REGIONS = ["SF", "East Bay", "Peninsula", "South Bay"] as const;

export type VenueOption = {
  slug: string;
  name: string;
  neighborhood?: string | null;
  region?: string | null;
};

function chipClass(active: boolean, hasData: boolean): string {
  if (!hasData) {
    return "cursor-not-allowed rounded-full border border-dashed border-zinc-200 px-3 py-1 text-sm text-zinc-400 dark:border-zinc-800 dark:text-zinc-600";
  }
  return `rounded-full border px-3 py-1 text-sm transition-colors ${
    active
      ? "border-zinc-900 bg-zinc-900 text-white dark:border-zinc-100 dark:bg-zinc-100 dark:text-zinc-900"
      : "border-zinc-300 text-zinc-700 hover:border-zinc-500 dark:border-zinc-700 dark:text-zinc-300"
  }`;
}

export default function LocationFilter({ venues }: { venues: VenueOption[] }) {
  const router = useRouter();
  const params = useSearchParams();

  const activeRegion = params.get("region");
  const activeNeighborhood = params.get("neighborhood") ?? "";
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

  function selectRegion(region: string): void {
    // Re-clicking the active region clears it. Either way the neighborhood is
    // dropped — it's scoped to a region, so it can't outlive one.
    navigate({
      region: activeRegion === region ? null : region,
      neighborhood: null,
    });
  }

  // Neighborhoods available within the selected region (scraped venues only,
  // since /api/venues is already filtered to those).
  const neighborhoods = activeRegion
    ? [
        ...new Set(
          venues
            .filter((v) => v.region === activeRegion && v.neighborhood)
            .map((v) => v.neighborhood as string),
        ),
      ].sort()
    : [];

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
              aria-pressed={hasData ? activeRegion === region : undefined}
              onClick={hasData ? () => selectRegion(region) : undefined}
              className={chipClass(activeRegion === region, hasData)}
              title={hasData ? undefined : "Coming soon"}
            >
              {region}
              {!hasData && " (soon)"}
            </button>
          );
        })}
      </div>

      {activeRegion && neighborhoods.length > 0 && (
        <label className="flex flex-col gap-1 text-xs text-zinc-500 dark:text-zinc-400">
          Neighborhood
          <select
            value={activeNeighborhood}
            onChange={(e) => navigate({ neighborhood: e.target.value || null })}
            className="rounded-md border border-zinc-300 bg-transparent px-2 py-1 text-sm text-zinc-900 dark:border-zinc-700 dark:text-zinc-100"
          >
            <option value="">All neighborhoods</option>
            {neighborhoods.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
      )}
    </fieldset>
  );
}
