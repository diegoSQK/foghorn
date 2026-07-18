import { expect, test } from "@playwright/test";

// The day view renders as a time × venue grid: one column per venue with
// shows (the mock returns the whole fixture regardless of date), an hour
// ruler derived from the data's time range, and a block per show. Blocks
// link out to tickets when the show has a ticket_url, else to source_url.

test("day view renders venue columns, an hour ruler, and show blocks", async ({
  page,
}) => {
  await page.goto("/?view=day&anchor=2026-06-05");

  // Venue column headers link into that venue's calendar.
  await expect(
    page.getByRole("link", { name: "Keys Jazz Bistro" }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Bird & Beckett Books and Records" }),
  ).toBeVisible();

  // Hour ruler spans the fixture's range: earliest set 19:30 → "7 PM" label.
  await expect(page.getByText("7 PM", { exact: true })).toBeVisible();

  // Show blocks render at their start times; Keys Quartet has a ticket_url,
  // so its block is a link out to tickets.
  await expect(page.getByText("David Parker Sextet")).toBeVisible();
  await expect(
    page.getByRole("link", { name: /Keys Quartet/ }),
  ).toHaveAttribute("href", "https://example.com/tickets/2");
});
