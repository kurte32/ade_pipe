import type { components } from "@pipeline/api-client";

export type SitioDetail = components["schemas"]["SitioDetail"];
export type SitioListItem = components["schemas"]["SitioListItem"];
export type SitioDelta = components["schemas"]["SitioDelta"];
export type ArchivoOut = components["schemas"]["ArchivoOut"];
export type ArchivoMeta = components["schemas"]["ArchivoMeta"];
export type SubidaOut = components["schemas"]["SubidaOut"];
export type PartesOut = components["schemas"]["PartesOut"];
export type Catalogos = components["schemas"]["Catalogos"];
export type NotificacionList = components["schemas"]["NotificacionList"];
export type NotificacionOut = components["schemas"]["NotificacionOut"];
export type HistorialItem = components["schemas"]["HistorialItem"];
export type ContactoIn = components["schemas"]["ContactoIn"];
export type VisitaIn = components["schemas"]["VisitaIn"];
export type ContactoResponse = components["schemas"]["ContactoResponse"];
export type VisitaResponse = components["schemas"]["VisitaResponse"];
export type TransicionIn = components["schemas"]["TransicionIn"];

export const ESTATUS_ORDER = [
  "sitio_prospectado",
  "dueno_localizado",
  "primera_visita",
  "recepcion_documentos",
] as const;

export function nextEstatus(current: string): string | null {
  const idx = (ESTATUS_ORDER as readonly string[]).indexOf(current);
  if (idx < 0 || idx + 1 >= ESTATUS_ORDER.length) return null;
  return ESTATUS_ORDER[idx + 1] ?? null;
}

export function asNumber(v: string | number | null | undefined): number | null {
  if (v === null || v === undefined || v === "") return null;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}
