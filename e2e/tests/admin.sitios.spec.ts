import { expect, test } from "@playwright/test";

import { advanceToDuenoLocalizado, signInAdmin, trackConsoleErrors } from "../helpers/admin";

test.describe("HU-13: admin returns a site; RF-09 reassignment", () => {
  test("devolver with motivo and comentario, then reasignar", async ({ page }) => {
    const errors = trackConsoleErrors(page);
    const sitioId = await advanceToDuenoLocalizado("ard");

    await signInAdmin(page);
    await page.goto(`/sitios/${sitioId}`);
    await expect(page.getByText("Dueño Localizado").first()).toBeVisible();
    await expect(page.getByTestId("detail-coordinador")).toContainText("ard");

    await page.getByRole("button", { name: "Devolver", exact: true }).click();
    const dialog = page.getByTestId("dialog-devolver");
    await expect(dialog).toBeVisible();
    await dialog.getByLabel("Estatus destino").selectOption("sitio_prospectado");
    await dialog.getByLabel("Motivo").selectOption("calidad_datos");
    await dialog.getByLabel(/Comentario/).fill("Teléfono del dueño incompleto, verificar en campo.");
    await dialog.getByRole("button", { name: "Devolver" }).click();

    await expect(page.getByRole("status")).toContainText("Sitio devuelto a Sitio Prospectado");
    await expect(page.locator(".badge-devuelto")).toContainText("devuelto");
    await expect(page.getByTestId("detail-devolucion")).toContainText("calidad_datos");
    const historial = page.getByTestId("historial");
    await expect(historial).toContainText("devolucion");
    await expect(historial).toContainText("Teléfono del dueño incompleto");

    await page.getByRole("button", { name: "Reasignar", exact: true }).click();
    const reasignar = page.getByTestId("dialog-reasignar");
    await expect(reasignar).toBeVisible();
    const select = reasignar.getByLabel("Nuevo coordinador");
    const mmiValue = await select.locator("option", { hasText: /^mmi/ }).getAttribute("value");
    expect(mmiValue).toBeTruthy();
    await select.selectOption(mmiValue!);
    await reasignar.getByRole("button", { name: "Reasignar" }).click();
    await expect(page.getByRole("status")).toContainText("Sitio reasignado");
    await expect(page.getByTestId("detail-coordinador")).toContainText("mmi");
    await expect(historial).toContainText("reasignacion");

    // The site now shows up under mmi in the list.
    const nombre = ((await page.locator("h1").first().innerText()).split("#")[0] ?? "").trim();
    await page.getByRole("navigation", { name: "Principal" }).getByRole("link", { name: "Sitios" }).click();
    await page.getByTestId("sitios-search").fill(nombre);
    await page.getByRole("button", { name: "Filtrar" }).click();
    const row = page.getByTestId(`sitio-row-${sitioId}`);
    await expect(row).toBeVisible();
    await expect(row.getByTestId("col-coordinador")).toHaveText("mmi");
    expect(errors).toEqual([]);
  });

  test("stale ETag yields a clear conflict message", async ({ page }) => {
    const sitioId = await advanceToDuenoLocalizado("ard");
    await signInAdmin(page);
    await page.goto(`/sitios/${sitioId}`);
    await expect(page.getByText("Dueño Localizado").first()).toBeVisible();

    // Change the record behind the page's back (another admin returns it first).
    const { adminToken } = await import("../helpers/admin");
    const { api } = await import("../helpers/auth");
    const token = await adminToken();
    const detail = await api<{ etag: string }>("GET", `/api/v1/sitios/${sitioId}`, token);
    const r = await api(
      "POST",
      `/api/v1/admin/sitios/${sitioId}/devolver`,
      token,
      { estatus_destino: "sitio_prospectado", motivo: "otro", comentario: "Devuelto por otro admin" },
      { "if-match": `"${detail.data.etag}"` },
    );
    expect(r.status).toBe(200);

    await page.getByRole("button", { name: "Devolver", exact: true }).click();
    const dialog = page.getByTestId("dialog-devolver");
    await dialog.getByLabel(/Comentario/).fill("Intento con ETag viejo");
    await dialog.getByRole("button", { name: "Devolver" }).click();
    await expect(dialog.getByRole("alert")).toContainText("El registro cambió");
  });
});
