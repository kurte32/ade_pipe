import { ESTATUS_LABELS, HISTORIAL_TIPO, Icon, formatMexicoCity, label } from "@pipeline/ui";
import { useQuery } from "@tanstack/react-query";

import { useApi } from "../api";
import type { HistorialItem } from "../lib/types";
import { useSync } from "../sync/context";

export function HistorialList({ sitioId, refreshKey }: { sitioId: number; refreshKey: string }) {
  const api = useApi();
  const { online } = useSync();
  const q = useQuery({
    queryKey: ["historial", sitioId, refreshKey],
    queryFn: () => api.get<HistorialItem[]>(`/api/v1/sitios/${sitioId}/historial`),
    enabled: online,
    retry: 0,
  });
  const items = q.data ?? [];
  return (
    <section aria-labelledby="hist-h">
      <h2 id="hist-h">Historial</h2>
      {!online ? <p className="muted small">El historial se consulta con señal.</p> : null}
      {q.isError ? <p className="muted small">No se pudo cargar el historial.</p> : null}
      {online && q.isSuccess && items.length === 0 ? <p className="muted small">Sin movimientos todavía.</p> : null}
      <ul className="hist" data-testid="historial">
        {items.map((h) => (
          <li key={h.id}>
            <Icon name={h.tipo === "devolucion" ? "alert-circle" : h.tipo === "carga" ? "upload" : "check"} size={16} />
            <div>
              <strong>{label(HISTORIAL_TIPO, h.tipo)}</strong>
              {": "}
              {h.estatus_anterior ? `${ESTATUS_LABELS[h.estatus_anterior] ?? h.estatus_anterior} → ` : ""}
              {ESTATUS_LABELS[h.estatus_nuevo] ?? h.estatus_nuevo}
              <div className="when">
                {formatMexicoCity(h.fecha_utc)}
                {h.motivo ? ` · ${h.motivo}` : ""}
                {h.comentario ? ` · ${h.comentario}` : ""}
              </div>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
