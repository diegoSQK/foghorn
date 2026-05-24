# Frontend e2e tests (Playwright)

End-to-end / component tests for the foghorn frontend. They drive a real
Chromium against a production build of the app, with the backend mocked — so
they exercise the full server-component → fetch → render → client-interaction
loop without needing Python or a database.

## Run them

```bash
make frontend-test          # from the repo root (installs the browser if needed)
# or, from frontend/:
npx playwright install chromium   # one-time, downloads the browser binary
npm run test:e2e
```

These are **not** part of `make gate` (they're slower and need a browser).
CI runs them as a separate `frontend-test` job; both it and `gate` must pass.

Useful flags while developing: `npx playwright test --ui` (interactive),
`--headed`, `--debug`, `npx playwright test tests/region-toggle.spec.ts` (one
file).

## How it's wired (`playwright.config.ts`)

Playwright starts two servers and waits for both before running:

1. **Mock backend** — `tests/mock-api/server.mjs`, a ~30-line Node HTTP server
   that returns the fixture JSON below for `/api/shows` and `/api/venues`.
2. **The app** — `npm run build && npm run start` on port **3100**, built with
   `NEXT_PUBLIC_API_BASE_URL` pointed at the mock.

**Why a mock *server* and not Playwright's `page.route()`?** `app/page.tsx` is
an async *server* component: it fetches the API from the Next server process,
not the browser. `page.route()` only intercepts browser requests, so it can't
see those fetches. Pointing the app at a mock server is the way to control the
data a server component sees. (If/when a *client* component fetches directly,
`page.route()` is the right tool for that call — both can coexist.)

The specs assert **UI/URL behavior** (chip toggles, debounced search, deep-link
reflection), not backend filtering — that's covered by the backend pytest
suite, so the mock returns a static list regardless of query params.

## Writing a new spec

1. Add `tests/<feature>.spec.ts`:

   ```ts
   import { expect, test } from "@playwright/test";

   test("does the thing", async ({ page }) => {
     await page.goto("/?some=filter");        // baseURL is localhost:3100
     await page.getByRole("button", { name: "Tonight" }).click();
     await expect(page).toHaveURL(/[?&]from=/);
   });
   ```

2. Prefer role/label selectors (`getByRole`, `getByLabel`) over CSS classes so
   the tests survive styling changes. (The one place we match a class is the
   active-chip `bg-zinc-900` style, since active-ness isn't otherwise exposed —
   if a chip gains `aria-pressed`, switch to that.)

3. If you need different data, edit the fixtures (next section). The specs and
   config are excluded from the app's `tsc`/`eslint` (see `tsconfig.json` /
   `eslint.config.mjs`); Playwright type-checks and runs them itself.

## Updating fixtures

- `tests/fixtures/venues.json` — shape of `GET /api/venues` (drives the venue
  checkboxes and which region chips are interactive).
- `tests/fixtures/shows.json` — shape of `GET /api/shows` (`ShowView[]`; see
  `backend/src/foghorn/api/shows.py`).

Keep them in sync with the backend response shapes. They're plain JSON — no
build step. After editing, re-run `npm run test:e2e`.
