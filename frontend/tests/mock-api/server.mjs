// Tiny mock of the foghorn backend for Playwright e2e tests.
//
// Why a real process and not Playwright's page.route()? app/page.tsx is an
// async *server* component — it fetches /api/shows and /api/venues from the
// Next server process, not the browser. page.route() only intercepts browser
// requests, so it can't see those server-side fetches. Instead we run this
// process and point the app at it via NEXT_PUBLIC_API_BASE_URL (set in
// playwright.config.ts's webServer env). It returns static fixture JSON — the
// specs assert URL/UI state on interaction, not backend filtering (that's
// covered by the backend pytest suite).

import { createServer } from "node:http";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const fixtures = join(here, "..", "fixtures");

const routes = {
  "/api/shows": readFileSync(join(fixtures, "shows.json"), "utf8"),
  "/api/venues": readFileSync(join(fixtures, "venues.json"), "utf8"),
};

const port = Number(process.env.MOCK_API_PORT ?? 4010);

createServer((req, res) => {
  const path = (req.url ?? "").split("?")[0];
  const body = routes[path];
  if (body === undefined) {
    res.writeHead(404, { "content-type": "application/json" });
    res.end(JSON.stringify({ error: "not_found" }));
    return;
  }
  res.writeHead(200, { "content-type": "application/json" });
  res.end(body);
}).listen(port, () => {
  // eslint-disable-next-line no-console
  console.log(`mock-api listening on http://localhost:${port}`);
});
