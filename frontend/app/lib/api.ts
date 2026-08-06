// Shared API base, fetch helper, and response types used by the server
// components (/, /watchlist, layout) and inlined by client components.

// API_BASE is prepended to every /api/* path. Its value depends on where the
// fetch runs, because the two contexts have different constraints:
//
//   • Browser (client components POSTing to the API): an EMPTY base, i.e. a
//     relative URL. The request then goes to whatever host served the page —
//     the laptop directly, or the laptop over Tailscale from a phone — and the
//     next.config.ts rewrite proxies /api/* to the backend server-side. An
//     absolute "http://localhost:…" base would resolve to the *device's* own
//     localhost, so remote access could never work (and the backend binds
//     127.0.0.1 only).
//
//   • Server (async server components rendering the initial page): a relative
//     URL has no origin to resolve against, so we need an absolute base. These
//     fetches run on the Next server (the laptop), so they hit the backend
//     directly at BACKEND_URL — default 127.0.0.1:8100 (foghorn's port; 8000
//     is ficycle's on this machine, so it must never be the default).
//
// NEXT_PUBLIC_API_BASE_URL stays as an explicit override for both contexts
// (the e2e suite points it, or BACKEND_URL, at its mock backend).
export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  (typeof window === "undefined"
    ? process.env.BACKEND_URL ?? "http://127.0.0.1:8100"
    : "");

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
  // Stated end ("HH:MM"), when the source publishes one; earlier than
  // start = past midnight. Null = not stated (UI estimates).
  end_local_time: string | null;
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

// The signed-in user (GET /api/auth/me). Null in callers = anonymous.
export type MeView = {
  id: number;
  display_name: string;
  email: string | null;
  is_admin: boolean;
};

// A user row as the admin management surface sees it (GET /api/auth/users).
export type UserAdminView = {
  id: number;
  display_name: string;
  email: string | null;
  is_admin: boolean;
  disabled: boolean;
  created_at: string;
  claimed_at: string | null;
  // Path form ("/join/<token>") — prefix with the serving origin to share.
  invite_path: string;
};

// Server-side fetch (no-store so filters/watchlist always reflect current
// state). Returns null on any failure so callers can render a fallback.
// Server components fetch the backend directly (bypassing the browser), so
// per-user endpoints need the incoming request's session cookie forwarded
// via `init.headers` — see lib/serverAuth.ts.
export async function getJSON<T>(
  path: string,
  init?: RequestInit,
): Promise<T | null> {
  try {
    const res = await fetch(`${API_BASE}${path}`, { cache: "no-store", ...init });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}
