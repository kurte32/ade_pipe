import { ProblemAlert, Spinner, formatMexicoCity } from "@pipeline/ui";
import { useInfiniteQuery } from "@tanstack/react-query";
import { useState } from "react";

import { useApi } from "../api";
import { localToUtcIso } from "../lib/dates";
import type { AuditoriaPage } from "../lib/types";

interface Filters {
  usuario_oid: string;
  entidad: string;
  entidad_id: string;
  accion: string;
  desde: string;
  hasta: string;
}

const EMPTY: Filters = { usuario_oid: "", entidad: "", entidad_id: "", accion: "", desde: "", hasta: "" };

function buildQuery(f: Filters, cursor?: string): string {
  const p = new URLSearchParams();
  p.set("limit", "50");
  if (f.usuario_oid) p.set("usuario_oid", f.usuario_oid.trim());
  if (f.entidad) p.set("entidad", f.entidad.trim());
  if (f.entidad_id) p.set("entidad_id", f.entidad_id.trim());
  if (f.accion) p.set("accion", f.accion.trim());
  const desde = localToUtcIso(f.desde);
  const hasta = localToUtcIso(f.hasta);
  if (desde) p.set("desde", desde);
  if (hasta) p.set("hasta", hasta);
  if (cursor) p.set("cursor", cursor);
  return p.toString();
}

export function Auditoria() {
  const api = useApi();
  const [draft, setDraft] = useState<Filters>(EMPTY);
  const [filters, setFilters] = useState<Filters>(EMPTY);
  const [open, setOpen] = useState<Record<number, boolean>>({});

  const q = useInfiniteQuery({
    queryKey: ["auditoria", filters],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) => api.get<AuditoriaPage>(`/api/v1/admin/auditoria?${buildQuery(filters, pageParam)}`),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
  const items = q.data?.pages.flatMap((p) => p.items) ?? [];

  return (
    <main>
      <h1>Auditoría</h1>
      <form
        className="filters"
        onSubmit={(e) => {
          e.preventDefault();
          setFilters(draft);
        }}
      >
        <label>
          Usuario (oid)
          <input value={draft.usuario_oid} onChange={(e) => setDraft({ ...draft, usuario_oid: e.target.value })} />
        </label>
        <label>
          Entidad
          <input value={draft.entidad} onChange={(e) => setDraft({ ...draft, entidad: e.target.value })} placeholder="sitio, carga_lote…" />
        </label>
        <label>
          Id de entidad
          <input value={draft.entidad_id} onChange={(e) => setDraft({ ...draft, entidad_id: e.target.value })} />
        </label>
        <label>
          Acción
          <input
            value={draft.accion}
            data-testid="aud-accion"
            onChange={(e) => setDraft({ ...draft, accion: e.target.value })}
            placeholder="devolucion, carga_confirmada…"
          />
        </label>
        <label>
          Desde
          <input type="datetime-local" value={draft.desde} onChange={(e) => setDraft({ ...draft, desde: e.target.value })} />
        </label>
        <label>
          Hasta
          <input type="datetime-local" value={draft.hasta} onChange={(e) => setDraft({ ...draft, hasta: e.target.value })} />
        </label>
        <button type="submit" data-testid="aud-filtrar">
          Filtrar
        </button>
        <button
          type="button"
          className="secondary"
          onClick={() => {
            setDraft(EMPTY);
            setFilters(EMPTY);
          }}
        >
          Limpiar
        </button>
      </form>

      {q.isPending ? <Spinner /> : null}
      {q.isError ? <ProblemAlert error={q.error} onRetry={() => void q.refetch()} /> : null}
      {q.data ? (
        <div className="table-wrap">
          <table data-testid="auditoria-table">
            <thead>
              <tr>
                <th>Fecha</th>
                <th>Usuario</th>
                <th>Rol</th>
                <th>Acción</th>
                <th>Entidad</th>
                <th>Id</th>
                <th>Correlación</th>
                <th>Detalle</th>
              </tr>
            </thead>
            <tbody>
              {items.map((a) => (
                <tr key={a.id} data-testid="aud-row">
                  <td className="nowrap">{formatMexicoCity(a.fecha_utc)}</td>
                  <td className="muted" title={a.usuario_oid}>
                    {a.usuario_oid.slice(0, 8)}…
                  </td>
                  <td>{a.rol}</td>
                  <td>
                    <code>{a.accion}</code>
                  </td>
                  <td>{a.entidad}</td>
                  <td>{a.entidad_id}</td>
                  <td className="muted">{a.correlation_id?.slice(0, 8) ?? ""}</td>
                  <td>
                    {a.detalle ? (
                      <>
                        <button type="button" className="secondary" onClick={() => setOpen({ ...open, [a.id]: !open[a.id] })}>
                          {open[a.id] ? "Ocultar" : "Ver"}
                        </button>
                        {open[a.id] ? <pre className="json">{JSON.stringify(a.detalle, null, 2)}</pre> : null}
                      </>
                    ) : (
                      ""
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {items.length === 0 ? <p className="muted">Sin registros para este filtro.</p> : null}
          {q.hasNextPage ? (
            <div className="actions">
              <button type="button" className="secondary" disabled={q.isFetchingNextPage} onClick={() => void q.fetchNextPage()}>
                Cargar más
              </button>
            </div>
          ) : null}
        </div>
      ) : null}
    </main>
  );
}
