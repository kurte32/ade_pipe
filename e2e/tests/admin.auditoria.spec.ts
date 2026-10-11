import { expect, test } from "@playwright/test";

import { signInAdmin, trackConsoleErrors } from "../helpers/admin";

test.describe("HU-15: audit log viewer", () => {
  test("filter by action shows matching rows with details", async ({ page }) => {
    const errors = trackConsoleErrors(page);
    await signInAdmin(page);
    await page.getByRole("link", { name: "Auditoría" }).click();
    await expect(page.getByTestId("auditoria-table")).toBeVisible();
    await expect(page.getByTestId("aud-row").first()).toBeVisible();

    await page.getByTestId("aud-accion").fill("carga_confirmada");
    await page.getByTestId("aud-filtrar").click();
    const rows = page.getByTestId("aud-row");
    await expect(rows.first()).toBeVisible();
    const count = await rows.count();
    for (let i = 0; i < Math.min(count, 5); i++) {
      await expect(rows.nth(i)).toContainText("carga_confirmada");
    }
    await rows.first().getByRole("button", { name: "Ver" }).click();
    await expect(rows.first().locator("pre.json")).toContainText("insertadas");

    await page.getByTestId("aud-accion").fill("accion_que_no_existe");
    await page.getByTestId("aud-filtrar").click();
    await expect(page.getByText("Sin registros para este filtro.")).toBeVisible();
    expect(errors).toEqual([]);
  });
});
