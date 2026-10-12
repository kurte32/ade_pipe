export const ESTATUS_LABELS: Record<string, string> = {
  sitio_prospectado: "Sitio Prospectado",
  dueno_localizado: "Dueño Localizado",
  primera_visita: "Primera visita",
  recepcion_documentos: "Recepción de documentos",
  descartado: "Descartado",
  entregado: "Entregado",
};

/** Pipeline order (TDD section 7). Terminal statuses are not part of the forward chain. */
export const ESTATUS_ORDER = ["sitio_prospectado", "dueno_localizado", "primera_visita", "recepcion_documentos"] as const;

export function estatusTone(estatus: string): string {
  const idx = (ESTATUS_ORDER as readonly string[]).indexOf(estatus);
  if (idx >= 0) return `stage-${idx + 1}`;
  return "terminal";
}

export function EstatusBadge({ estatus, devuelto }: { estatus: string; devuelto?: boolean }) {
  return (
    <span className={`badge ${estatusTone(estatus)} badge-${estatus}${devuelto ? " badge-devuelto" : ""}`}>
      {ESTATUS_LABELS[estatus] ?? estatus}
      {devuelto ? " · devuelto" : ""}
    </span>
  );
}
