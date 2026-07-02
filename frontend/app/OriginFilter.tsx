"use client";

// Local/touring filter chips (performer-origin tagging v1). Same URL-as-state
// pattern as the region/genre chips. Origin tags are inferred (heuristic) or
// hand-set and cover only part of the catalog, so the labels say "acts" and
// the parent only renders this when tagged performers actually exist in the
// current result set (or the filter is already active) — no dead chips on an
// untagged DB.

import { usePathname, useRouter, useSearchParams } from "next/navigation";

const OPTIONS = [
  { value: "local", label: "Local acts" },
  { value: "touring", label: "Touring" },
] as const;

function chipClass(active: boolean): string {
  return `rounded-full border px-3 py-1 text-sm transition-colors ${
    active
      ? "border-zinc-900 bg-zinc-900 text-white dark:border-zinc-100 dark:bg-zinc-100 dark:text-zinc-900"
      : "border-zinc-300 text-zinc-700 hover:border-zinc-500 dark:border-zinc-700 dark:text-zinc-300"
  }`;
}

export default function OriginFilter() {
  const router = useRouter();
  const params = useSearchParams();
  const pathname = usePathname();

  const active = params.get("origin");

  function selectOrigin(origin: string): void {
    const next = new URLSearchParams(params.toString());
    if (active === origin) next.delete("origin");
    else next.set("origin", origin);
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
            aria-pressed={active === value}
            onClick={() => selectOrigin(value)}
            className={chipClass(active === value)}
          >
            {label}
          </button>
        ))}
      </div>
    </fieldset>
  );
}
