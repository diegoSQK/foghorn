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

type Status =
  | { kind: "added"; name: string }
  | { kind: "duplicate"; name: string }
  | { kind: "covered"; name: string; by: string }
  | { kind: "error"; message: string };

export default function AddWatchlistForm() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<Status | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const displayName = name.trim();
    if (busy || !displayName) return;
    setBusy(true);
    setStatus(null);
    try {
      const res = await fetch(`${API_BASE}/api/watchlist`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ display_name: displayName }),
      });
      if (!res.ok) throw new Error(`request failed (${res.status})`);
      const body = (await res.json()) as {
        display_name: string;
        created: boolean;
        already_covered_by: string | null;
      };
      // The add is idempotent, so "followed" and "already following" both
      // return 200 — say which, rather than clearing the box either way and
      // leaving it ambiguous.
      if (!body.created) {
        setStatus({ kind: "duplicate", name: body.display_name });
        // Keep the text so it's obvious what was just judged a duplicate.
      } else {
        setStatus(
          body.already_covered_by
            ? {
                kind: "covered",
                name: body.display_name,
                by: body.already_covered_by,
              }
            : { kind: "added", name: body.display_name },
        );
        setName("");
      }
      router.refresh();
    } catch (err) {
      setStatus({
        kind: "error",
        message: err instanceof Error ? err.message : "something went wrong",
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="mb-4 flex flex-col gap-1.5">
      <div className="flex flex-wrap items-center gap-2">
        <input
          value={name}
          onChange={(e) => {
            setName(e.target.value);
            setStatus(null); // typing again clears the last verdict
          }}
          placeholder="Follow a performer by name…"
          aria-label="Follow a performer by name"
          className={`${inputClass} min-w-56 grow sm:grow-0`}
        />
        <button
          type="submit"
          disabled={busy || !name.trim()}
          className={buttonClass}
        >
          Follow
        </button>
        <span className="text-xs text-zinc-500 dark:text-zinc-400">
          matches any bill containing the name
        </span>
      </div>
      {status && (
        // aria-live so the verdict reaches screen readers; the input keeps
        // focus, so a silent DOM change would otherwise go unannounced.
        <p
          aria-live="polite"
          className={`text-xs ${
            status.kind === "error"
              ? "text-red-600 dark:text-red-400"
              : status.kind === "added"
                ? "text-green-700 dark:text-green-400"
                : "text-amber-700 dark:text-amber-400"
          }`}
        >
          {status.kind === "added" && `Now following ${status.name}.`}
          {status.kind === "duplicate" &&
            `${status.name} is already on your watchlist.`}
          {status.kind === "covered" &&
            `Added ${status.name} — but “${status.by}” already matched it, ` +
              `so this follows nothing new.`}
          {status.kind === "error" && status.message}
        </p>
      )}
    </form>
  );
}
