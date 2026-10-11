import { ADMIN_CLIENT_ID, api, mintToken } from "./auth";
import { inPool } from "./pool";

export interface SitioLite {
  id: number;
  origen_id: number;
  nombre: string;
  estatus: string;
  etag: string;
  devuelto: boolean;
}

interface Page<T> {
  items: T[];
  next_cursor: string | null;
}

/** Pool sites of a coordinator filtered by estatus, via the API (test setup). Seeded data is untouched. */
export async function sitiosDe(userCode: string, estatus?: string, exclude: number[] = []): Promise<SitioLite[]> {
  const token = await mintToken(userCode);
  const out: SitioLite[] = [];
  let cursor: string | null = null;
  do {
    const qs: string = `?limit=200${estatus ? `&estatus=${estatus}` : ""}${cursor ? `&cursor=${cursor}` : ""}`;
    const r: { status: number; data: Page<SitioLite> } = await api<Page<SitioLite>>("GET", `/api/v1/sitios${qs}`, token);
    if (r.status !== 200) throw new Error(`list failed ${r.status}`);
    out.push(...r.data.items);
    cursor = r.data.next_cursor;
  } while (cursor);
  return out.filter((s) => inPool(s.origen_id) && !exclude.includes(s.id));
}

export async function detalle(userCode: string, id: number): Promise<SitioLite & { contacto: unknown; visita: unknown; archivos: { id: string; tipo: string; tipo_documento: string | null; vigente: boolean; estado: string }[] }> {
  const token = await mintToken(userCode);
  const r = await api<SitioLite & { contacto: unknown; visita: unknown; archivos: never[] }>("GET", `/api/v1/sitios/${id}`, token);
  if (r.status !== 200) throw new Error(`detail failed ${r.status}`);
  return { ...r.data, etag: r.etag?.replace(/"/g, "") ?? r.data.etag };
}

/** Admin returns a site to an earlier status (used to create a conflict). */
export async function devolverComoAdmin(id: number, estatusDestino: string, comentario = "Prueba e2e"): Promise<void> {
  const token = await mintToken("adm", ADMIN_CLIENT_ID);
  const d = await api<SitioLite>("GET", `/api/v1/sitios/${id}`, token);
  const r = await api("POST", `/api/v1/admin/sitios/${id}/devolver`, token, { estatus_destino: estatusDestino, motivo: "calidad_datos", comentario }, {
    "if-match": d.etag ?? `"${d.data.etag}"`,
  });
  if (r.status !== 200) throw new Error(`devolver failed ${r.status} ${JSON.stringify(r.data)}`);
}

/** Minimal valid single-page PDF. */
export function tinyPdf(text = "Prueba e2e"): Buffer {
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
    null,
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
  ];
  const stream = `BT /F1 12 Tf 20 100 Td (${text}) Tj ET`;
  objects[3] = `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`;
  let out = "%PDF-1.4\n";
  const offsets: number[] = [];
  objects.forEach((o, i) => {
    offsets.push(out.length);
    out += `${i + 1} 0 obj\n${o}\nendobj\n`;
  });
  const xref = out.length;
  out += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  for (const off of offsets) out += `${String(off).padStart(10, "0")} 00000 n \n`;
  out += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return Buffer.from(out, "latin1");
}

/** 1x1 red PNG. */
export function tinyPng(): Buffer {
  return Buffer.from(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg==",
    "base64",
  );
}

export async function waitFor<T>(fn: () => Promise<T | null | undefined | false>, timeoutMs = 20_000, every = 500): Promise<T> {
  const start = Date.now();
  for (;;) {
    const v = await fn();
    if (v) return v;
    if (Date.now() - start > timeoutMs) throw new Error("waitFor timeout");
    await new Promise((r) => setTimeout(r, every));
  }
}
