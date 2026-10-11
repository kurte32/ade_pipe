import { AUDITORIA_ACCIONES, AUDITORIA_ENTIDADES, Icon, PageHeader, ProblemAlert, Spinner, formatMexicoCity, usePageTitle } from "@pipeline/ui";
import { useInfiniteQuery } from "@tanstack/react-query";
import { useState } from "react";

import { useApi } from "../api";
import { localToUtcIso } from "../lib/dates";
import { useCoordinadores, useEquivalencias } from "../lib/equivalencias";
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
  usePageTitle("Auditoría");
  const api = useApi();
  const coords = useCoordinadores();
  const equivalencias = useEquivalencias();
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
  const active = Object.values(filters).some(Boolean);

  return (
    <main>
      <PageHeader title="Auditoría" description="Bitácora inalterable de cada escritura y cada descarga. Filtra por quién, qué y cuándo." />
      <form
        className="filters"
        onSubmit={(e) => {
          e.preventDefault();
          setFilters(draft);
        }}
      >
        <label>
          Usuario
          <select value={draft.usuario_oid} onChange={(e) => setDraft({ ...draft, usuario_oid: e.target.value })}>
            <option value="">Todos</option>
            {(equivalencias.data ?? [])
              .filter((c) => c.oid)
              .map((c) => (
                <option key={c.usuario_codigo} value={c.oid ?? ""}>
                  {c.usuario_codigo} · {c.nombre ?? c.correo}
                </option>
              ))}
          </select>
        </label>
        <label>
          Acción
          <input value={draft.accion} list="aud-acciones" data-testid="aud-accion" onChange={(e) => setDraft({ ...draft, accion: e.target.value })} placeholder="Todas" />
          <datalist id="aud-acciones">
            {AUDITORIA_ACCIONES.map((a) => (
              <option key={a} value={a} />
            ))}
          </datalist>
        </label>
        <label>
          Entidad
          <input value={draft.entidad} list="aud-entidades" onChange={(e) => setDraft({ ...draft, entidad: e.target.value })} placeholder="Todas" />
          <datalist id="aud-entidades">
            {AUDITORIA_ENTIDADES.map((a) => (
              <option key={a} value={a} />
            ))}
          </datalist>
        </label>
        <label>
          Id de entidad
          <input value={draft.entidad_id} onChange={(e) => setDraft({ ...draft, entidad_id: e.target.value })} placeholder="p. ej. 416" />
        </label>
        <label>
          Desde
          <input type="datetime-local" value={draft.desde} onChange={(e) => setDraft({ ...draft, desde: e.target.value })} />
        </label>
        <label>
          Hasta
          <input type="datetime-local" value={draft.hasta} onChange={(e) => setDraft({ ...draft, hasta: e.target.value })} />
        </label>
        <div className="filter-actions">
          <button type="submit" className="secondary" data-testid="aud-filtrar">
            <Icon name="search" size={16} /> Filtrar
          </button>
          {active || Object.values(draft).some(Boolean) ? (
            <button
              type="button"
              className="ghost"
              onClick={() => {
                setDraft(EMPTY);
                setFilters(EMPTY);
              }}
            >
              Limpiar
            </button>
          ) : null}
        </div>
      </form>

      {q.isPending ? <Spinner /> : null}
      {q.isError ? <ProblemAlert error={q.error} onRetry={() => void q.refetch()} /> : null}
      {q.data ? (
        <div className="table-wrap">
          <table data-testid="auditoria-table">
            <thead>
              <tr>
                <th scope="col">Fecha</th>
                <th scope="col">Usuario</th>
                <th scope="col">Acción</th>
                <th scope="col">Entidad</th>
                <th scope="col">Id</th>
                <th scope="col">Detalle</th>
              </tr>
            </thead>
            <tbody>
              {items.map((a) => {
                const name = coords.nombrePorOid(a.usuario_oid);
                return (
                  <tr key={a.id} data-testid="aud-row">
                    <td className="nowrap">{formatMexicoCity(a.fecha_utc)}</td>
                    <td>
                      <span className="aud-user" title={a.usuario_oid}>
                        {name ?? (a.rol === "Admin" ? "Administrador" : a.rol)}
                        <br />
                        <small>
                          {a.rol} · {a.usuario_oid.slice(0, 8)}…
                        </small>
                      </span>
                    </td>
                    <td>
                      <code>{a.accion}</code>
                    </td>
                    <td>{a.entidad}</td>
                    <td className="cell-id">{a.entidad_id}</td>
                    <td>
                      {a.detalle || a.correlation_id ? (
                        <>
                          <button type="button" className="ghost small" onClick={() => setOpen({ ...open, [a.id]: !open[a.id] })} aria-expanded={!!open[a.id]}>
                            {open[a.id] ? "Ocultar" : "Ver"}
                          </button>
                          {open[a.id] ? (
                            <>
                              {a.correlation_id ? (
                                <div className="muted small">
                                  Correlación <code>{a.correlation_id}</code>
                                </div>
                              ) : null}
                              {a.detalle ? <pre className="json">{JSON.stringify(a.detalle, null, 2)}</pre> : null}
                            </>
                          ) : null}
                        </>
                      ) : (
                        ""
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {items.length === 0 ? <p className="muted" style={{ padding: "var(--space-4)" }}>Sin registros para este filtro.</p> : null}
          <div className="table-foot">
            <span>
              {items.length} registro{items.length === 1 ? "" : "s"}
              {q.hasNextPage ? " mostrados; hay más" : ""}
            </span>
            {q.hasNextPage ? (
              <button type="button" className="secondary small" disabled={q.isFetchingNextPage} onClick={() => void q.fetchNextPage()}>
                Cargar más
              </button>
            ) : null}
          </div>
        </div>
      ) : null}
    </main>
  );
}
