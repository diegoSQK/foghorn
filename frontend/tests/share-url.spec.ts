import { expect, test } from "@playwright/test";

// A deep-linked filter URL should be reflected in the controls on load — the
// whole point of URL-as-state (shareable / bookmarkable filters).
test("a deep-linked filter URL is reflected in the controls", async ({ page }) => {
  await page.goto("/?venues=keys_jazz_bistro&time_of_day=late");

  // Venue checkboxes reflect ?venues=keys_jazz_bistro.
  await expect(
    page.getByRole("checkbox", { name: "Keys Jazz Bistro" }),
  ).toBeChecked();
  await expect(
    page.getByRole("checkbox", { name: "Bird & Beckett Books and Records" }),
  ).not.toBeChecked();

  // The Late chip reflects ?time_of_day=late.
  await expect(page.getByRole("button", { name: "Late (9pm+)" })).toHaveClass(
    /bg-zinc-900/,
  );

  // Shows still render (the mock returns a non-empty list).
  await expect(page.getByText("David Parker Sextet")).toBeVisible();
});
