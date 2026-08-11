import { expect, test } from "@playwright/test";

// The two cookie-less UI modes. Every other spec runs with the seeded session
// cookie from playwright.config.ts; these clear it, because what's under test
// is precisely what the app does when it has no cookie to forward.
//
// - Anonymous (:3200, mock backend in normal mode): /api/auth/me 401s, so the
//   calendar renders read-only — no follow affordances at all.
// - Single-user (:3201, mock backend with single_user: true, mirroring
//   FOGHORN_SINGLE_USER=1): the backend resolves the request as the bootstrap
//   admin, so every affordance is present with no sign-in — the fleet
//   deployment's whole reason for existing. Regression guard on
//   lib/serverAuth.ts, which used to return null before ever asking the
//   backend whenever the cookie was missing.

const NO_COOKIES = { storageState: { cookies: [], origins: [] } };

/** The `+` / `✓` toggles rendered next to every performer on a show row. */
function followButtons(page: import("@playwright/test").Page) {
  return page.getByRole("button", {
    name: /(Add .+ to watchlist|Remove .+ from watchlist)/,
  });
}

test.describe("anonymous (no session, normal mode)", () => {
  test.use(NO_COOKIES);

  test("renders the calendar with no follow affordances", async ({ page }) => {
    await page.goto("/");

    // Shows still render — browsing is public.
    await expect(page.getByRole("link", { name: "foghorn" })).toBeVisible();
    await expect(followButtons(page)).toHaveCount(0);
    await expect(
      page.getByRole("button", { name: "Mark as jam session" }),
    ).toHaveCount(0);
    await expect(
      page.getByRole("button", { name: /^Watchlist \(\d+\)$/ }),
    ).toHaveCount(0);

    // No identity in the nav, and no admin-only links.
    await expect(page.getByText("Test User")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Sign out" })).toHaveCount(0);
    await expect(page.getByRole("link", { name: "Inbox" })).toHaveCount(0);
  });
});

test.describe("single-user mode (no session, FOGHORN_SINGLE_USER)", () => {
  test.use({ ...NO_COOKIES, baseURL: "http://localhost:3201" });

  test("shows every follow affordance without signing in", async ({ page }) => {
    await page.goto("/");

    await expect(followButtons(page).first()).toBeVisible();
    await expect(
      page.getByRole("button", { name: /^Watchlist \(\d+\)$/ }),
    ).toBeVisible();
    // Admin-gated surfaces resolve too (the flag resolves to an admin).
    await expect(
      page.getByRole("button", { name: "Mark as jam session" }).first(),
    ).toBeVisible();
    await expect(page.getByRole("link", { name: /^Inbox/ })).toBeVisible();
  });

  test("names the user but offers no sign-out", async ({ page }) => {
    await page.goto("/");

    await expect(page.getByText("Test User")).toBeVisible();
    // Signing out would be a no-op: the next request re-resolves as the same
    // admin, so the control is hidden rather than left to mislead.
    await expect(page.getByRole("button", { name: "Sign out" })).toHaveCount(0);
  });
});
