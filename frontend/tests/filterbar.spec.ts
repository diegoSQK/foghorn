import { expect, test } from "@playwright/test";

// The "Tonight" quick chip should collapse the date range to a single day
// (from === to) in the URL and render as active.
test("Tonight chip sets a single-day range and shows active", async ({ page }) => {
  await page.goto("/");

  const tonight = page.getByRole("button", { name: "Tonight" });
  await tonight.click();

  await expect(page).toHaveURL(/[?&]from=\d{4}-\d{2}-\d{2}/);
  const url = new URL(page.url());
  expect(url.searchParams.get("from")).toBe(url.searchParams.get("to"));

  // Active chip carries the filled style.
  await expect(tonight).toHaveClass(/bg-teal-700/);
});

// Date inputs hold a draft and commit on blur — mid-edit segment changes must
// not navigate (that snapped the input back while typing), and moving "From"
// past the current "To" drags "To" along instead of being blocked.
test("date inputs commit on blur and drag the range along", async ({ page }) => {
  await page.goto("/");

  // exact: the mock watchlist makes cards render "Remove X *from* watchlist"
  // buttons, which a substring label match would also catch.
  const fromInput = page.getByLabel("From", { exact: true });
  await fromInput.fill("2099-01-15"); // change event only; no blur yet
  await expect(page).toHaveURL((u) => !u.search.includes("from="));

  await fromInput.blur();
  await expect(page).toHaveURL(/from=2099-01-15/);
  // Default "To" was ~14 days out; committing a later "From" dragged it along.
  await expect(page).toHaveURL(/to=2099-01-15/);
});

// The "(N active)" badge on the mobile "More filters" toggle counts exactly
// the selections hidden behind it — nothing from the always-visible chip row.
// It has been wrong in both directions before: it counted params rather than
// selections (three genres read as "1"), and it counted controls sitting in
// the visible row, reporting as hidden things you could already see.
test.describe("More filters badge", () => {
  // The toggle is sm:hidden — it only exists on a narrow viewport.
  test.use({ viewport: { width: 390, height: 844 } });

  const badge = (page: import("@playwright/test").Page) =>
    page.getByRole("button", { name: /More filters/ });

  test("counts each selection, not each param", async ({ page }) => {
    await page.goto("/?genre=jazz");
    await expect(badge(page)).toHaveText(/\(1 active\)/);

    // Two values in one facet is two selections, not one param.
    await page.goto("/?genre=jazz,rock");
    await expect(badge(page)).toHaveText(/\(2 active\)/);

    // ...and facets add up.
    await page.goto("/?genre=jazz,rock&region=SF");
    await expect(badge(page)).toHaveText(/\(3 active\)/);
  });

  test("ignores filters that live in the always-visible row", async ({
    page,
  }) => {
    // Date range (the quick chips drive this), time of day, the performer
    // search, and the watchlist toggles are all visible while collapsed, so
    // none of them belong in a count of what's hidden.
    await page.goto(
      "/?from=2099-01-01&to=2099-01-02&time_of_day=late" +
        "&watchlist=true&venue_watchlist=true&performer_query=redman",
    );
    await expect(badge(page)).toHaveText(/More filters$/);

    // One genuinely hidden selection alongside them still counts as exactly 1.
    await page.goto("/?from=2099-01-01&time_of_day=late&genre=jazz");
    await expect(badge(page)).toHaveText(/\(1 active\)/);
  });
});
