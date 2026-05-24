import { expect, test } from "@playwright/test";

// Typing in the search box should debounce (~300ms) into ?performer_query= and
// keep the typed value after the URL-driven re-render.
test("typing a performer debounces into the URL", async ({ page }) => {
  await page.goto("/");

  const search = page.getByRole("searchbox", { name: "Search performers" });
  await search.fill("redman");

  await expect(page).toHaveURL(/[?&]performer_query=redman/, { timeout: 5000 });
  await expect(search).toHaveValue("redman");
});
