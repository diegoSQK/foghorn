import { expect, test } from "@playwright/test";

// Followed shows (watchlist-matched performers / watched venues) take
// display precedence. Fixture: "David Parker Sextet" and "Late Night Trio"
// are watchlist entries; "Early Openers" (6pm, same date as David Parker's
// 7:30pm) is not — followed-first ordering must beat time order.

test("list view floats watchlist matches to the top of a date group", async ({
  page,
}) => {
  await page.goto("/");
  const firstSection = page.locator("section").filter({ hasText: "June 5" }).first();
  const rows = firstSection.locator("li");
  await expect(rows.first()).toContainText("David Parker Sextet");
  await expect(rows.nth(1)).toContainText("Early Openers");
});

test("day grid sorts followed venue columns to the far left", async ({
  page,
}) => {
  await page.goto("/?view=day&anchor=2026-06-05");
  // Bird & Beckett (David Parker Sextet, 7:30pm) leads despite Keys' 6pm
  // start, because its column holds a followed show.
  const headers = page.getByRole("link", {
    name: /Bird & Beckett|Keys Jazz Bistro|Mr\. Tipple/,
  });
  await expect(headers.first()).toHaveText(/Bird & Beckett/);
});
