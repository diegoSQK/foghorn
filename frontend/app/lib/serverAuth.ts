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

/** The signed-in user for this request, or null when anonymous. */
export async function getMe(): Promise<MeView | null> {
  const headers = await sessionHeaders();
  if (!headers) return null;
  return getJSON<MeView>("/api/auth/me", { headers });
}
