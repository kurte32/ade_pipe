import { expect, type Page } from "@playwright/test";

import { ADMIN_CLIENT_ID, ADMIN_URL, PWA_CLIENT_ID, api, mintToken, signInAs } from "./auth";
import { inPool } from "./pool";

export interface SitioLite {
  id: number;
  origen_id: number;
  nombre: string;
  estatus: string;
  devuelto: boolean;
  usuario_codigo: string;
  etag: string;
}

export async function signInAdmin(page: Page): Promise<void> {
  await signInAs(page, ADMIN_URL, "adm");
  await expect(page.getByTestId("account-name")).toContainText("Administrador");
}

/** Collect console errors (favicon noise ignored). */
export function trackConsoleErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (m) => {
    const text = m.text();
    // Chromium logs expected 4xx responses (validation errors under test) as console errors; keep 5xx.
    const expected4xx = /Failed to load resource: the server responded with a status of 4\d\d/.test(text);
    if (m.type() === "error" && !text.includes("favicon") && !expected4xx) errors.push(text);
  });
  page.on("pageerror", (e) => errors.push(e.message));
  return errors;
}

export async function adminToken(): Promise<string> {
  return mintToken("adm", ADMIN_CLIENT_ID);
}

export async function coordToken(code: string): Promise<string> {
  return mintToken(code, PWA_CLIENT_ID);
}

/** Find one site of a coordinator in the given status that is not devuelto and not under review. */
export async function findSitio(code: string, estatus: string): Promise<SitioLite | null> {
  const token = await coordToken(code);
  const r = await api<{ items: SitioLite[] }>("GET", `/api/v1/sitios?limit=200&estatus=${estatus}`, token);
  // Only the per-run pool, never seeded sites (audit C7).
  const candidates = r.data.items.filter((s) => !s.devuelto && inPool(s.origen_id));
  return candidates[0] ?? null;
}

/** As the coordinator: capture contact and advance prospectado -> dueno_localizado. Returns the site id. */
export async function advanceToDuenoLocalizado(code: string): Promise<number> {
  const token = await coordToken(code);
  const s = await findSitio(code, "sitio_prospectado");
  if (!s) throw new Error(`no sitio_prospectado for ${code}`);
  const contacto = await api<{ etag: string }>("PUT", `/api/v1/sitios/${s.id}/contacto`, token, {
    nombre: "Dueño E2E",
    telefono: "2281234567",
  });
  if (contacto.status !== 200) throw new Error(`contacto ${contacto.status} ${JSON.stringify(contacto.data)}`);
  const tr = await api<unknown>(
    "POST",
    `/api/v1/sitios/${s.id}/transiciones`,
    token,
    { estatus_destino: "dueno_localizado" },
    { "if-match": `"${contacto.data.etag}"` },
  );
  if (tr.status !== 201) throw new Error(`transicion ${tr.status} ${JSON.stringify(tr.data)}`);
  return s.id;
}

/** CSV with new origen_ids for a load test. One suspicious name (warning) and one bad POTENCIAL (error). */
export function buildE2ECsv(base: number): { csv: string; names: string[] } {
  const header = "#,USUARIO,REGION,SITIO,COORDENADAS,GPS,POTENCIAL,CAMPOS,FECHA";
  const tag = `E2E-${base}`;
  const names = [`Sitio ${tag} A`, `Sitio ${tag} B`, `Sitio ${tag} C`, `Prueba ${tag}`, `Sitio ${tag} E`];
  const rows = [
    `${base},ard,Xalapa,${names[0]},"19.531${base % 1000}, -96.931${base % 1000}",5.1,Alto,24/24,10/01/2026 09:00:00`,
    `${base + 1},ard,Xalapa,${names[1]},"19.541${base % 1000}, -96.941${base % 1000}",,Medio,24/24,10/02/2026 10:30:00`,
    `${base + 2},usa,Azcapotzalco,${names[2]},"19.482${base % 1000}, -99.182${base % 1000}",0,Bajo,24/24,10/03/2026 11:00:00`,
    `${base + 3},ard,Xalapa,${names[3]},"19.551${base % 1000}, -96.951${base % 1000}",3,Alto,24/24,10/04/2026 12:00:00`,
    `${base + 4},ard,Xalapa,${names[4]},"19.561${base % 1000}, -96.961${base % 1000}",3,Altísimo,24/24,10/05/2026 13:00:00`,
  ];
  return { csv: [header, ...rows].join("\n") + "\n", names };
}
