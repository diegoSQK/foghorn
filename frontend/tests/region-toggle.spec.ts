import { expect, test } from "@playwright/test";

// The SF region chip (the only region with data) is single-select: clicking
// sets ?region=SF, clicking again clears it.
test("SF region chip toggles ?region=SF on and off", async ({ page }) => {
  await page.goto("/");

  const sf = page.getByRole("button", { name: "SF", exact: true });
  await sf.click();
  await expect(page).toHaveURL(/[?&]region=SF/);
  await expect(sf).toHaveAttribute("aria-pressed", "true");

  await sf.click();
  await expect(page).not.toHaveURL(/region=SF/);
});

// Regions without venues render disabled with a "(soon)" affordance.
test("regions without data are disabled", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("button", { name: "East Bay (soon)" })).toBeDisabled();
});
