import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { signInAdmin } from "../helpers/admin";

/** Accessibility checks for the admin shell and dialogs (docs/ux/UX_VALIDATION.md). */
test.describe("UX: accessibility (admin)", () => {
  test("admin dialog traps focus, closes with Escape and restores focus", async ({ page }) => {
    await signInAdmin(page);
    await page.goto("/sitios");
    await page.locator('[data-testid="sitios-table"] a').first().click();
    const reasignar = page.getByRole("button", { name: "Reasignar", exact: true });
    await reasignar.click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await expect(dialog).toHaveAttribute("aria-modal", "true");
    for (let i = 0; i < 8; i++) {
      await page.keyboard.press("Tab");
      const inside = await page.evaluate(() => !!document.activeElement?.closest('[role="dialog"]'));
      expect(inside, `focus left the dialog after ${i + 1} tabs`).toBe(true);
    }
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
    await expect(reasignar).toBeFocused();
  });

  test("admin pages have a skip link, one h1 and a current nav item", async ({ page }) => {
    await signInAdmin(page);
    for (const path of ["/", "/sitios", "/cargas", "/equivalencias", "/auditoria"]) {
      await page.goto(path);
      await expect(page.locator("h1")).toHaveCount(1);
      await expect(page.locator("a.skip-link")).toHaveAttribute("href", "#contenido");
      await expect(page.getByRole("navigation", { name: "Principal" }).locator('a[aria-current="page"]')).toHaveCount(1);
      await expect(page).toHaveTitle(/Pipeline de Posibles Tiendas$/);
      // Automated WCAG 2 A/AA scan (backlog UX-SR); a screen-reader walkthrough is still manual.
      await page.waitForLoadState("networkidle");
      const axe = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
      const serious = axe.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
      expect(serious.map((v) => `${v.id} on ${path}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`)).toEqual([]);
    }
  });

});
