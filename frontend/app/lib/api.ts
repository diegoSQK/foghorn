// Shared API base, fetch helper, and response types used by the server
// components (/, /watchlist, layout) and inlined by client components.

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export type PerformerView = {
  display: string;
  canonical: string;
  // Local/touring tag (heuristic or hand-set); null = unknown.
  origin: "local" | "touring" | null;
};

export type ShowView = {
  id: number;
  source: "scrape" | "manual";
  event_type: "show" | "jam";
  // Resolved genre: per-show override if the source published one, else the
  // venue's default lean.
  genre: string | null;
  venue: {
    slug: string;
    name: string;
    neighborhood: string | null;
    region: string | null;
    genre: string | null;
  };
  start_local_date: string;
  start_local_time: string;
  doors_local_time: string | null;
  headliner: PerformerView;
  support: PerformerView[];
  ticket_url: string | null;
  price_text: string | null;
  source_url: string;
};

export type VenueOption = {
  slug: string;
  name: string;
  neighborhood: string | null;
  region: string | null;
  genre: string | null;
};

export type WatchlistEntry = {
  canonical_name: string;
  display_name: string;
  added_at: string;
  notes: string | null;
};

// Server-side fetch (no-store so filters/watchlist always reflect current
// state). Returns null on any failure so callers can render a fallback.
export async function getJSON<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}
