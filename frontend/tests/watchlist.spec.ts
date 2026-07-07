import { expect, test } from "@playwright/test";

// /watchlist against the mock backend: two fixture entries ("David Parker
// Sextet", "Late Night Trio" — see fixtures/watchlist.json) and the static
// shows fixture. The mock's watchlist route is stateful (POST appends), so the
// add-form spec uses a name no other spec asserts on.

// The chip row's remove buttons share their accessible name with the show
// cards' on-watchlist toggles, so chip assertions scope to the section under
// the "Your watchlist" heading.
function chipRow(page: import("@playwright/test").Page) {
  return page
    .locator("section")
    .filter({ has: page.getByRole("heading", { name: "Your watchlist" }) });
}

test("watchlist page renders entry chips and matching shows", async ({ page }) => {
  await page.goto("/watchlist");

  await expect(
    page.getByRole("heading", { name: "Your watchlist" }),
  ).toBeVisible();
  // Each fixture entry renders as a chip with its remove affordance.
  await expect(
    chipRow(page).getByRole("button", {
      name: "Remove David Parker Sextet from watchlist",
    }),
  ).toBeVisible();
  await expect(
    chipRow(page).getByRole("button", {
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
  await page.goto("/watchlist");

  await page
    .getByRole("textbox", { name: "Follow a performer by name" })
    .fill("Zawinul Syndicate");
  await page.getByRole("button", { name: "Follow", exact: true }).click();

  // POST → router.refresh() → the server refetches GET /api/watchlist and the
  // new entry lands in the chip row.
  await expect(
    chipRow(page).getByRole("button", {
      name: "Remove Zawinul Syndicate from watchlist",
    }),
  ).toBeVisible();
  // The input clears after a successful add.
  await expect(
    page.getByRole("textbox", { name: "Follow a performer by name" }),
  ).toHaveValue("");
});

test("a deep-linked filter URL is reflected in the watchlist controls", async ({
  page,
}) => {
  await page.goto("/watchlist?venues=keys_jazz_bistro&time_of_day=late");

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
