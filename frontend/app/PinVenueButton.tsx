"use client";

// Venue pin/unpin toggle (Phase 9 venue watchlist). Optimistic, like the
// performer +/✓ button; other surfaces catch up on the next navigation.

import { useState } from "react";

import { API_BASE } from "./lib/api";

export default function PinVenueButton({
  venueSlug,
  initiallyOn,
}: {
  venueSlug: string;
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
      const res = wasOn
        ? await fetch(`${API_BASE}/api/venues/watchlist/${venueSlug}`, {
            method: "DELETE",
          })
        : await fetch(`${API_BASE}/api/venues/watchlist`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ venue_slug: venueSlug }),
          });
      if (!res.ok) setOn(wasOn); // revert
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
      aria-pressed={on}
      aria-label={on ? "Unfollow venue" : "Follow venue"}
      title={on ? "Following this venue" : "Follow this venue"}
      className={`ml-1 align-middle text-sm leading-none transition-colors disabled:opacity-50 ${
        on
          ? "text-teal-600 dark:text-teal-400"
          : "text-zinc-300 hover:text-teal-600 dark:text-zinc-600 dark:hover:text-teal-400"
      }`}
    >
      {on ? "★" : "☆"}
    </button>
  );
}
