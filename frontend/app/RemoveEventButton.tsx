"use client";

// Delete affordance for manually-entered events only (the API refuses
// scraped rows — they'd come back on the next refresh anyway).

import { useRouter } from "next/navigation";
import { useState } from "react";

import { API_BASE } from "./lib/api";

export default function RemoveEventButton({ showId }: { showId: number }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  async function remove() {
    if (busy) return;
    setBusy(true);
    try {
      const res = await fetch(`${API_BASE}/api/events/${showId}`, {
        method: "DELETE",
      });
      if (res.ok) router.refresh();
      else setBusy(false);
    } catch {
      setBusy(false);
    }
  }

  return (
    <button
      type="button"
      onClick={remove}
      disabled={busy}
      title="Remove this manually-added event"
      className="ml-1 align-middle text-xs text-zinc-400 underline hover:text-red-600 hover:no-underline disabled:opacity-50 dark:text-zinc-500 dark:hover:text-red-400"
    >
      remove
    </button>
  );
}
