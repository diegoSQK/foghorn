"use client";

// The sender→artist map (mail_senders): which From: addresses foghorn
// recognizes, and which artist each one's emails announce. The parser
// prefills the headliner from this.

import { useRouter } from "next/navigation";
import { useState } from "react";

import { API_BASE, type MailSenderEntry } from "../lib/api";
import { buttonClass, inputClass } from "../lib/ui";

export default function SendersManager({
  senders,
}: {
  senders: MailSenderEntry[];
}) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [artist, setArtist] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    if (busy || !email.trim() || !artist.trim()) return;
    setError(null);
    setBusy(true);
    try {
      const res = await fetch(`${API_BASE}/api/inbox/senders`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: email.trim(),
          artist_display: artist.trim(),
        }),
      });
      if (!res.ok) throw new Error(`request failed (${res.status})`);
      setEmail("");
      setArtist("");
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "something went wrong");
    } finally {
      setBusy(false);
    }
  }

  async function remove(target: string) {
    if (busy) return;
    setBusy(true);
    try {
      const res = await fetch(
        `${API_BASE}/api/inbox/senders/${encodeURIComponent(target)}`,
        { method: "DELETE" },
      );
      if (res.ok) router.refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-800">
      <h2 className="text-sm font-medium">Known senders</h2>
      <p className="mb-3 text-xs text-zinc-500 dark:text-zinc-400">
        Emails from these addresses prefill the artist as the headliner.
      </p>

      {senders.length > 0 && (
        <ul className="mb-3 flex flex-col gap-1 text-sm">
          {senders.map((s) => (
            <li key={s.email} className="flex items-baseline gap-2">
              <span className="font-mono text-xs">{s.email}</span>
              <span className="text-zinc-500 dark:text-zinc-400">→</span>
              <span>{s.artist_display}</span>
              <button
                type="button"
                onClick={() => void remove(s.email)}
                disabled={busy}
                title="Forget this sender"
                className="ml-1 text-xs text-zinc-400 underline hover:text-red-600 hover:no-underline disabled:opacity-50 dark:text-zinc-500 dark:hover:text-red-400"
              >
                remove
              </button>
            </li>
          ))}
        </ul>
      )}

      <form onSubmit={add} className="flex flex-wrap items-center gap-2">
        <input
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="list@artist.example"
          aria-label="Sender email address"
          className={`${inputClass} min-w-48`}
        />
        <input
          value={artist}
          onChange={(e) => setArtist(e.target.value)}
          placeholder="Artist name"
          aria-label="Artist name"
          className={`${inputClass} min-w-40`}
        />
        <button
          type="submit"
          disabled={busy || !email.trim() || !artist.trim()}
          className={buttonClass}
        >
          Add sender
        </button>
        {error && (
          <span className="text-xs text-red-600 dark:text-red-400">
            {error}
          </span>
        )}
      </form>
    </section>
  );
}
