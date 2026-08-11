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

Playwright starts three servers and waits for them before running:

1. **Mock backend** — `tests/mock-api/server.mjs`, a small Node HTTP server
   returning the fixture JSON below for `/api/shows` and `/api/venues`. One
   process, two ports: **4010** (normal auth) and **4011** (single-user).
2. **The app** — `npm run build && npm run start` on port **3200**, with
   `BACKEND_URL` pointed at :4010. Server components fetch it directly;
   browser fetches go relative and the `next.config.ts` rewrite proxies them
   to the mock.
3. **A second app** on port **3201**, pointed at the single-user mock (:4011).
   It gets its own build under `NEXT_DIST_DIR=.next-single-user`: the rewrite
   destination is resolved at *build* time, so sharing one build would proxy
   this app's browser calls to the other mock.

**Auth in the specs.** The config seeds a `foghorn_session` cookie, so specs
run signed in as an admin; the mock 401s personal routes without it, like the
real backend. `auth-modes.spec.ts` clears the cookie to cover the two
cookie-less modes — anonymous (:3200) and single-user (:3201). Those two are
the *same* request distinguished only by the backend's `FOGHORN_SINGLE_USER`
flag, which is why there's a second app/mock pair rather than one.

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
