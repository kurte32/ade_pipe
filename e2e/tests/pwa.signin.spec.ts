import { expect, test } from "@playwright/test";

import { PWA_URL, signInAs } from "../helpers/auth";

test.describe("HU-01 / HU-02: sign in and see only my sites", () => {
  test("coordinator signs in and sees the site list", async ({ page }) => {
    const errors: string[] = [];
    page.on("console", (m) => {
      if (m.type() === "error") errors.push(m.text());
    });
    await signInAs(page, PWA_URL, "ard");
    await expect(page.getByRole("heading", { name: "Mis sitios" })).toBeVisible();
    await expect(page.getByTestId("sitios-list")).toBeVisible();
    expect(errors.filter((e) => !e.includes("favicon"))).toEqual([]);
  });

  test("user without role cannot enter", async ({ page }) => {
    await page.goto(PWA_URL + "/");
    await page.getByTestId("dev-user-xna").click();
    await expect(page.getByRole("alert")).toContainText("no tiene el rol Coordinador");
  });

  test("session survives a reload", async ({ page }) => {
    await signInAs(page, PWA_URL, "ard");
    await page.reload();
    await expect(page.getByRole("heading", { name: "Mis sitios" })).toBeVisible();
  });
});
