import { defineConfig, devices } from "@playwright/test";

// Two managed servers, started in parallel and waited on before tests run:
//   1. the mock backend (returns fixture JSON for /api/shows + /api/venues)
//   2. the Next app, built+started with NEXT_PUBLIC_API_BASE_URL pointed at (1)
//
// We run a built production app (`npm run build && npm run start`), not `dev`:
// it's what `next build` already validates in the gate, exercises the real
// server-component → fetch → render path, and avoids dev-only quirks. The app
// runs on 3100 (not the default 3000) so a developer's `npm run dev` can keep
// running alongside the test run.

const MOCK_API_PORT = 4010;
const APP_PORT = 3100;

export default defineConfig({
  testDir: "./tests",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: `http://localhost:${APP_PORT}`,
    trace: "on-first-retry",
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
        NEXT_PUBLIC_API_BASE_URL: `http://localhost:${MOCK_API_PORT}`,
      },
    },
  ],
});
