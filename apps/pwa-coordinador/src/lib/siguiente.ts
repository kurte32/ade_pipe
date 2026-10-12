import type { SitioDetail } from "./types";

/** What the coordinator has to do next on a site, in their words. Used in the list and the detail. */
export function siguientePaso(s: Pick<SitioDetail, "estatus" | "devuelto" | "en_revision_admin">): string | null {
  if (s.en_revision_admin) return "En revisión del administrador";
  switch (s.estatus) {
    case "sitio_prospectado":
      return "Localiza al dueño y captura su contacto";
    case "dueno_localizado":
      return "Visita el local y captura las medidas";
    case "primera_visita":
      return "Sube los documentos del inmueble";
    case "recepcion_documentos":
      return "Etapas del coordinador completas";
    default:
      return null;
  }
}
