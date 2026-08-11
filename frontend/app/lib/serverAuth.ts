// Server-only auth helpers (multi-user, August 2026).
//
// Server components fetch the backend directly (see lib/api.ts), so the
// browser's session cookie never rides along automatically — these helpers
// read it from the incoming request and produce headers to forward. Client
// components don't need any of this: their fetches are same-origin (the
// /api rewrite), so the browser attaches the cookie itself.

import { cookies } from "next/headers";

import { getJSON, type MeView } from "./api";

const SESSION_COOKIE = "foghorn_session";

/** Headers forwarding the caller's session cookie; undefined when anonymous. */
export async function sessionHeaders(): Promise<HeadersInit | undefined> {
  const store = await cookies();
  const token = store.get(SESSION_COOKIE)?.value;
  return token ? { cookie: `${SESSION_COOKIE}=${token}` } : undefined;
}

/**
 * The signed-in user for this request, or null when anonymous.
 *
 * Always asks the backend, even with no cookie to forward: under
 * FOGHORN_SINGLE_USER the backend resolves a cookie-less call to the
 * bootstrap admin (see backend/README.md → Auth). Short-circuiting here on a
 * missing cookie would hide that mode from the whole UI. Anonymous requests
 * in normal mode still land as null — /api/auth/me 401s and getJSON maps a
 * non-OK response to null.
 */
export async function getMe(): Promise<MeView | null> {
  return getJSON<MeView>("/api/auth/me", { headers: await sessionHeaders() });
}
