"use client";

// The watchlist management panel, shown on / while the watchlist filter is
// active. Removing an entry DELETEs it then router.refresh()es so the server
// re-fetches the (now narrower) matches and this list.
//
// This was a flat row of chips, which stopped working somewhere past ~20
// entries: at 55 it was a wall of names between the filters and the shows you
// came to look at. It now follows the shape VenuePicker uses for the same
// problem — collapsed behind a summary carrying the count, with a filter box
// and a compact multi-column list once opened. Alphabetical rather than
// newest-first, because at this size the list is something you *search*, not
// something you read.

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { API_BASE, type WatchlistEntry } from "./lib/api";
import { inputClass } from "./lib/ui";

export default function WatchlistPanel({
  entries,
}: {
  entries: WatchlistEntry[];
}) {
  const router = useRouter();
  const [removing, setRemoving] = useState<string | null>(null);
  const [query, setQuery] = useState("");

  const sorted = useMemo(
    () =>
      [...entries].sort((a, b) =>
        a.display_name.localeCompare(b.display_name, undefined, {
          sensitivity: "base",
        }),
      ),
    [entries],
  );

  const needle = query.trim().toLowerCase();
  const matches = needle
    ? sorted.filter((e) => e.display_name.toLowerCase().includes(needle))
    : sorted;

  async function remove(canonicalName: string) {
    setRemoving(canonicalName);
    try {
      await fetch(
        `${API_BASE}/api/watchlist/${encodeURIComponent(canonicalName)}`,
        { method: "DELETE" },
      );
      router.refresh();
    } finally {
      setRemoving(null);
    }
  }

  return (
    <details className="mb-6 group">
      <summary className="cursor-pointer select-none text-sm font-semibold uppercase tracking-wide text-zinc-500 marker:text-zinc-400 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200">
        Your watchlist{" "}
        <span className="font-normal normal-case tracking-normal text-zinc-400 dark:text-zinc-500">
          · {entries.length}
        </span>
      </summary>

      <div className="mt-2 flex flex-col gap-2">
        {/* The filter box only earns its space once scanning is the slow part. */}
        {entries.length > 12 && (
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Filter watchlist…"
            aria-label="Filter watchlist"
            className={`${inputClass} max-w-xs`}
          />
        )}

        {matches.length === 0 ? (
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            No followed performers match “{query.trim()}”.
          </p>
        ) : (
          <ul className="grid grid-cols-1 gap-x-4 gap-y-1 sm:grid-cols-2 md:grid-cols-3">
            {matches.map((entry) => (
              <li
                key={entry.canonical_name}
                className="flex min-w-0 items-center text-sm text-zinc-700 dark:text-zinc-300"
              >
                <span className="min-w-0 truncate" title={entry.display_name}>
                  {entry.display_name}
                </span>
                <button
                  type="button"
                  onClick={() => remove(entry.canonical_name)}
                  disabled={removing === entry.canonical_name}
                  aria-label={`Remove ${entry.display_name} from watchlist`}
                  className="ml-1.5 inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-zinc-400 hover:bg-zinc-200 hover:text-zinc-700 disabled:opacity-40 dark:hover:bg-zinc-700 dark:hover:text-zinc-200"
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </details>
  );
}
