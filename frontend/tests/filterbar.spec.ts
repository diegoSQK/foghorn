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

  const fromInput = page.getByLabel("From");
  await fromInput.fill("2099-01-15"); // change event only; no blur yet
  await expect(page).toHaveURL((u) => !u.search.includes("from="));

  await fromInput.blur();
  await expect(page).toHaveURL(/from=2099-01-15/);
  // Default "To" was ~14 days out; committing a later "From" dragged it along.
  await expect(page).toHaveURL(/to=2099-01-15/);
});
