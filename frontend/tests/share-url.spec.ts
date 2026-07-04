import { expect, test } from "@playwright/test";

// A deep-linked filter URL should be reflected in the controls on load — the
// whole point of URL-as-state (shareable / bookmarkable filters).
test("a deep-linked filter URL is reflected in the controls", async ({ page }) => {
  await page.goto("/?venues=keys_jazz_bistro&time_of_day=late");

  // The venue picker reflects ?venues=keys_jazz_bistro: a removable selected
  // chip for Keys, and only Keys.
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

  // Shows still render (the mock returns a non-empty list).
  await expect(page.getByText("David Parker Sextet")).toBeVisible();
});
