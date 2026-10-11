import { ESTATUS_LABELS, ProblemAlert, Spinner, formatMexicoCity } from "@pipeline/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { useApi } from "../api";
import { getDb, getMeta, setMeta } from "../db/schema";
import type { NotificacionList, NotificacionOut } from "../lib/types";
import { useSync } from "../sync/context";

const KEY = "notificaciones";

export function Notificaciones() {
  const api = useApi();
  const qc = useQueryClient();
  const { online } = useSync();
  const q = useQuery({
    queryKey: ["notificaciones"],
    queryFn: async () => {
      try {
        const data = await api.get<NotificacionList>("/api/v1/notificaciones");
        await setMeta(getDb(), KEY, data);
        return data;
      } catch (e) {
        const cached = await getMeta<NotificacionList>(getDb(), KEY);
        if (cached) return cached;
        throw e;
      }
    },
    retry: 0,
  });
  const leer = useMutation({
    mutationFn: (id: number) => api.post<NotificacionOut>(`/api/v1/notificaciones/${id}/leer`),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["notificaciones"] }),
  });

  if (q.isPending) return <Spinner label="Cargando avisos" />;
  if (q.isError) return <ProblemAlert error={q.error} onRetry={() => void q.refetch()} />;
  return (
    <main>
      <h1>Avisos</h1>
      {!online ? <p className="muted">Mostrando los avisos guardados.</p> : null}
      {q.data.items.length === 0 ? <p className="muted">No tienes avisos.</p> : null}
      <ul className="list" data-testid="notificaciones">
        {q.data.items.map((n) => {
          const c = n.cuerpo as Record<string, unknown>;
          return (
            <li key={n.id} style={{ padding: 12, opacity: n.leida ? 0.7 : 1 }} data-testid={`notificacion-${n.id}`}>
              <strong>{String(c["titulo"] ?? "Sitio devuelto")}</strong>
              <p style={{ margin: "4px 0" }}>
                {String(c["sitio_nombre"] ?? c["sitio"] ?? "")}
                {c["estatus_destino"] ? ` → ${ESTATUS_LABELS[String(c["estatus_destino"])] ?? String(c["estatus_destino"])}` : ""}
                {c["motivo"] ? ` · ${String(c["motivo_nombre"] ?? c["motivo"])}` : ""}
              </p>
              <div className="row">
                <span className="muted">{formatMexicoCity(n.creado_utc)}</span>
                <Link to={`/sitios/${n.sitio_id}`}>Ver sitio</Link>
                {!n.leida ? (
                  <button type="button" className="secondary" onClick={() => leer.mutate(n.id)} disabled={!online}>
                    Marcar leído
                  </button>
                ) : null}
              </div>
            </li>
          );
        })}
      </ul>
    </main>
  );
}
