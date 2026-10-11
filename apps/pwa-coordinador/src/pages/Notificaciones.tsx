import { Alert, EmptyState, ESTATUS_LABELS, Icon, PageHeader, ProblemAlert, Spinner, formatMexicoCity, usePageTitle } from "@pipeline/ui";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { useApi } from "../api";
import { useNotificaciones } from "../lib/notificaciones";
import type { NotificacionOut } from "../lib/types";
import { useSync } from "../sync/context";

export function Notificaciones() {
  usePageTitle("Avisos");
  const api = useApi();
  const qc = useQueryClient();
  const { online } = useSync();
  const q = useNotificaciones();
  const leer = useMutation({
    mutationFn: (id: number) => api.post<NotificacionOut>(`/api/v1/notificaciones/${id}/leer`),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["notificaciones"] }),
  });

  if (q.isPending) return <Spinner label="Cargando avisos" />;
  if (q.isError) return <ProblemAlert error={q.error} onRetry={() => void q.refetch()} />;
  const unread = q.data.items.filter((n) => !n.leida).length;
  return (
    <main className="narrow">
      <PageHeader title="Avisos" description={unread ? `${unread} sin leer` : undefined} />
      {!online ? (
        <Alert tone="neutral" icon="wifi-off">
          Sin señal: se muestran los avisos guardados en el teléfono.
        </Alert>
      ) : null}
      {q.data.items.length === 0 ? (
        <EmptyState icon="bell" title="No tienes avisos">
          Cuando el administrador te devuelva un sitio con un motivo, el aviso aparece aquí y el sitio queda marcado en Mis sitios.
        </EmptyState>
      ) : null}
      <ul className="list" data-testid="notificaciones">
        {q.data.items.map((n) => {
          const c = n.cuerpo as Record<string, unknown>;
          return (
            <li key={n.id} style={{ padding: "var(--space-3) var(--space-4)", opacity: n.leida ? 0.75 : 1 }} data-testid={`notificacion-${n.id}`}>
              <div className="list-row">
                <Icon name={n.leida ? "check-circle" : "alert-circle"} className="chev" />
                <div className="body">
                  <span className="list-title">{String(c["titulo"] ?? "Sitio devuelto")}</span>
                  <p style={{ margin: "2px 0" }}>
                    {String(c["sitio_nombre"] ?? c["sitio"] ?? "")}
                    {c["estatus_destino"] ? ` → ${ESTATUS_LABELS[String(c["estatus_destino"])] ?? String(c["estatus_destino"])}` : ""}
                    {c["motivo"] ? ` · ${String(c["motivo_nombre"] ?? c["motivo"])}` : ""}
                  </p>
                  <div className="cluster">
                    <span className="muted small">{formatMexicoCity(n.creado_utc)}</span>
                    <Link to={`/sitios/${n.sitio_id}`}>Ver sitio</Link>
                    {!n.leida ? (
                      <button type="button" className="ghost small" onClick={() => leer.mutate(n.id)} disabled={!online} title={online ? undefined : "Requiere señal"}>
                        Marcar leído
                      </button>
                    ) : null}
                  </div>
                </div>
              </div>
            </li>
          );
        })}
      </ul>
    </main>
  );
}
