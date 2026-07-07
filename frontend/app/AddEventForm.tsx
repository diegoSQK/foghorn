"use client";

// Manual event entry form (POST /api/events). The venue field is free text
// over a datalist of tracked venues: a name that matches a known venue books
// the show there; anything else creates a new manual venue, and the region
// select appears so the new venue lands in the right filter bucket.

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { API_BASE, type VenueOption } from "./lib/api";
import { buttonClass, inputClass } from "./lib/ui";

const REGIONS = ["SF", "East Bay", "North Bay", "Peninsula", "South Bay"] as const;

const labelClass =
  "flex flex-col gap-1 text-xs text-zinc-500 dark:text-zinc-400";

export default function AddEventForm({ venues }: { venues: VenueOption[] }) {
  const router = useRouter();
  const [venueName, setVenueName] = useState("");
  const [region, setRegion] = useState("");
  const [headliner, setHeadliner] = useState("");
  const [support, setSupport] = useState("");
  const [date, setDate] = useState("");
  const [time, setTime] = useState("20:00");
  const [price, setPrice] = useState("");
  const [link, setLink] = useState("");
  const [genre, setGenre] = useState("");
  const [isJam, setIsJam] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const known = useMemo(() => {
    const byName = new Map(venues.map((v) => [v.name.toLowerCase(), v]));
    return byName.get(venueName.trim().toLowerCase()) ?? null;
  }, [venues, venueName]);

  const isNewVenue = venueName.trim().length > 0 && known === null;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    setError(null);
    setBusy(true);
    try {
      const body: Record<string, unknown> = {
        headliner: headliner.trim(),
        support: support
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
        date,
        time,
        price_text: price.trim() || null,
        source_url: link.trim() || null,
        event_type: isJam ? "jam" : "show",
        genre: genre.trim() || null,
      };
      if (known !== null) body.venue_slug = known.slug;
      else
        body.venue = {
          name: venueName.trim(),
          region: region || null,
        };
      const res = await fetch(`${API_BASE}/api/events`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => null);
        throw new Error(
          typeof detail?.detail === "string"
            ? detail.detail
            : `request failed (${res.status})`,
        );
      }
      // Land on the calendar at the event's date so the new entry is visible.
      router.push(`/?from=${date}&to=${date}`);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "something went wrong");
      setBusy(false);
    }
  }

  return (
    <form
      onSubmit={submit}
      className="flex flex-col gap-4 rounded-lg border border-zinc-200 p-4 dark:border-zinc-800"
    >
      <label className={labelClass}>
        Venue
        <input
          list="venue-names"
          value={venueName}
          onChange={(e) => setVenueName(e.target.value)}
          placeholder="Pick a tracked venue or type a new one"
          required
          className={inputClass}
        />
        <datalist id="venue-names">
          {venues.map((v) => (
            <option key={v.slug} value={v.name} />
          ))}
        </datalist>
        {isNewVenue && (
          <span className="text-amber-600 dark:text-amber-400">
            New venue — foghorn will start tracking it (without a scraper).
          </span>
        )}
      </label>

      {isNewVenue && (
        <label className={labelClass}>
          Region (for the new venue)
          <select
            value={region}
            onChange={(e) => setRegion(e.target.value)}
            className={inputClass}
          >
            <option value="">Unknown</option>
            {REGIONS.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </label>
      )}

      <label className={labelClass}>
        Headliner
        <input
          value={headliner}
          onChange={(e) => setHeadliner(e.target.value)}
          required
          className={inputClass}
        />
      </label>

      <label className={labelClass}>
        Support acts (comma-separated, optional)
        <input
          value={support}
          onChange={(e) => setSupport(e.target.value)}
          className={inputClass}
        />
      </label>

      <div className="flex flex-wrap gap-3">
        <label className={labelClass}>
          Date
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            required
            className={inputClass}
          />
        </label>
        <label className={labelClass}>
          Start time
          <input
            type="time"
            value={time}
            onChange={(e) => setTime(e.target.value)}
            required
            className={inputClass}
          />
        </label>
      </div>

      <div className="flex flex-wrap gap-3">
        <label className={labelClass}>
          Price (optional)
          <input
            value={price}
            onChange={(e) => setPrice(e.target.value)}
            placeholder="$15"
            className={inputClass}
          />
        </label>
        <label className={labelClass}>
          Genre (optional)
          <input
            list="genre-names"
            value={genre}
            onChange={(e) => setGenre(e.target.value)}
            placeholder="jazz"
            className={inputClass}
          />
          <datalist id="genre-names">
            {[...new Set(venues.map((v) => v.genre).filter(Boolean))].map(
              (g) => (
                <option key={g} value={g ?? ""} />
              ),
            )}
          </datalist>
        </label>
        <label className={`${labelClass} grow`}>
          Event link (optional — flyer, IG post, artist site)
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

      {error && (
        <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
      )}

      <button
        type="submit"
        disabled={busy}
        className={`self-start ${buttonClass}`}
      >
        {busy ? "Adding…" : "Add event"}
      </button>
    </form>
  );
}
