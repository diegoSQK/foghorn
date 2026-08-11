"use client";

// Signed-in indicator + sign-out, right-aligned in the nav. Anonymous
// visitors see nothing here — browsing is public and sign-in happens only
// through an invite link (/join/<token>), so there's no "Sign in" route to
// offer. In single-user mode (FOGHORN_SINGLE_USER on the backend) the name
// shows without a sign-out button: there's no session to end, and the next
// request would resolve as the same admin anyway.

import { useRouter } from "next/navigation";
import { useState } from "react";

import { API_BASE, type MeView } from "./lib/api";

export default function UserMenu({ me }: { me: MeView | null }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  if (me === null) return null;

  async function signOut() {
    if (busy) return;
    setBusy(true);
    try {
      await fetch(`${API_BASE}/api/auth/logout`, { method: "POST" });
      router.push("/");
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <span className="ml-auto flex items-baseline gap-3">
      <span className="text-zinc-500 dark:text-zinc-400">{me.display_name}</span>
      {!me.single_user && (
        <button
          type="button"
          onClick={signOut}
          disabled={busy}
          className="text-zinc-400 hover:text-teal-700 dark:text-zinc-500 dark:hover:text-teal-300"
        >
          Sign out
        </button>
      )}
    </span>
  );
}
