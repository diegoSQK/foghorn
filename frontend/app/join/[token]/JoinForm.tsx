"use client";

// The invite-claim form (multi-user, August 2026). The invite link is the
// credential: first open claims the account, later opens sign back in. The
// claim POST sets the session cookie (same-origin via the /api rewrite), so
// success is just navigate-home-and-refresh.

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { API_BASE, type MeView } from "../../lib/api";
import { inputClass } from "../../lib/ui";

type InviteInfo = { display_name: string; claimed: boolean };

export default function JoinForm({ token }: { token: string }) {
  const router = useRouter();
  const [info, setInfo] = useState<InviteInfo | null | "loading">("loading");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(
          `${API_BASE}/api/auth/invite/${encodeURIComponent(token)}`,
        );
        const body = res.ok ? ((await res.json()) as InviteInfo) : null;
        if (!cancelled) {
          setInfo(body);
          if (body) setName(body.display_name);
        }
      } catch {
        if (!cancelled) setInfo(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token]);

  async function join() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/auth/claim`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          token,
          display_name: name.trim() || undefined,
          email: email.trim() || undefined,
        }),
      });
      if (!res.ok) {
        setError("This invite link isn't valid anymore — ask for a fresh one.");
        return;
      }
      const me = (await res.json()) as MeView;
      router.push("/");
      router.refresh();
      void me;
    } catch {
      setError("Couldn't reach the server — try again in a moment.");
    } finally {
      setBusy(false);
    }
  }

  if (info === "loading") {
    return <p className="text-zinc-500 dark:text-zinc-400">Checking your invite…</p>;
  }
  if (info === null) {
    return (
      <p className="text-zinc-600 dark:text-zinc-300">
        This invite link isn&apos;t valid — it may have been regenerated. Ask
        whoever sent it for a fresh one.
      </p>
    );
  }

  return (
    <div className="flex max-w-sm flex-col gap-4">
      <p className="text-zinc-600 dark:text-zinc-300">
        {info.claimed
          ? `Welcome back, ${info.display_name} — this signs you in on this device.`
          : "You've been invited to foghorn — Bay Area jazz & music shows, with your own watchlist."}
      </p>
      {!info.claimed && (
        <>
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-zinc-500 dark:text-zinc-400">Your name</span>
            <input
              className={inputClass}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-zinc-500 dark:text-zinc-400">
              Email <span className="text-zinc-400 dark:text-zinc-500">(optional — for account recovery later)</span>
            </span>
            <input
              className={inputClass}
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </label>
        </>
      )}
      <button
        type="button"
        onClick={join}
        disabled={busy}
        className="rounded-lg bg-teal-700 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-teal-800 disabled:opacity-50 dark:bg-teal-600 dark:hover:bg-teal-500"
      >
        {info.claimed ? "Sign in" : "Join foghorn"}
      </button>
      {!info.claimed && (
        <p className="text-xs text-zinc-500 dark:text-zinc-400">
          Keep this link — it&apos;s also how you sign in on a new device.
        </p>
      )}
      {error && (
        <p className="text-sm text-amber-700 dark:text-amber-400">{error}</p>
      )}
    </div>
  );
}
