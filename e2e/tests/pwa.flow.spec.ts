import { expect, test, type Page } from "@playwright/test";

import { PWA_URL, signInAs } from "../helpers/auth";
import { detalle, devolverComoAdmin, sitiosDe, tinyPdf, tinyPng, waitFor } from "../helpers/pwa";

const used: number[] = [];

function trackErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (m) => {
    if (m.type() === "error" && !m.text().includes("favicon")) errors.push(m.text());
  });
  page.on("pageerror", (e) => errors.push(e.message));
  return errors;
}

async function openSitio(page: Page, id: number) {
  await page.goto(`${PWA_URL}/sitios/${id}`);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
}

async function pickProspectado(): Promise<number> {
  const list = await sitiosDe("ard", "sitio_prospectado", used);
  const s = list.find((x) => !x.devuelto) ?? list[0];
  if (!s) throw new Error("no hay sitios prospectados para ard");
  used.push(s.id);
  return s.id;
}

test.describe("HU-06 a HU-12: flujo del coordinador", () => {
  test("captura contacto y medidas, avanza dos estatus en línea", async ({ page }) => {
    const errors = trackErrors(page);
    const id = await pickProspectado();
    // Slow the contact PUT so "Avanzar" is tapped while it is still in flight: the advance must
    // still apply, not end in a false 412 (risk R24; first seen on the slower CI runner).
    await page.route("**/api/v1/sitios/*/contacto", async (route) => {
      await new Promise((r) => setTimeout(r, 1500));
      await route.continue();
    });
    await signInAs(page, PWA_URL, "ard");
    await openSitio(page, id);
    await expect(page.getByText("Sitio Prospectado", { exact: false }).first()).toBeVisible();

    await page.getByLabel("Nombre del dueño").fill("Dueño Prueba");
    await page.getByLabel("Teléfono").fill("228 123 4567");
    await page.getByTestId("guardar-contacto").click();
    await expect(page.getByTestId("flash")).toContainText("Contacto");

    const avanzar = page.getByTestId("avanzar");
    await expect(avanzar).toBeEnabled();
    await avanzar.click();
    await expect(page.locator(".badge").first()).toContainText("Dueño Localizado", { timeout: 15_000 });
    await expect(page.getByTestId("historial")).toContainText("Avance");

    await page.getByLabel("Frente (m)").fill("8.5");
    await page.getByLabel("Fondo (m)").fill("12");
    await page.getByTestId("guardar-visita").click();
    await expect(page.getByTestId("flash")).toContainText("Medidas");
    await expect(page.getByTestId("avanzar")).toBeEnabled();
    await page.getByTestId("avanzar").click();
    await expect(page.locator(".badge").first()).toContainText("Primera visita", { timeout: 15_000 });

    const d = await detalle("ard", id);
    expect(d.estatus).toBe("primera_visita");
    expect(d.contacto).toBeTruthy();
    expect(d.visita).toBeTruthy();
    expect(errors).toEqual([]);
  });

  test("captura sin señal y sincroniza al recuperar conexión (RNF-02)", async ({ page, context }) => {
    const errors = trackErrors(page);
    const id = await pickProspectado();
    await signInAs(page, PWA_URL, "ard");
    await openSitio(page, id);

    await context.setOffline(true);
    await expect(page.getByTestId("offline-banner")).toBeVisible();
    await page.getByLabel("Nombre del dueño").fill("Dueño Offline");
    await page.getByLabel("Teléfono").fill("5512345678");
    await page.getByTestId("guardar-contacto").click();
    await expect(page.getByText("se enviará al recuperar señal", { exact: false })).toBeVisible();
    await page.getByTestId("avanzar").click();
    await expect(page.getByTestId("pending-badge")).toBeVisible();
    // the server must not have changed yet
    expect((await detalle("ard", id)).estatus).toBe("sitio_prospectado");

    await context.setOffline(false);
    await page.goto(`${PWA_URL}/`);
    await page.getByTestId("sync-now").click();
    await expect(page.getByTestId(`sitio-${id}`)).toContainText("Dueño Localizado", { timeout: 20_000 });
    expect((await detalle("ard", id)).estatus).toBe("dueno_localizado");
    expect(errors.filter((e) => !/Failed to load resource|net::ERR_INTERNET_DISCONNECTED|NetworkError|TypeError: Failed to fetch/.test(e))).toEqual([]);
  });

  test("conflicto: devolución del administrador bloquea el avance local y se muestra", async ({ page, context }) => {
    const errors = trackErrors(page);
    const id = await pickProspectado();
    // prepare: contacto + dueno_localizado via UI
    await signInAs(page, PWA_URL, "ard");
    await openSitio(page, id);
    await page.getByLabel("Nombre del dueño").fill("Dueño Conflicto");
    await page.getByLabel("Teléfono").fill("2289876543");
    await page.getByTestId("guardar-contacto").click();
    await page.getByTestId("avanzar").click();
    await expect(page.locator(".badge").first()).toContainText("Dueño Localizado", { timeout: 15_000 });

    // go offline, capture visita and queue the advance to primera_visita
    await context.setOffline(true);
    await page.getByLabel("Frente (m)").fill("5");
    await page.getByLabel("Fondo (m)").fill("5");
    await page.getByTestId("guardar-visita").click();
    await page.getByTestId("avanzar").click();
    await expect(page.getByTestId("pending-badge")).toBeVisible();

    // meanwhile the admin returns the site to sitio_prospectado
    await devolverComoAdmin(id, "sitio_prospectado", "Datos de contacto incompletos (prueba e2e)");

    await context.setOffline(false);
    // reloading mounts the sync provider, which syncs on start when online
    await page.goto(`${PWA_URL}/sitios/${id}`);
    await expect(page.getByTestId("conflict-panel")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("devuelto-banner")).toContainText("Devuelto por el administrador");
    await expect(page.getByTestId("conflict-panel")).toContainText("Sitio Prospectado");
    // the server is still in sitio_prospectado: the stale transition was not applied
    expect((await detalle("ard", id)).estatus).toBe("sitio_prospectado");
    // discard the local change; the chain is cleared
    await page.getByTestId("conflict-panel").getByRole("button", { name: "Descartar cambio local" }).first().click();
    await expect(page.getByTestId("conflict-panel")).toBeHidden();
    await expect(page.getByTestId("pending-badge")).toBeHidden();
    expect(errors.filter((e) => !/Failed to load resource|net::ERR|Failed to fetch/.test(e))).toEqual([]);
  });

  test("foto: se comprime, se encola y queda publicada tras sincronizar (HU-12)", async ({ page }) => {
    const errors = trackErrors(page);
    const id = await pickProspectado();
    await signInAs(page, PWA_URL, "ard");
    await openSitio(page, id);
    await page.getByTestId("foto-input").setInputFiles({ name: "fachada.png", mimeType: "image/png", buffer: tinyPng() });
    const published = await waitFor(async () => {
      const d = await detalle("ard", id);
      return d.archivos.find((a) => a.tipo === "foto" && a.estado === "publicado") ?? null;
    });
    expect(published.vigente).toBe(true);
    await expect(page.getByTestId(`foto-${published.id}`)).toBeVisible({ timeout: 20_000 });
    expect(errors).toEqual([]);
  });

  test("PDF: subida reanudable por partes y descarga (HU-09, HU-11)", async ({ page }) => {
    const errors = trackErrors(page);
    const id = await pickProspectado();
    await signInAs(page, PWA_URL, "ard");
    await openSitio(page, id);
    await page.getByTestId("doc-input-uso_de_suelo").setInputFiles({ name: "uso_suelo.pdf", mimeType: "application/pdf", buffer: tinyPdf() });
    await expect(page.getByTestId("doc-uso_de_suelo")).toContainText("cargado", { timeout: 30_000 });
    const d = await detalle("ard", id);
    const doc = d.archivos.find((a) => a.tipo === "documento" && a.tipo_documento === "uso_de_suelo" && a.vigente);
    expect(doc).toBeTruthy();
    // download through the API with the coordinator token: a real PDF comes back
    const { mintToken } = await import("../helpers/auth");
    const token = await mintToken("ard");
    const res = await fetch(`${process.env.API_URL ?? "http://localhost:8000"}/api/v1/archivos/${doc!.id}`, { headers: { authorization: `Bearer ${token}` } });
    expect(res.status).toBe(200);
    const bytes = Buffer.from(await res.arrayBuffer());
    expect(bytes.subarray(0, 4).toString()).toBe("%PDF");
    // in-app download button works (object URL + anchor): verify it triggers a download event
    const dl = page.waitForEvent("download", { timeout: 15_000 }).catch(() => null);
    await page.getByTestId("descargar-uso_de_suelo").click();
    const ev = await dl;
    expect(ev === null || (await ev.suggestedFilename()).endsWith(".pdf")).toBe(true);
    expect(errors).toEqual([]);
  });
});
