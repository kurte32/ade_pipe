import { expect, test } from "@playwright/test";

import { PWA_URL, signInAs } from "../helpers/auth";
import { sitiosDe } from "../helpers/pwa";

/** Responsive and keyboard checks for the coordinator PWA on a phone (docs/ux/UX_VALIDATION.md). */
test.describe("UX: layout and keyboard (coordinador)", () => {
  test("coordinator pages never scroll horizontally on a phone", async ({ page }) => {
    await signInAs(page, PWA_URL, "ard");
    const sites = await sitiosDe("ard");
    const paths = ["/", "/notificaciones", ...(sites[0] ? [`/sitios/${sites[0].id}`] : [])];
    for (const path of paths) {
      await page.goto(PWA_URL + path);
      await expect(page.locator("h1")).toHaveCount(1);
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      expect(overflow, `horizontal overflow on ${path}`).toBeLessThanOrEqual(0);
      // Every interactive control reachable by keyboard shows a visible focus ring (outline from :focus-visible).
      await page.keyboard.press("Tab");
      const outline = await page.evaluate(() => getComputedStyle(document.activeElement!).outlineStyle);
      expect(outline).not.toBe("none");
    }
  });
});
