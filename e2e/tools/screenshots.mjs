// UX screenshot tool: signs in through the dev user picker and captures every screen of both apps
// at a phone and a desktop viewport. Used for the before/after evidence in docs/ux/UX_VALIDATION.md.
//   node e2e/tools/screenshots.mjs <outDir> [label]
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { join } from "node:path";

const PWA = process.env.PWA_URL ?? "http://localhost:5173";
const ADMIN = process.env.ADMIN_URL ?? "http://localhost:5174";
const out = process.argv[2] ?? "screenshots";
const label = process.argv[3] ?? "";
mkdirSync(out, { recursive: true });

const VIEWPORTS = { phone: { width: 390, height: 844 }, desktop: { width: 1366, height: 900 } };

async function signIn(page, base, code) {
  await page.goto(base + "/");
  const btn = page.getByTestId(`dev-user-${code}`);
  await btn.waitFor({ state: "visible", timeout: 15000 });
  await btn.click();
  await btn.waitFor({ state: "hidden", timeout: 15000 });
}

async function shot(page, name, { full = true } = {}) {
  await page.waitForTimeout(600);
  await page.screenshot({ path: join(out, `${name}${label ? "-" + label : ""}.png`), fullPage: full });
}

async function firstSitioId(page) {
  const href = await page.locator('[data-testid="sitios-list"] a').first().getAttribute("href").catch(() => null);
  return href ? href.split("/").pop() : null;
}

const browser = await chromium.launch();
for (const [vp, size] of Object.entries(VIEWPORTS)) {
  const ctx = await browser.newContext({ viewport: size, deviceScaleFactor: 1, locale: "es-MX" });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => { if (m.type() === "error" && !m.text().includes("favicon")) errors.push(m.text()); });

  // PWA
  await page.goto(PWA + "/");
  await shot(page, `pwa-signin-${vp}`);
  await signIn(page, PWA, "ard");
  await page.getByTestId("sitios-list").waitFor({ timeout: 20000 }).catch(() => {});
  await page.waitForTimeout(1500);
  await shot(page, `pwa-lista-${vp}`);
  const id = await firstSitioId(page);
  if (id) {
    await page.goto(`${PWA}/sitios/${id}`);
    await page.getByRole("heading", { level: 1 }).waitFor();
    await shot(page, `pwa-detalle-${vp}`);
  }
  await page.goto(PWA + "/notificaciones");
  await page.waitForTimeout(800);
  await shot(page, `pwa-avisos-${vp}`);

  // Admin
  await page.goto(ADMIN + "/");
  await shot(page, `admin-signin-${vp}`);
  await signIn(page, ADMIN, "adm");
  await page.waitForTimeout(1500);
  await shot(page, `admin-resumen-${vp}`);
  await page.goto(ADMIN + "/sitios");
  await page.getByTestId("sitios-table").waitFor({ timeout: 20000 }).catch(() => {});
  await shot(page, `admin-sitios-${vp}`);
  const row = await page.locator('[data-testid="sitios-table"] a').first().getAttribute("href").catch(() => null);
  if (row) {
    await page.goto(ADMIN + row);
    await page.getByRole("heading", { level: 1 }).waitFor();
    await page.waitForTimeout(800);
    await shot(page, `admin-sitio-${vp}`);
  }
  await page.goto(ADMIN + "/cargas");
  await page.getByTestId("cargas-table").waitFor({ timeout: 20000 }).catch(() => {});
  await shot(page, `admin-cargas-${vp}`);
  const carga = await page.locator('[data-testid="cargas-table"] a').first().getAttribute("href").catch(() => null);
  if (carga) {
    await page.goto(ADMIN + carga);
    await page.getByTestId("filas-table").waitFor({ timeout: 20000 }).catch(() => {});
    await shot(page, `admin-carga-${vp}`);
  }
  await page.goto(ADMIN + "/equivalencias");
  await page.getByTestId("equivalencias-table").waitFor({ timeout: 20000 }).catch(() => {});
  await shot(page, `admin-equivalencias-${vp}`);
  await page.goto(ADMIN + "/auditoria");
  await page.getByTestId("auditoria-table").waitFor({ timeout: 20000 }).catch(() => {});
  await shot(page, `admin-auditoria-${vp}`);
  if (errors.length) console.log(`[${vp}] console/page errors:`, errors);
  await ctx.close();
}
await browser.close();
console.log("done:", out);
