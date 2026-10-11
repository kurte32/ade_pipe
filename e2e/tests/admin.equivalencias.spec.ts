import { expect, test } from "@playwright/test";

import { signInAdmin, trackConsoleErrors } from "../helpers/admin";

test.describe("HU-05: equivalences user code to email", () => {
  test("unknown email is rejected per code; valid email is saved", async ({ page }) => {
    const errors = trackConsoleErrors(page);
    await signInAdmin(page);
    await page.getByRole("link", { name: "Equivalencias" }).click();
    await expect(page.getByTestId("equivalencias-table")).toBeVisible();
    const row = page.getByTestId("eq-jdc");
    await expect(row).toContainText("jdc");

    const correo = row.getByLabel("Correo jdc");
    await correo.fill("nadie@dev.tiendas3b.test");
    await page.getByTestId("eq-guardar").click();
    await expect(page.getByTestId("eq-problem")).toBeVisible();
    await expect(page.getByTestId("eq-error-jdc")).toBeVisible();
    // Nothing was saved: the server still has the original email.
    await page.reload();
    await expect(page.getByTestId("eq-jdc").getByLabel("Correo jdc")).toHaveValue("jdc@dev.tiendas3b.test");

    await page.getByTestId("eq-jdc").getByLabel("Correo jdc").fill("jdc@dev.tiendas3b.test");
    await page.getByTestId("eq-guardar").click();
    await expect(page.getByTestId("eq-saved")).toBeVisible();
    await expect(page.getByTestId("eq-jdc")).toContainText("Javier Delgado Castro");
    expect(errors).toEqual([]);
  });
});
