/** Pipeline order (TDD section 7). Terminal statuses are not part of the forward chain. */
export const ESTATUS_ORDER = [
  "sitio_prospectado",
  "dueno_localizado",
  "primera_visita",
  "recepcion_documentos",
] as const;

export type EstatusPipeline = (typeof ESTATUS_ORDER)[number];

/** Statuses an administrator may return a site to: strictly earlier than the current one. */
export function estatusAnteriores(actual: string): string[] {
  const idx = (ESTATUS_ORDER as readonly string[]).indexOf(actual);
  if (idx <= 0) return [];
  return ESTATUS_ORDER.slice(0, idx);
}

export function esTerminal(estatus: string): boolean {
  return !(ESTATUS_ORDER as readonly string[]).includes(estatus);
}

export const REGIONES = ["Xalapa", "Azcapotzalco"] as const;
