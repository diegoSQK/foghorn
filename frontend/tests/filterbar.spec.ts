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
  await expect(tonight).toHaveClass(/bg-zinc-900/);
});
