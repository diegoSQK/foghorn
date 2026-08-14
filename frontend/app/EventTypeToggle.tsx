"use client";

// Per-show event-type correction: the jam badge is clickable (unmark), and
// non-jam rows carry a faint "jam?" affordance (mark). Foghorn can only
// infer jams from titles ("Standards Hang" defeats it), so the user is the
// source of truth here. The PUT stores a permanent venue+billing override
// rule server-side — future instances of a recurring session inherit it.
// Optimistic flip, revert on failure, soft refresh so filters catch up.

import { useRouter } from "next/navigation";
import { useState } from "react";

import { API_BASE } from "./lib/api";

export default function EventTypeToggle({
  showId,
  initialType,
  interactive = true,
}: {
  showId: number;
  initialType: "show" | "jam" | "comedy";
  // Corrections are admin-only since multi-user (August 2026); everyone else
  // gets a static jam badge (and no "jam?" affordance on regular shows).
  interactive?: boolean;
}) {
  const router = useRouter();
  const [type, setType] = useState(initialType);
  const [busy, setBusy] = useState(false);

  // Comedy is a source classification, not a judgement call, so it renders as
  // a plain badge with no correction affordance — and crucially no "jam?"
  // prompt, which would be nonsense on a stand-up booking.
  if (type === "comedy") {
    return (
      <span className="ml-1 rounded-full border border-violet-300 px-1.5 py-px align-middle text-[10px] font-medium uppercase tracking-wide text-violet-700 dark:border-violet-800 dark:text-violet-400">
        comedy
      </span>
    );
  }

  if (!interactive) {
    return type === "jam" ? (
      <span className="ml-1 rounded-full border border-amber-300 px-1.5 py-px align-middle text-[10px] font-medium uppercase tracking-wide text-amber-700 dark:border-amber-800 dark:text-amber-400">
        jam
      </span>
    ) : null;
  }

  async function toggle() {
    if (busy) return;
    setBusy(true);
    const next = type === "jam" ? "show" : "jam";
    setType(next); // optimistic
    try {
      const res = await fetch(`${API_BASE}/api/shows/${showId}/event_type`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ event_type: next }),
      });
      if (!res.ok) setType(type); // revert
      else router.refresh();
    } catch {
      setType(type);
    } finally {
      setBusy(false);
    }
  }

  return type === "jam" ? (
    <button
      type="button"
      onClick={toggle}
      disabled={busy}
      title="Jam session — click if this is actually a regular show"
      aria-label="Unmark jam session"
      className="ml-1 rounded-full border border-amber-300 px-1.5 py-px align-middle text-[10px] font-medium uppercase tracking-wide text-amber-700 transition-colors hover:border-amber-500 disabled:opacity-50 dark:border-amber-800 dark:text-amber-400 dark:hover:border-amber-600"
    >
      jam
    </button>
  ) : (
    <button
      type="button"
      onClick={toggle}
      disabled={busy}
      title="Mark as jam session (applies to repeats of this billing here)"
      aria-label="Mark as jam session"
      className="ml-1 rounded-full border border-dashed border-zinc-300 px-1.5 py-px align-middle text-[10px] font-medium uppercase tracking-wide text-zinc-400 opacity-50 transition-all hover:border-amber-400 hover:text-amber-700 hover:opacity-100 disabled:opacity-30 dark:border-zinc-700 dark:text-zinc-500 dark:hover:border-amber-600 dark:hover:text-amber-400"
    >
      jam?
    </button>
  );
}
