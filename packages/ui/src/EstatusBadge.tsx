export const ESTATUS_LABELS: Record<string, string> = {
  sitio_prospectado: "Sitio Prospectado",
  dueno_localizado: "Dueño Localizado",
  primera_visita: "Primera visita",
  recepcion_documentos: "Recepción de documentos",
  descartado: "Descartado",
  entregado: "Entregado",
};

export function EstatusBadge({ estatus, devuelto }: { estatus: string; devuelto?: boolean }) {
  return (
    <span className={`badge badge-${estatus}${devuelto ? " badge-devuelto" : ""}`}>
      {ESTATUS_LABELS[estatus] ?? estatus}
      {devuelto ? " · devuelto" : ""}
    </span>
  );
}
