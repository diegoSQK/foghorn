"use client";

// Event-type filter chips: shows vs jam sessions (?type=). Same URL-as-state
// pattern as the region/genre/origin chips. Default (no chip active) is both.

import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { chipClass } from "./lib/ui";

const OPTIONS = [
  { value: "show", label: "Shows" },
  { value: "jam", label: "Jam sessions" },
] as const;

export default function TypeFilter() {
  const router = useRouter();
  const params = useSearchParams();
  const pathname = usePathname();

  const active = params.get("type");

  function selectType(value: string): void {
    const next = new URLSearchParams(params.toString());
    if (active === value) next.delete("type");
    else next.set("type", value);
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
            aria-pressed={active === value}
            onClick={() => selectType(value)}
            className={chipClass(active === value)}
          >
            {label}
          </button>
        ))}
      </div>
    </fieldset>
  );
}
