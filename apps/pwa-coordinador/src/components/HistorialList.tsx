import { ESTATUS_LABELS, formatMexicoCity } from "@pipeline/ui";
import { useQuery } from "@tanstack/react-query";

import { useApi } from "../api";
import type { HistorialItem } from "../lib/types";
import { useSync } from "../sync/context";

const TIPO: Record<string, string> = {
  avance: "Avance",
  devolucion: "Devolución",
  carga: "Carga",
  reasignacion: "Reasignación",
  descarte: "Descarte",
};

export function HistorialList({ sitioId, refreshKey }: { sitioId: number; refreshKey: string }) {
  const api = useApi();
  const { online } = useSync();
  const q = useQuery({
    queryKey: ["historial", sitioId, refreshKey],
    queryFn: () => api.get<HistorialItem[]>(`/api/v1/sitios/${sitioId}/historial`),
    enabled: online,
    retry: 0,
  });
  return (
    <section aria-labelledby="hist-h">
      <h2 id="hist-h">Historial</h2>
      {!online ? <p className="muted">El historial se consulta con conexión.</p> : null}
      {q.isError ? <p className="muted">No se pudo cargar el historial.</p> : null}
      <ul className="list" data-testid="historial">
        {(q.data ?? []).map((h) => (
          <li key={h.id} style={{ padding: 10 }}>
            <strong>{TIPO[h.tipo] ?? h.tipo}</strong>: {h.estatus_anterior ? `${ESTATUS_LABELS[h.estatus_anterior] ?? h.estatus_anterior} → ` : ""}
            {ESTATUS_LABELS[h.estatus_nuevo] ?? h.estatus_nuevo}
            <div className="muted">
              {formatMexicoCity(h.fecha_utc)}
              {h.motivo ? ` · ${h.motivo}` : ""}
              {h.comentario ? ` · ${h.comentario}` : ""}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
