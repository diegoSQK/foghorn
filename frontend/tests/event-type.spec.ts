import { expect, test } from "@playwright/test";

// The per-show event-type correction: non-jam rows carry a faint "jam?"
// affordance that optimistically flips to the jam badge on click (the PUT
// stores a venue+billing rule server-side); jam rows carry the badge as an
// unmark button. Fixture: "Late Night Trio" is the one jam row.

test("jam badge renders for jam rows and 'jam?' affordance for the rest", async ({
  page,
}) => {
  await page.goto("/");
  await expect(
    page.getByRole("button", { name: "Unmark jam session" }),
  ).toHaveCount(1);
  expect(
    await page.getByRole("button", { name: "Mark as jam session" }).count(),
  ).toBeGreaterThan(0);
});

test("marking a show as jam flips the badge optimistically", async ({
  page,
}) => {
  await page.goto("/");
  const before = await page
    .getByRole("button", { name: "Unmark jam session" })
    .count();
  await page.getByRole("button", { name: "Mark as jam session" }).first().click();
  await expect(
    page.getByRole("button", { name: "Unmark jam session" }),
  ).toHaveCount(before + 1);
});
