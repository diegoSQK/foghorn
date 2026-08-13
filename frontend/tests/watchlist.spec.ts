import { expect, test } from "@playwright/test";

// The watchlist against the mock backend: two fixture entries ("David Parker
// Sextet", "Late Night Trio" — see fixtures/watchlist.json) and the static
// shows fixture. Since the UI consolidation the watchlist lives on the main
// page as the ?watchlist=true filter (with its management panel inline);
// /watchlist survives only as a param-preserving redirect. The mock's
// watchlist route is stateful (POST appends), so the add-form spec uses a
// name no other spec asserts on.

// The panel's remove buttons share their accessible name with the show cards'
// on-watchlist toggles, so entry assertions scope to the <details> carrying
// the "Your watchlist" summary. The panel collapsed (it was a wall of chips at
// 55 entries), so specs open it before asserting on entries.
function watchlistPanel(page: import("@playwright/test").Page) {
  return page
    .locator("details")
    .filter({ has: page.getByText("Your watchlist") });
}

async function openPanel(page: import("@playwright/test").Page) {
  const panel = watchlistPanel(page);
  await expect(panel).toBeVisible();
  if (!(await panel.evaluate((el: HTMLDetailsElement) => el.open))) {
    await panel.locator("summary").click();
  }
  return panel;
}

test("the Watchlist chip filters and reveals the management panel", async ({
  page,
}) => {
  await page.goto("/");

  // Chip carries the entry count — but the count is shared mutable mock
  // state (the add-form spec grows it in a parallel worker), so the locator
  // stays count-agnostic. The panel is hidden until the chip is active.
  const chip = page.getByRole("button", { name: /^Watchlist \(\d+\)$/ });
  await expect(watchlistPanel(page)).toHaveCount(0);

  await chip.click();
  await expect(page).toHaveURL(/[?&]watchlist=true/);
  await openPanel(page);
  await expect(
    watchlistPanel(page).getByRole("button", {
      name: "Remove David Parker Sextet from watchlist",
    }),
  ).toBeVisible();

  // Toggling off clears the param and the panel.
  await chip.click();
  await expect(page).not.toHaveURL(/watchlist=true/);
  await expect(watchlistPanel(page)).toHaveCount(0);
});

test("/watchlist redirects into the main-page filter", async ({ page }) => {
  await page.goto("/watchlist");

  await expect(page).toHaveURL(/\/\?.*watchlist=true/);
  await openPanel(page);
  await expect(
    watchlistPanel(page).getByRole("button", {
      name: "Remove Late Night Trio from watchlist",
    }),
  ).toBeVisible();

  // The show list renders from the mock's /api/shows — "Keys Quartet" is not
  // a watchlist entry, so it can only come from a rendered show card.
  await expect(page.getByText("Keys Quartet")).toBeVisible();
});

test("follow-by-name form posts and the new chip appears on refresh", async ({
  page,
}) => {
  await page.goto("/?watchlist=true");

  await page
    .getByRole("textbox", { name: "Follow a performer by name" })
    .fill("Zawinul Syndicate");
  await page.getByRole("button", { name: "Follow", exact: true }).click();

  // A genuinely new follow says so, and clears the input.
  await expect(page.getByText("Now following Zawinul Syndicate.")).toBeVisible();
  await expect(
    page.getByRole("textbox", { name: "Follow a performer by name" }),
  ).toHaveValue("");

  // POST → router.refresh() → the server refetches GET /api/watchlist and the
  // new entry lands in the panel.
  await openPanel(page);
  await expect(
    watchlistPanel(page).getByRole("button", {
      name: "Remove Zawinul Syndicate from watchlist",
    }),
  ).toBeVisible();
});

test("a deep-linked /watchlist filter URL survives the redirect", async ({
  page,
}) => {
  await page.goto("/watchlist?venues=keys_jazz_bistro&time_of_day=late");

  // The redirect lands on / with every param carried across.
  await expect(page).toHaveURL(/[?&]watchlist=true/);
  await expect(page).toHaveURL(/[?&]venues=keys_jazz_bistro/);
  await expect(page).toHaveURL(/[?&]time_of_day=late/);

  // The venue picker reflects ?venues=: a removable chip for Keys, and only Keys.
  await expect(
    page.getByRole("button", { name: "Remove venue Keys Jazz Bistro" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", {
      name: "Remove venue Bird & Beckett Books and Records",
    }),
  ).toHaveCount(0);

  // The Late chip reflects ?time_of_day=late.
  await expect(page.getByRole("button", { name: "Late (9pm+)" })).toHaveClass(
    /bg-teal-700/,
  );

  // Watchlist matches still render (the mock returns a non-empty list).
  await expect(page.getByText("Keys Quartet")).toBeVisible();
});

test("/venues redirects into the venue-watchlist filter", async ({ page }) => {
  await page.goto("/venues");
  await expect(page).toHaveURL(/\/\?.*venue_watchlist=true/);
});

test("re-following an existing name says so instead of silently succeeding", async ({
  page,
}) => {
  await page.goto("/?watchlist=true");

  const input = page.getByRole("textbox", {
    name: "Follow a performer by name",
  });
  // "David Parker Sextet" is a fixture entry. Typed in a different case, to
  // prove the check is on the canonical name rather than the literal string.
  await input.fill("david parker SEXTET");
  await page.getByRole("button", { name: "Follow", exact: true }).click();

  await expect(
    page.getByText("David Parker Sextet is already on your watchlist."),
  ).toBeVisible();
  // The text stays put on a duplicate, so it's obvious what was just judged
  // one — unlike the old behaviour, which cleared the box either way.
  await expect(input).toHaveValue("david parker SEXTET");

  // Typing again clears the verdict.
  await input.fill("david parker SEXTET!");
  await expect(
    page.getByText("David Parker Sextet is already on your watchlist."),
  ).toHaveCount(0);
});
