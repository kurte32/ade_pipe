import { expect, test } from "@playwright/test";

import { buildE2ECsv, signInAdmin, trackConsoleErrors } from "../helpers/admin";

test.describe("HU-03 / HU-04: bulk load with preview, decisions and confirm", () => {
  test("upload CSV, review, approve warning, confirm, find new site", async ({ page }) => {
    const errors = trackConsoleErrors(page);
    const base = 800000 + (Date.now() % 80000); // below the 890000 site pool
    const { csv, names } = buildE2ECsv(base);

    await signInAdmin(page);
    await page.getByRole("link", { name: "Cargas" }).click();
    await expect(page.getByRole("heading", { name: "Cargas" })).toBeVisible();

    await page.getByTestId("carga-file").setInputFiles({
      name: `carga_e2e_${base}.csv`,
      mimeType: "text/csv",
      buffer: Buffer.from(csv, "utf-8"),
    });
    await page.getByTestId("carga-submit").click();

    await expect(page).toHaveURL(/\/cargas\/[0-9a-f-]{36}$/);
    await expect(page.getByTestId("lote-estado")).toHaveText("vista_previa");
    await expect(page.getByTestId("count-error")).toHaveText("1");
    const warnings = Number(await page.getByTestId("count-advertencia").textContent());
    expect(warnings).toBeGreaterThanOrEqual(1);
    await expect(page.getByTestId("count-pendientes")).toHaveText(String(warnings));

    // The bad POTENCIAL row is an error and cannot be decided.
    const errorRow = page.locator('tr[data-resultado="error"]').first();
    await expect(errorRow).toContainText(names[4]!);
    await expect(errorRow).toContainText("no se puede aprobar");

    // Suspicious name is a warning requiring a decision.
    const warnRow = page.locator('tr[data-resultado="advertencia"]', { hasText: names[3]! });
    await expect(warnRow).toBeVisible();
    await expect(warnRow).toContainText("nombre_sospechoso");

    // Confirm is disabled until decisions are saved.
    await expect(page.getByTestId("confirmar-carga")).toBeDisabled();
    await page.getByRole("button", { name: "Aprobar todas las advertencias" }).click();
    await page.getByTestId("guardar-decisiones").click();
    await expect(page.getByTestId("count-pendientes")).toHaveText("0");
    await expect(page.getByTestId("confirmar-carga")).toBeEnabled();

    await page.getByTestId("confirmar-carga").click();
    await expect(page.getByTestId("confirm-result")).toContainText("4 sitios insertados");
    await expect(page.getByTestId("lote-estado")).toHaveText("confirmado");

    // The new site is searchable in Sitios.
    await page.getByRole("link", { name: "Sitios" }).click();
    await page.getByTestId("sitios-search").fill(`E2E-${base} A`);
    await page.getByRole("button", { name: "Filtrar" }).click();
    const table = page.getByTestId("sitios-table");
    await expect(table).toContainText(names[0]!);
    await expect(table).toContainText("ard");
    await expect(table).toContainText("Sitio Prospectado");

    // Error rows never became sites.
    await page.getByTestId("sitios-search").fill(`E2E-${base} E`);
    await page.getByRole("button", { name: "Filtrar" }).click();
    await expect(page.getByText("Sin resultados.")).toBeVisible();

    expect(errors).toEqual([]);
  });

  test("invalid file is rejected with a Problem Details message", async ({ page }) => {
    await signInAdmin(page);
    await page.goto("/cargas");
    await page.getByTestId("carga-file").setInputFiles({
      name: "malo.csv",
      mimeType: "text/csv",
      buffer: Buffer.from("A,B,C\n1,2,3\n", "utf-8"),
    });
    await page.getByTestId("carga-submit").click();
    await expect(page.getByRole("alert")).toContainText(/columna|Datos inv|no válid/i);
  });
});
