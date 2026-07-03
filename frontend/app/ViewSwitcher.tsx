"use client";

// List / Day / Week / Month view chips (?view=). Same URL-as-state pattern as
// the filter chips; every other filter carries across view switches. List is
// the default (no param). Switching into a calendar view drops the list's
// explicit from/to — the view derives its own window from ?anchor=.

import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { chipClass } from "./lib/ui";

const VIEWS = [
  { value: "list", label: "List" },
  { value: "day", label: "Day" },
  { value: "week", label: "Week" },
  { value: "month", label: "Month" },
] as const;

export default function ViewSwitcher() {
  const router = useRouter();
  const params = useSearchParams();
  const pathname = usePathname();

  const raw = params.get("view");
  const active = raw === "day" || raw === "week" || raw === "month" ? raw : "list";

  function selectView(view: string): void {
    const next = new URLSearchParams(params.toString());
    if (view === "list") {
      next.delete("view");
      next.delete("anchor");
    } else {
      next.set("view", view);
      next.delete("from");
      next.delete("to");
    }
    const query = next.toString();
    router.push(query ? `${pathname}?${query}` : pathname);
  }

  return (
    <div className="mb-4 flex flex-wrap gap-2">
      {VIEWS.map(({ value, label }) => (
        <button
          key={value}
          type="button"
          aria-pressed={active === value}
          onClick={() => selectView(value)}
          className={chipClass(active === value)}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
