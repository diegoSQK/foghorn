import { defineConfig, devices } from "@playwright/test";

// Three managed servers, started in parallel and waited on before tests run:
//   1. the mock backend (returns fixture JSON for /api/shows + /api/venues);
//      one process, two ports — :4010 normal, :4011 single-user
//   2. the Next app with BACKEND_URL pointed at :4010
//   3. a second Next app on :3201 with BACKEND_URL pointed at :4011
//
// Why (3): "anonymous" and "single-user" are the *same* cookie-less request to
// /api/auth/me, distinguished only by the backend's FOGHORN_SINGLE_USER flag —
// so one app instance can't exercise both. auth-modes.spec.ts overrides
// baseURL to :3201 for the single-user half; every other spec runs on :3200.
//
// BACKEND_URL (not NEXT_PUBLIC_API_BASE_URL) is what production uses, so the
// suite exercises the real wiring: server components fetch it directly, and
// browser fetches go relative to the app, which the next.config.ts rewrite
// proxies to BACKEND_URL. The mock is therefore same-origin from the browser's
// view — the rewrite path itself is under test, not sidestepped via CORS.
//
// We run a built production app (`npm run build && npm run start`), not `dev`:
// it's what `next build` already validates in the gate, exercises the real
// server-component → fetch → render path, and avoids dev-only quirks. Each app
// builds under its own BACKEND_URL because the /api/* rewrite is baked in at
// build time. The apps run on 3200/3201 — off both the default 3000 AND 3100
// (a common second choice for a dev server when 3000 is taken):
// reuseExistingServer means any live server already on this port gets tested
// INSTEAD of the mock-backed build, so the ports must be ones nothing else uses.

const MOCK_API_PORT = 4010;
const MOCK_API_SINGLE_USER_PORT = 4011;
const APP_PORT = 3200;
const SINGLE_USER_APP_PORT = 3201;

export default defineConfig({
  testDir: "./tests",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: `http://localhost:${APP_PORT}`,
    trace: "on-first-retry",
    // Specs run "signed in": the mock backend 401s every personal route
    // without a session cookie (as the real one does), so seed one. Any token
    // works — the mock doesn't validate it. The two specs that assert the
    // anonymous / single-user UI clear this via their own test.use().
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
      // One process, both mock ports — they bind in the same tick, so waiting
      // on MOCK_API_PORT is enough to know the single-user one is up too.
      command: "node tests/mock-api/server.mjs",
      port: MOCK_API_PORT,
      reuseExistingServer: !process.env.CI,
      env: {
        MOCK_API_PORT: String(MOCK_API_PORT),
        MOCK_API_SINGLE_USER_PORT: String(MOCK_API_SINGLE_USER_PORT),
      },
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
    {
      // Its own build (and so its own distDir — the two run concurrently):
      // next.config.ts's /api/* rewrite is resolved at build time, so a shared
      // build would proxy this app's *browser* calls to the wrong mock.
      command: "npm run build && npm run start",
      port: SINGLE_USER_APP_PORT,
      timeout: 120_000,
      reuseExistingServer: !process.env.CI,
      env: {
        PORT: String(SINGLE_USER_APP_PORT),
        BACKEND_URL: `http://localhost:${MOCK_API_SINGLE_USER_PORT}`,
        NEXT_DIST_DIR: ".next-single-user",
      },
    },
  ],
});
