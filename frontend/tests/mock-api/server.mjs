// Tiny mock of the foghorn backend for Playwright e2e tests.
//
// Why a real process and not Playwright's page.route()? app/page.tsx is an
// async *server* component — it fetches /api/shows and /api/venues from the
// Next server process, not the browser. page.route() only intercepts browser
// requests, so it can't see those server-side fetches. Instead we run this
// process and point the app at it via BACKEND_URL (set in
// playwright.config.ts's webServer env). It returns static fixture JSON — the
// specs assert URL/UI state on interaction, not backend filtering (that's
// covered by the backend pytest suite).
//
// The watchlist is the one stateful route: /watchlist's add form and chips
// POST/DELETE from the *browser*. Those go relative to the app (app on 3200),
// which the next.config.ts rewrite proxies to the mock (:4010); then
// router.refresh() re-fetches GET /api/watchlist server-side — so the mock
// keeps an in-memory list (seeded from fixtures/watchlist.json). Browser
// requests are same-origin via the rewrite, so the CORS headers below are now
// belt-and-suspenders (harmless if a spec ever hits the mock cross-origin).
//
// Auth is mocked the way the real backend behaves, because the frontend's
// signed-in/anonymous/single-user branches all hang off what /api/auth/me
// answers for a *cookie-less* request:
//
//   - normal mode, session cookie present → signed-in admin (what almost
//     every spec runs as; the cookie is seeded in playwright.config.ts)
//   - normal mode, no cookie              → 401 on every personal route
//   - single-user mode, no cookie         → the bootstrap admin, with
//     `single_user: true` (backend flag FOGHORN_SINGLE_USER=1)
//
// The last two are the same request, so they can't come from one instance:
// two are started on separate ports, each fronted by its own Next app (see
// playwright.config.ts).

import { createServer } from "node:http";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const fixtures = join(here, "..", "fixtures");

const SHOWS = readFileSync(join(fixtures, "shows.json"), "utf8");
const VENUES = readFileSync(join(fixtures, "venues.json"), "utf8");
const WATCHLIST_SEED = readFileSync(join(fixtures, "watchlist.json"), "utf8");

// Rough stand-in for the backend's canonicalize(): lowercase, alnum tokens.
function canonicalize(name) {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

const CORS_HEADERS = {
  "access-control-allow-origin": "*",
  "access-control-allow-methods": "GET,POST,DELETE,OPTIONS",
  "access-control-allow-headers": "content-type",
};

function hasSession(req) {
  return /(^|;\s*)foghorn_session=/.test(req.headers.cookie ?? "");
}

/** One mock backend. `singleUser` mirrors FOGHORN_SINGLE_USER=1. */
function createMockApi({ singleUser = false } = {}) {
  // Per-instance so the two backends don't share mutable state.
  const watchlist = JSON.parse(WATCHLIST_SEED);

  const me = JSON.stringify({
    id: 1,
    display_name: "Test User",
    email: null,
    is_admin: true,
    single_user: singleUser,
  });

  const publicRoutes = { "/api/shows": SHOWS, "/api/venues": VENUES };

  return createServer((req, res) => {
    const path = (req.url ?? "").split("?")[0];
    const send = (status, body) => {
      res.writeHead(status, {
        ...CORS_HEADERS,
        "content-type": "application/json",
      });
      res.end(body);
    };

    if (req.method === "OPTIONS") {
      res.writeHead(204, CORS_HEADERS);
      res.end();
      return;
    }

    const body = publicRoutes[path];
    if (body !== undefined) {
      send(200, body);
      return;
    }

    // Everything below is personal or admin data: a session resolves it, and
    // so does single-user mode with no session at all.
    const resolved = hasSession(req) || singleUser;
    if (!resolved) {
      send(401, JSON.stringify({ detail: "sign-in required" }));
      return;
    }

    if (path === "/api/auth/me") {
      send(200, me);
      return;
    }
    if (path === "/api/venues/watchlist") {
      send(200, "[]");
      return;
    }

    // Event-type correction (PUT/DELETE /api/shows/:id/event_type): accept
    // and echo — specs assert the optimistic UI, not server state.
    if (/^\/api\/shows\/\d+\/event_type$/.test(path)) {
      if (req.method === "PUT") {
        let raw = "";
        req.on("data", (chunk) => (raw += chunk));
        req.on("end", () => {
          const eventType = JSON.parse(raw || "{}").event_type ?? "show";
          send(
            200,
            JSON.stringify({
              show_id: 0,
              event_type: eventType,
              applies_to_billing: "",
            }),
          );
        });
        return;
      }
      if (req.method === "DELETE") {
        res.writeHead(204, CORS_HEADERS);
        res.end();
        return;
      }
    }

    if (path === "/api/watchlist" && req.method === "GET") {
      send(200, JSON.stringify(watchlist));
      return;
    }
    if (path === "/api/watchlist" && req.method === "POST") {
      let raw = "";
      req.on("data", (chunk) => (raw += chunk));
      req.on("end", () => {
        const displayName = (JSON.parse(raw || "{}").display_name ?? "").trim();
        const entry = {
          canonical_name: canonicalize(displayName),
          display_name: displayName,
          added_at: new Date().toISOString(),
          notes: null,
        };
        if (!watchlist.some((e) => e.canonical_name === entry.canonical_name)) {
          watchlist.push(entry);
        }
        send(200, JSON.stringify(entry));
      });
      return;
    }
    if (path.startsWith("/api/watchlist/") && req.method === "DELETE") {
      const canonical = decodeURIComponent(path.slice("/api/watchlist/".length));
      const index = watchlist.findIndex((e) => e.canonical_name === canonical);
      if (index !== -1) watchlist.splice(index, 1);
      send(200, "{}");
      return;
    }

    send(404, JSON.stringify({ error: "not_found" }));
  });
}

const port = Number(process.env.MOCK_API_PORT ?? 4010);
const singleUserPort = Number(process.env.MOCK_API_SINGLE_USER_PORT ?? 4011);

createMockApi().listen(port, () => {
  // eslint-disable-next-line no-console
  console.log(`mock-api listening on http://localhost:${port}`);
});
createMockApi({ singleUser: true }).listen(singleUserPort, () => {
  // eslint-disable-next-line no-console
  console.log(`mock-api (single-user) on http://localhost:${singleUserPort}`);
});
