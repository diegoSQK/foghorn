"use client";

// Free-text watchlist add. Venues bill acts however they like ("Larry Ochs,
// Ben Davis, Darren Johnston, Lisa Mezzacappa - Subconscious Life"), and the
// '+' buttons can only add that verbatim string — which then matches only
// that exact billing. Adding a bare name here ("Lisa Mezzacappa") tracks the
// person across every billing shape, because watchlist matching only
// requires the entry's tokens to appear in a bill.

import { useRouter } from "next/navigation";
import { useState } from "react";

import { API_BASE } from "./lib/api";
import { buttonClass, inputClass } from "./lib/ui";

export default function AddWatchlistForm() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const displayName = name.trim();
    if (busy || !displayName) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/watchlist`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ display_name: displayName }),
      });
      if (!res.ok) throw new Error(`request failed (${res.status})`);
      setName("");
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "something went wrong");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="mb-4 flex flex-wrap items-center gap-2">
      <input
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="Follow a performer by name…"
        aria-label="Follow a performer by name"
        className={`${inputClass} min-w-56 grow sm:grow-0`}
      />
      <button type="submit" disabled={busy || !name.trim()} className={buttonClass}>
        Follow
      </button>
      <span className="text-xs text-zinc-500 dark:text-zinc-400">
        matches any bill containing the name
      </span>
      {error && (
        <span className="text-xs text-red-600 dark:text-red-400">{error}</span>
      )}
    </form>
  );
}
