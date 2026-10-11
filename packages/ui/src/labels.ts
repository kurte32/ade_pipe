/** Human labels for codes the API returns. Catalog-backed labels (estatus, motivos, documentos) come from the API. */

export const HISTORIAL_TIPO: Record<string, string> = {
  avance: "Avance",
  devolucion: "Devolución",
  carga: "Carga",
  reasignacion: "Reasignación",
  descarte: "Descarte",
  entrega: "Entrega",
};

export const HISTORIAL_ORIGEN: Record<string, string> = {
  carga: "Carga masiva",
  pwa: "App del coordinador",
  admin: "Web de administración",
};

export const LOTE_ESTADO: Record<string, { label: string; tone: string }> = {
  vista_previa: { label: "Vista previa", tone: "tag-warning" },
  confirmado: { label: "Confirmada", tone: "tag-ok" },
  cancelado: { label: "Cancelada", tone: "tag-muted" },
};

export const FILA_RESULTADO: Record<string, { label: string; tone: string }> = {
  ok: { label: "Correcta", tone: "tag-ok" },
  advertencia: { label: "Advertencia", tone: "tag-warning" },
  error: { label: "Error", tone: "tag-error" },
};

export const ACCION_PREVISTA: Record<string, string> = {
  insertar: "Nuevo sitio",
  actualizar: "Actualiza sitio",
  revision: "A revisión",
  omitir: "Se omite",
};

export const AUDITORIA_ACCIONES = [
  "contacto_capturado",
  "visita_capturada",
  "transicion",
  "descarte_propuesto",
  "devolucion",
  "descarte",
  "reasignacion",
  "carga_creada",
  "carga_decision",
  "carga_confirmada",
  "carga_cancelada",
  "equivalencia_actualizada",
  "subida_iniciada",
  "subida_cancelada",
  "archivo_publicado",
  "archivo_retirado",
  "archivo_descargado",
  "archivo_purgado",
  "subida_expirada",
  "subida_escaneando",
  "purga_bloqueada",
  "notificacion_enviada",
  "notificacion_fallida",
];

export const AUDITORIA_ENTIDADES = ["sitio", "carga_lote", "coordinador_equivalencia", "sitio_archivo", "subida_sesion"];

export function label(map: Record<string, string>, code: string | null | undefined): string {
  if (!code) return "";
  return map[code] ?? code;
}

/** "Sin estatus" is a legitimate value of the POTENCIAL column; read it as "not defined". */
export function potencialLabel(p: string | null | undefined): string {
  if (!p || p === "Sin estatus") return "Sin definir";
  return p;
}

export function formatMb(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

/** Plain-language meaning of each audit action, for tooltips and the filter list (UX-AUDIT). */
export const AUDITORIA_ACCION_LABELS: Record<string, string> = {
  contacto_capturado: "El coordinador guardó el contacto del dueño",
  visita_capturada: "El coordinador guardó las medidas de la visita",
  transicion: "El coordinador avanzó el estatus del sitio",
  descarte_propuesto: "El coordinador propuso descartar el sitio",
  devolucion: "El administrador devolvió el sitio a un estatus anterior",
  descarte: "El administrador descartó el sitio",
  reasignacion: "El sitio cambió de coordinador",
  carga_creada: "Se subió un archivo de carga (vista previa)",
  carga_decision: "El administrador aprobó o excluyó filas con advertencia",
  carga_confirmada: "La carga se confirmó y sus filas entraron al pipeline",
  carga_cancelada: "La carga se canceló sin confirmar",
  equivalencia_actualizada: "Cambió la tabla usuario → correo",
  subida_iniciada: "Empezó la subida de un archivo",
  subida_cancelada: "Se canceló una subida",
  subida_expirada: "Una subida sin terminar expiró y se limpió",
  subida_escaneando: "El archivo espera el resultado del antimalware",
  archivo_publicado: "El archivo quedó validado y guardado",
  archivo_retirado: "El coordinador retiró un archivo (versión no vigente)",
  archivo_descargado: "Alguien descargó un archivo",
  archivo_rechazado_malware: "El antimalware rechazó un archivo",
  archivo_purgado: "La retención purgó un archivo",
  purga_bloqueada: "Una retención legal impidió purgar un archivo",
  notificacion_enviada: "Se envió el aviso de Teams",
  notificacion_fallida: "El aviso de Teams agotó sus reintentos",
};
