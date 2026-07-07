"use client";

// Paste-an-email intake (POST /api/inbox/ingest): the queue is usable
// without any IMAP setup — copy a newsletter into the box and the parser
// drafts it like a polled message.

import { useRouter } from "next/navigation";
import { useState } from "react";

import { API_BASE } from "../lib/api";
import { buttonClass, inputClass } from "../lib/ui";

const labelClass =
  "flex flex-col gap-1 text-xs text-zinc-500 dark:text-zinc-400";

export default function PasteEmailForm() {
  const router = useRouter();
  const [from, setFrom] = useState("");
  const [subject, setSubject] = useState("");
  const [text, setText] = useState("");
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (busy || !text.trim()) return;
    setError(null);
    setBusy(true);
    try {
      const res = await fetch(`${API_BASE}/api/inbox/ingest`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          from_addr: from.trim(),
          subject: subject.trim(),
          text,
        }),
      });
      if (!res.ok) throw new Error(`request failed (${res.status})`);
      setFrom("");
      setSubject("");
      setText("");
      setOpen(false);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "something went wrong");
    } finally {
      setBusy(false);
    }
  }

  return (
    <details
      open={open}
      onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}
      className="mb-6 rounded-lg border border-zinc-200 p-4 dark:border-zinc-800"
    >
      <summary className="cursor-pointer select-none text-sm font-medium">
        Paste an email into the queue
      </summary>
      <form onSubmit={submit} className="mt-3 flex flex-col gap-3">
        <div className="flex flex-wrap gap-3">
          <label className={`${labelClass} grow`}>
            From (matches the sender map)
            <input
              value={from}
              onChange={(e) => setFrom(e.target.value)}
              placeholder="list@artist.example"
              className={inputClass}
            />
          </label>
          <label className={`${labelClass} grow`}>
            Subject
            <input
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              className={inputClass}
            />
          </label>
        </div>
        <label className={labelClass}>
          Email text
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={5}
            required
            placeholder="TONIGHT at the Make-Out Room, 8pm…"
            className={`${inputClass} font-mono text-xs`}
          />
        </label>
        {error && (
          <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
        )}
        <button
          type="submit"
          disabled={busy || !text.trim()}
          className={`self-start ${buttonClass}`}
        >
          {busy ? "Parsing…" : "Add to queue"}
        </button>
      </form>
    </details>
  );
}
