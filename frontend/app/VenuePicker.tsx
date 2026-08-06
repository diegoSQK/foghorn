"use client";

// First-class venue selection (replaces the raw 37-checkbox grid): a search
// box over a region-grouped list whose rows toggle membership in the
// ?venues= URL param. Selected venues render as removable chips, so the
// state reads honestly — no chips means no constraint (the old
// all-boxes-checked default implied a selection that wasn't there).
// Followed venues sort first within each region and always carry their ★.

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import PinVenueButton from "./PinVenueButton";
import type { VenueOption } from "./lib/api";
import { inputClass } from "./lib/ui";

const REGION_ORDER = ["SF", "East Bay", "Peninsula", "South Bay", "Santa Cruz"];

export default function VenuePicker({
  venues,
  watchedVenueSlugs,
  showPins = true,
}: {
  venues: VenueOption[];
  watchedVenueSlugs: Set<string>;
  // Pinning needs an account; anonymous visitors get a pin-less picker.
  showPins?: boolean;
}) {
  const router = useRouter();
  const params = useSearchParams();
  const pathname = usePathname();
  const [query, setQuery] = useState("");

  const venuesParam = params.get("venues");
  const selected = new Set(
    venuesParam ? venuesParam.split(",").filter(Boolean) : [],
  );
  const bySlug = new Map(venues.map((v) => [v.slug, v]));

  function setSelection(next: Set<string>): void {
    const nextParams = new URLSearchParams(params.toString());
    if (next.size === 0 || next.size === visible.length) {
      nextParams.delete("venues");
    } else {
      nextParams.set("venues", [...next].sort().join(","));
    }
    const q = nextParams.toString();
    router.push(q ? `${pathname}?${q}` : pathname);
  }

  function toggle(slug: string): void {
    const next = new Set(selected);
    if (next.has(slug)) next.delete(slug);
    else next.add(slug);
    setSelection(next);
  }

  const needle = query.trim().toLowerCase();
  const longTail = params.get("long_tail") === "true";
  const visible = venues.filter(
    (v) =>
      v.source !== "aggregator" ||
      longTail ||
      watchedVenueSlugs.has(v.slug) ||
      selected.has(v.slug),
  );
  const matches = visible.filter(
    (v) => !needle || v.name.toLowerCase().includes(needle),
  );
  const groups = new Map<string, VenueOption[]>();
  for (const v of matches) {
    const region =
      v.source === "aggregator" ? "Long tail" : (v.region ?? "Other");
    (groups.get(region) ?? groups.set(region, []).get(region)!).push(v);
  }
  const orderedRegions = [
    ...REGION_ORDER.filter((r) => groups.has(r)),
    ...[...groups.keys()].filter((r) => !REGION_ORDER.includes(r)),
  ];
  const sortGroup = (list: VenueOption[]) =>
    [...list].sort((a, b) => {
      const aw = watchedVenueSlugs.has(a.slug) ? 0 : 1;
      const bw = watchedVenueSlugs.has(b.slug) ? 0 : 1;
      return aw - bw || a.name.localeCompare(b.name);
    });

  return (
    <div className="flex flex-col gap-2">
      {selected.size > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          {[...selected].sort().map((slug) => (
            <button
              key={slug}
              type="button"
              onClick={() => toggle(slug)}
              aria-label={`Remove venue ${bySlug.get(slug)?.name ?? slug}`}
              className="rounded-full border border-teal-700 bg-teal-700 px-2.5 py-0.5 text-xs text-white transition-colors hover:bg-teal-800 dark:border-teal-500 dark:bg-teal-500 dark:text-zinc-950"
            >
              {bySlug.get(slug)?.name ?? slug} ×
            </button>
          ))}
          <button
            type="button"
            onClick={() => setSelection(new Set())}
            className="text-xs text-teal-700 underline decoration-teal-700/40 underline-offset-2 dark:text-teal-400"
          >
            clear
          </button>
        </div>
      )}

      <input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Filter venues…"
        aria-label="Filter venues"
        className={`${inputClass} max-w-xs`}
      />

      {orderedRegions.map((region) => (
        <div key={region}>
          <p className="mt-1 text-[11px] font-semibold uppercase tracking-wide text-zinc-400 dark:text-zinc-500">
            {region}
          </p>
          <div className="mt-1 grid grid-cols-1 gap-x-4 gap-y-1 sm:grid-cols-2 md:grid-cols-3">
            {sortGroup(groups.get(region)!).map((v) => (
              <span
                key={v.slug}
                className="flex min-w-0 items-center text-sm text-zinc-700 dark:text-zinc-300"
              >
                <button
                  type="button"
                  onClick={() => toggle(v.slug)}
                  aria-pressed={selected.has(v.slug)}
                  className={`min-w-0 truncate text-left transition-colors hover:text-teal-700 dark:hover:text-teal-300 ${
                    selected.has(v.slug)
                      ? "font-medium text-teal-700 dark:text-teal-400"
                      : ""
                  }`}
                  title={v.name}
                >
                  {v.name}
                </button>
                {showPins && (
                  <span className="shrink-0">
                    <PinVenueButton
                      venueSlug={v.slug}
                      initiallyOn={watchedVenueSlugs.has(v.slug)}
                    />
                  </span>
                )}
              </span>
            ))}
          </div>
        </div>
      ))}
      {matches.length === 0 && (
        <p className="text-xs text-zinc-400 dark:text-zinc-600">
          No venues match “{query}”.
        </p>
      )}
    </div>
  );
}
