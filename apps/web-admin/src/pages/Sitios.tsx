import { ESTATUS_LABELS, EstatusBadge, ProblemAlert, Spinner, formatMexicoCity } from "@pipeline/ui";
import { useInfiniteQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { useApi } from "../api";
import { REGIONES } from "../lib/estatus";
import type { SitioPage } from "../lib/types";

interface Filters {
  region: string;
  estatus: string;
  q: string;
  incluirNoVigentes: boolean;
}

function buildQuery(f: Filters, cursor?: string): string {
  const p = new URLSearchParams();
  p.set("limit", "50");
  if (f.region) p.set("region", f.region);
  if (f.estatus) p.set("estatus", f.estatus);
  if (f.q) p.set("q", f.q);
  if (f.incluirNoVigentes) p.set("incluir_no_vigentes", "true");
  if (cursor) p.set("cursor", cursor);
  return p.toString();
}

export function Sitios() {
  const api = useApi();
  const [draft, setDraft] = useState<Filters>({ region: "", estatus: "", q: "", incluirNoVigentes: false });
  const [filters, setFilters] = useState<Filters>(draft);

  const q = useInfiniteQuery({
    queryKey: ["sitios", filters],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) => api.get<SitioPage>(`/api/v1/sitios?${buildQuery(filters, pageParam)}`),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
  const items = q.data?.pages.flatMap((p) => p.items) ?? [];

  return (
    <main>
      <h1>Sitios</h1>
      <form
        className="filters"
        onSubmit={(e) => {
          e.preventDefault();
          setFilters(draft);
        }}
      >
        <label>
          Región
          <select value={draft.region} onChange={(e) => setDraft({ ...draft, region: e.target.value })}>
            <option value="">Todas</option>
            {REGIONES.map((r) => (
              <option key={r}>{r}</option>
            ))}
          </select>
        </label>
        <label>
          Estatus
          <select value={draft.estatus} onChange={(e) => setDraft({ ...draft, estatus: e.target.value })}>
            <option value="">Todos</option>
            {Object.entries(ESTATUS_LABELS).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </label>
        <label>
          Buscar por nombre
          <input
            type="search"
            value={draft.q}
            maxLength={100}
            data-testid="sitios-search"
            onChange={(e) => setDraft({ ...draft, q: e.target.value })}
          />
        </label>
        <label className="check">
          <input
            type="checkbox"
            checked={draft.incluirNoVigentes}
            onChange={(e) => setDraft({ ...draft, incluirNoVigentes: e.target.checked })}
          />{" "}
          Incluir no vigentes
        </label>
        <button type="submit">Filtrar</button>
      </form>

      {q.isPending ? <Spinner label="Cargando sitios" /> : null}
      {q.isError ? <ProblemAlert error={q.error} onRetry={() => void q.refetch()} /> : null}
      {q.data ? (
        <div className="table-wrap">
          <table data-testid="sitios-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Nombre</th>
                <th>Región</th>
                <th>Estatus</th>
                <th>Coordinador</th>
                <th>Campos</th>
                <th>Actualizado</th>
                <th>Revisión</th>
              </tr>
            </thead>
            <tbody>
              {items.map((s) => (
                <tr key={s.id} data-testid={`sitio-row-${s.id}`}>
                  <td>{s.origen_id}</td>
                  <td>
                    <Link to={`/sitios/${s.id}`}>{s.nombre}</Link>
                    {!s.vigente ? <span className="tag">no vigente</span> : null}
                  </td>
                  <td>{s.region}</td>
                  <td>
                    <EstatusBadge estatus={s.estatus} devuelto={s.devuelto} />
                  </td>
                  <td data-testid="col-coordinador">{s.usuario_codigo}</td>
                  <td>
                    {s.campos_capturados}/{s.campos_total}
                  </td>
                  <td className="nowrap">{formatMexicoCity(s.actualizado_utc)}</td>
                  <td>{s.en_revision_admin ? <span className="tag tag-advertencia">pendiente</span> : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {items.length === 0 ? <p className="muted">Sin resultados.</p> : null}
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
