"use client";

// "Your watchlist" chip row, shown on / while the watchlist filter is
// active. Removing a chip DELETEs the entry then router.refresh()es so the
// server re-fetches the (now narrower) matches and the chip row.

import { useRouter } from "next/navigation";
import { useState } from "react";

import { API_BASE, type WatchlistEntry } from "./lib/api";

export default function WatchlistChips({ entries }: { entries: WatchlistEntry[] }) {
  const router = useRouter();
  const [removing, setRemoving] = useState<string | null>(null);

  async function remove(canonicalName: string) {
    setRemoving(canonicalName);
    try {
      await fetch(`${API_BASE}/api/watchlist/${encodeURIComponent(canonicalName)}`, {
        method: "DELETE",
      });
      router.refresh();
    } finally {
      setRemoving(null);
    }
  }

  return (
    <section className="mb-6">
      <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
        Your watchlist
      </h2>
      <div className="flex flex-wrap gap-2">
        {entries.map((entry) => (
          <span
            key={entry.canonical_name}
            className="inline-flex items-center gap-1.5 rounded-full border border-zinc-300 py-1 pl-3 pr-1.5 text-sm text-zinc-700 dark:border-zinc-700 dark:text-zinc-300"
          >
            {entry.display_name}
            <button
              type="button"
              onClick={() => remove(entry.canonical_name)}
              disabled={removing === entry.canonical_name}
              aria-label={`Remove ${entry.display_name} from watchlist`}
              className="inline-flex h-4 w-4 items-center justify-center rounded-full text-zinc-400 hover:bg-zinc-200 hover:text-zinc-700 dark:hover:bg-zinc-700 dark:hover:text-zinc-200"
            >
              ×
            </button>
          </span>
        ))}
      </div>
    </section>
  );
}
