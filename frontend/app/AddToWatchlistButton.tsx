"use client";

// Per-performer add/remove toggle on a show card. Optimistic: flips +/✓
// immediately, reverts on failure. The nav count and other cards' state catch
// up on the next page navigation (the watchlist is re-fetched server-side then).

import { useState } from "react";

import { API_BASE } from "./lib/api";

export default function AddToWatchlistButton({
  displayName,
  canonicalName,
  initiallyOn,
}: {
  displayName: string;
  canonicalName: string;
  initiallyOn: boolean;
}) {
  const [on, setOn] = useState(initiallyOn);
  const [busy, setBusy] = useState(false);

  async function toggle() {
    if (busy) return;
    setBusy(true);
    const wasOn = on;
    setOn(!wasOn); // optimistic
    try {
      const ok = wasOn
        ? await removeEntry(canonicalName)
        : await addEntry(displayName);
      if (!ok) setOn(wasOn); // revert on failure
    } catch {
      setOn(wasOn);
    } finally {
      setBusy(false);
    }
  }

  return (
    <button
      type="button"
      onClick={toggle}
      disabled={busy}
      aria-label={
        on
          ? `Remove ${displayName} from watchlist`
          : `Add ${displayName} to watchlist`
      }
      title={on ? "On your watchlist — click to remove" : "Add to watchlist"}
      className={`ml-1.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full border align-middle text-xs leading-none transition-colors ${
        on
          ? "border-green-500 text-green-600 dark:text-green-400"
          : "border-zinc-300 text-zinc-400 hover:border-zinc-500 hover:text-zinc-700 dark:border-zinc-600 dark:hover:text-zinc-200"
      }`}
    >
      {on ? "✓" : "+"}
    </button>
  );
}

async function addEntry(displayName: string): Promise<boolean> {
  const res = await fetch(`${API_BASE}/api/watchlist`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ display_name: displayName }),
  });
  return res.ok;
}

async function removeEntry(canonicalName: string): Promise<boolean> {
  const res = await fetch(
    `${API_BASE}/api/watchlist/${encodeURIComponent(canonicalName)}`,
    { method: "DELETE" },
  );
  return res.ok || res.status === 404; // already gone is success for our purposes
}
