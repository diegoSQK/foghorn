"use client";

// One review-queue card: the parser's draft as editable fields (same venue
// datalist behavior as AddEventForm), the raw email collapsed underneath, a
// duplicate warning when the artist already has a show at that venue+date,
// and Approve / Reject. Approving posts the edited fields as overrides —
// the backend merges them over the stored draft and creates a manual event.

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { API_BASE, type PendingEventView, type VenueOption } from "../lib/api";
import { buttonClass, inputClass } from "../lib/ui";

const labelClass =
  "flex flex-col gap-1 text-xs text-zinc-500 dark:text-zinc-400";

export default function InboxCard({
  row,
  venues,
}: {
  row: PendingEventView;
  venues: VenueOption[];
}) {
  const router = useRouter();
  const knownName =
    venues.find((v) => v.slug === row.venue_slug)?.name ??
    row.venue_name_guess ??
    "";
  const [venueName, setVenueName] = useState(knownName);
  const [headliner, setHeadliner] = useState(row.artist_display ?? "");
  const [date, setDate] = useState(row.date_guess ?? "");
  const [time, setTime] = useState(row.time_guess ?? "");
  const [genre, setGenre] = useState("");
  const [link, setLink] = useState("");
  const [isJam, setIsJam] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const known = useMemo(() => {
    const byName = new Map(venues.map((v) => [v.name.toLowerCase(), v]));
    return byName.get(venueName.trim().toLowerCase()) ?? null;
  }, [venues, venueName]);

  const isNewVenue = venueName.trim().length > 0 && known === null;

  async function post(path: string, body?: Record<string, unknown>) {
    if (busy) return;
    setError(null);
    setBusy(true);
    try {
      const res = await fetch(`${API_BASE}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => null);
        throw new Error(
          typeof detail?.detail === "string"
            ? detail.detail
            : `request failed (${res.status})`,
        );
      }
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "something went wrong");
      setBusy(false);
    }
  }

  function approve() {
    const body: Record<string, unknown> = {
      headliner: headliner.trim() || null,
      date: date || null,
      time: time || null,
      event_type: isJam ? "jam" : "show",
      genre: genre.trim() || null,
      source_url: link.trim() || null,
    };
    if (known !== null) body.venue_slug = known.slug;
    else if (venueName.trim()) body.venue = { name: venueName.trim() };
    void post(`/api/inbox/${row.id}/approve`, body);
  }

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-zinc-200 p-4 dark:border-zinc-800">
      <div className="text-xs text-zinc-500 dark:text-zinc-400">
        <span className="font-medium text-zinc-700 dark:text-zinc-300">
          {row.subject || "(no subject)"}
        </span>{" "}
        — {row.from_addr || "unknown sender"} ·{" "}
        {row.received_at.slice(0, 10)}
      </div>

      {row.possible_duplicates.length > 0 && (
        <div className="rounded-md border border-amber-300 bg-amber-50 p-2 text-xs text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200">
          Possible duplicate — already on the calendar that night:
          <ul className="mt-1 list-inside list-disc">
            {row.possible_duplicates.map((d) => (
              <li key={d.show_id}>
                {d.headliner} · {d.start_local_date} {d.start_local_time} (
                {d.source === "scrape" ? "scraped" : "manual"})
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex flex-wrap gap-3">
        <label className={`${labelClass} grow`}>
          Headliner
          <input
            value={headliner}
            onChange={(e) => setHeadliner(e.target.value)}
            placeholder="who's playing"
            className={inputClass}
          />
        </label>
        <label className={`${labelClass} grow`}>
          Venue
          <input
            list={`inbox-venues-${row.id}`}
            value={venueName}
            onChange={(e) => setVenueName(e.target.value)}
            placeholder="tracked venue or a new one"
            className={inputClass}
          />
          <datalist id={`inbox-venues-${row.id}`}>
            {venues.map((v) => (
              <option key={v.slug} value={v.name} />
            ))}
          </datalist>
          {isNewVenue && (
            <span className="text-amber-600 dark:text-amber-400">
              New venue — will be created on approve.
            </span>
          )}
        </label>
      </div>

      <div className="flex flex-wrap gap-3">
        <label className={labelClass}>
          Date
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className={inputClass}
          />
        </label>
        <label className={labelClass}>
          Time
          <input
            type="time"
            value={time}
            onChange={(e) => setTime(e.target.value)}
            className={inputClass}
          />
        </label>
        <label className={labelClass}>
          Genre (optional)
          <input
            value={genre}
            onChange={(e) => setGenre(e.target.value)}
            placeholder="jazz"
            className={inputClass}
          />
        </label>
        <label className={`${labelClass} grow`}>
          Link (optional — tickets, flyer)
          <input
            type="url"
            value={link}
            onChange={(e) => setLink(e.target.value)}
            className={inputClass}
          />
        </label>
      </div>

      <label className="flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
        <input
          type="checkbox"
          checked={isJam}
          onChange={(e) => setIsJam(e.target.checked)}
          className="h-4 w-4"
        />
        This is a jam session
      </label>

      <details className="text-xs text-zinc-500 dark:text-zinc-400">
        <summary className="cursor-pointer select-none">Raw email</summary>
        <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap rounded-md bg-zinc-50 p-2 font-mono text-[11px] leading-snug dark:bg-zinc-900">
          {row.raw_text}
        </pre>
      </details>

      {error && (
        <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
      )}

      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={approve}
          disabled={busy}
          className={buttonClass}
        >
          {busy ? "Working…" : "Approve"}
        </button>
        <button
          type="button"
          onClick={() => void post(`/api/inbox/${row.id}/reject`)}
          disabled={busy}
          className="rounded-full border border-zinc-300 px-4 py-1.5 text-sm text-zinc-600 transition-colors hover:border-red-400 hover:text-red-600 disabled:opacity-50 dark:border-zinc-700 dark:text-zinc-400 dark:hover:border-red-500 dark:hover:text-red-400"
        >
          Reject
        </button>
      </div>
    </div>
  );
}
