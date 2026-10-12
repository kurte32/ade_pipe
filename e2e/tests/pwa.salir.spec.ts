import { expect, test } from "@playwright/test";

import { PWA_URL, signInAs } from "../helpers/auth";
import { detalle, sitiosDe } from "../helpers/pwa";

/** "Salir" wipes the phone; with unsent captures it must ask first (docs/ux/UX_AUDIT.md P13, backlog UX-SALIR). */
test.describe("Salir con capturas sin enviar", () => {
  test("asks for confirmation while something is queued; signs out directly once synced", async ({ page, context }) => {
    const list = await sitiosDe("ard", "sitio_prospectado");
    const site = list.find((x) => !x.devuelto) ?? list[0];
    if (!site) throw new Error("no hay sitios prospectados para ard");

    await signInAs(page, PWA_URL, "ard");
    await page.goto(`${PWA_URL}/sitios/${site.id}`);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();

    await context.setOffline(true);
    await expect(page.getByTestId("offline-banner")).toBeVisible();
    await page.getByLabel("Nombre del dueño").fill("Dueño Salir");
    await page.getByLabel("Teléfono").fill("5511122233");
    await page.getByTestId("guardar-contacto").click();
    await expect(page.getByTestId("sync-now")).toContainText("1 por enviar");

    // Salir with one queued capture: the dialog appears and cancelling keeps the session and the capture.
    await page.getByRole("button", { name: "Salir" }).click();
    const dialog = page.getByTestId("dialog-salir");
    await expect(dialog).toBeVisible();
    await expect(dialog).toContainText("1 captura sin enviar");
    await dialog.getByRole("button", { name: "Cancelar" }).click();
    await expect(dialog).toBeHidden();
    await expect(page.getByRole("button", { name: "Salir" })).toBeVisible();
    await expect(page.getByTestId("sync-now")).toContainText("1 por enviar");
    expect((await detalle("ard", site.id)).contacto).toBeFalsy();

    // Back online: reconnecting starts a sync on its own, so hold the contact PUT until the dialog
    // has been exercised; "Sincronizar primero" closes it and the queue drains once released.
    let release!: () => void;
    const held = new Promise<void>((r) => (release = r));
    await page.route("**/api/v1/sitios/*/contacto", async (route) => {
      await held;
      await route.continue();
    });
    await context.setOffline(false);
    await page.getByRole("button", { name: "Salir" }).click();
    await expect(dialog).toBeVisible();
    await dialog.getByRole("button", { name: "Sincronizar primero" }).click();
    await expect(dialog).toBeHidden();
    release();
    // "Sincronizando…" also lacks "por enviar": wait for the settled state before reading the server.
    await expect(page.getByTestId("sync-now")).toContainText("Al día", { timeout: 20_000 });
    expect((await detalle("ard", site.id)).contacto).toBeTruthy();

    // Nothing pending: Salir signs out without asking.
    await page.getByRole("button", { name: "Salir" }).click();
    await expect(page.getByTestId("dialog-salir")).toHaveCount(0);
    await expect(page.getByTestId("dev-user-ard")).toBeVisible();
  });
});
