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
  // 'seed' | 'manual' | 'aggregator' — aggregator venues are quarantined
  // (hidden from pickers/chips unless the long-tail toggle or a pin
  // surfaces them).
  source: "seed" | "manual" | "aggregator";
};

export type WatchedVenueEntry = {
  venue_slug: string;
  name: string;
  added_at: string;
  notes: string | null;
};

export type DuplicateView = {
  show_id: number;
  headliner: string;
  venue_slug: string;
  start_local_date: string;
  start_local_time: string;
  source: "scrape" | "manual";
};

// A mailing-list email awaiting review (Phase 8). Draft fields are parser
// guesses — any may be null; raw_text always survives for the reviewer.
export type PendingEventView = {
  id: number;
  received_at: string;
  from_addr: string;
  subject: string;
  raw_text: string;
  artist_display: string | null;
  venue_slug: string | null;
  venue_name_guess: string | null;
  date_guess: string | null;
  time_guess: string | null;
  status: "pending" | "approved" | "rejected";
  possible_duplicates: DuplicateView[];
};

export type MailSenderEntry = {
  email: string;
  artist_display: string;
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
