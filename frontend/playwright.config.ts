import { defineConfig, devices } from "@playwright/test";

// Two managed servers, started in parallel and waited on before tests run:
//   1. the mock backend (returns fixture JSON for /api/shows + /api/venues)
//   2. the Next app, built+started with BACKEND_URL pointed at (1)
//
// BACKEND_URL (not NEXT_PUBLIC_API_BASE_URL) is what production uses, so the
// suite exercises the real wiring: server components fetch it directly, and
// browser fetches go relative to the app, which the next.config.ts rewrite
// proxies to BACKEND_URL. The mock is therefore same-origin from the browser's
// view — the rewrite path itself is under test, not sidestepped via CORS.
//
// We run a built production app (`npm run build && npm run start`), not `dev`:
// it's what `next build` already validates in the gate, exercises the real
// server-component → fetch → render path, and avoids dev-only quirks. The app
// runs on 3200 — off both the default 3000 AND 3100 (a common second choice
// for a dev server when 3000 is taken): reuseExistingServer means any live
// server already on this port gets tested INSTEAD of the mock-backed build,
// so the port must be one nothing else uses.

const MOCK_API_PORT = 4010;
const APP_PORT = 3200;

export default defineConfig({
  testDir: "./tests",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: `http://localhost:${APP_PORT}`,
    trace: "on-first-retry",
    // Specs run "signed in": the app only consults /api/auth/me when a
    // session cookie is present (see app/lib/serverAuth.ts), so seed one.
    // The mock backend answers /api/auth/me the same way for any token.
    storageState: {
      cookies: [
        {
          name: "foghorn_session",
          value: "e2e-session",
          domain: "localhost",
          path: "/",
          expires: -1,
          httpOnly: true,
          secure: false,
          sameSite: "Lax" as const,
        },
      ],
      origins: [],
    },
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: "node tests/mock-api/server.mjs",
      port: MOCK_API_PORT,
      reuseExistingServer: !process.env.CI,
      env: { MOCK_API_PORT: String(MOCK_API_PORT) },
    },
    {
      command: "npm run build && npm run start",
      port: APP_PORT,
      timeout: 120_000,
      reuseExistingServer: !process.env.CI,
      env: {
        PORT: String(APP_PORT),
        BACKEND_URL: `http://localhost:${MOCK_API_PORT}`,
      },
    },
  ],
});
