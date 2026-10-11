import { ESTATUS_LABELS, EstatusBadge, Icon, PageHeader, ProblemAlert, Spinner, formatMexicoCity, usePageTitle } from "@pipeline/ui";
import { useInfiniteQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { useApi } from "../api";
import { useCoordinadores } from "../lib/equivalencias";
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
  usePageTitle("Sitios");
  const api = useApi();
  const coords = useCoordinadores();
  const [params] = useSearchParams();
  const initial: Filters = { region: "", estatus: params.get("estatus") ?? "", q: "", incluirNoVigentes: false };
  const [draft, setDraft] = useState<Filters>(initial);
  const [filters, setFilters] = useState<Filters>(initial);
  useEffect(() => {
    const estatus = params.get("estatus") ?? "";
    setDraft((d) => ({ ...d, estatus }));
    setFilters((f) => ({ ...f, estatus }));
  }, [params]);

  const q = useInfiniteQuery({
    queryKey: ["sitios", filters],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) => api.get<SitioPage>(`/api/v1/sitios?${buildQuery(filters, pageParam)}`),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
  const items = q.data?.pages.flatMap((p) => p.items) ?? [];

  // Selects and the checkbox apply immediately; the text search applies with Enter or "Filtrar".
  const applyNow = (patch: Partial<Filters>) => {
    const next = { ...draft, ...patch };
    setDraft(next);
    setFilters(next);
  };

  return (
    <main>
      <PageHeader title="Sitios" description="Todos los sitios del pipeline, de todos los coordinadores." />
      <form
        className="filters"
        onSubmit={(e) => {
          e.preventDefault();
          setFilters(draft);
        }}
      >
        <label>
          Región
          <select value={draft.region} onChange={(e) => applyNow({ region: e.target.value })}>
            <option value="">Todas</option>
            {REGIONES.map((r) => (
              <option key={r}>{r}</option>
            ))}
          </select>
        </label>
        <label>
          Estatus
          <select value={draft.estatus} onChange={(e) => applyNow({ estatus: e.target.value })}>
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
            placeholder="Calle, avenida…"
            onChange={(e) => setDraft({ ...draft, q: e.target.value })}
          />
        </label>
        <label className="check">
          <input type="checkbox" checked={draft.incluirNoVigentes} onChange={(e) => applyNow({ incluirNoVigentes: e.target.checked })} /> Incluir no vigentes
        </label>
        <div className="filter-actions">
          <button type="submit" className="secondary">
            <Icon name="search" size={16} /> Filtrar
          </button>
        </div>
      </form>

      {q.isPending ? <Spinner label="Cargando sitios" /> : null}
      {q.isError ? <ProblemAlert error={q.error} onRetry={() => void q.refetch()} /> : null}
      {q.data ? (
        <>
          <div className="table-wrap">
            <table data-testid="sitios-table" className="table-cards">
              <thead>
                <tr>
                  <th scope="col">#</th>
                  <th scope="col">Nombre</th>
                  <th scope="col">Región</th>
                  <th scope="col">Estatus</th>
                  <th scope="col">Coordinador</th>
                  <th scope="col" title="Campos capturados en el archivo de origen">
                    Campos
                  </th>
                  <th scope="col">Actualizado</th>
                  <th scope="col">Revisión</th>
                </tr>
              </thead>
              <tbody>
                {items.map((s) => (
                  <tr key={s.id} data-testid={`sitio-row-${s.id}`} className={s.en_revision_admin ? "is-attention" : undefined}>
                    <td className="num" data-label="#">{s.origen_id}</td>
                    <td className="cell-name" data-label="Nombre">
                      <Link to={`/sitios/${s.id}`}>{s.nombre}</Link>
                      {!s.vigente ? <span className="tag tag-muted" style={{ marginLeft: 6 }}>no vigente</span> : null}
                    </td>
                    <td data-label="Región">{s.region}</td>
                    <td data-label="Estatus">
                      <EstatusBadge estatus={s.estatus} devuelto={s.devuelto} />
                    </td>
                    <td title={coords.nombre(s.usuario_codigo)} data-label="Coordinador">
                      <span data-testid="col-coordinador">{s.usuario_codigo}</span>
                      {coords.byCode[s.usuario_codigo]?.nombre ? <span className="muted"> · {coords.byCode[s.usuario_codigo]?.nombre?.split(" ")[0]}</span> : null}
                    </td>
                    <td className="cell-tight" data-label="Campos">
                      <span className="campos" title={`${s.campos_capturados} de ${s.campos_total} campos con dato en el archivo`}>
                        <span className="bar" aria-hidden="true">
                          <i style={{ width: `${Math.round((s.campos_capturados / Math.max(1, s.campos_total)) * 100)}%` }} />
                        </span>
                        {s.campos_capturados}/{s.campos_total}
                      </span>
                    </td>
                    <td className="nowrap" data-label="Actualizado">{formatMexicoCity(s.actualizado_utc)}</td>
                    <td data-label="Revisión">{s.en_revision_admin ? <span className="tag tag-warning">pendiente</span> : ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {items.length === 0 ? <p className="muted" style={{ padding: "var(--space-4)" }}>Sin resultados.</p> : null}
            <div className="table-foot">
              <span>
                {items.length} sitio{items.length === 1 ? "" : "s"}
                {q.hasNextPage ? " mostrados; hay más" : ""}
              </span>
              {q.hasNextPage ? (
                <button type="button" className="secondary small" disabled={q.isFetchingNextPage} onClick={() => void q.fetchNextPage()}>
                  {q.isFetchingNextPage ? "Cargando…" : "Cargar más"}
                </button>
              ) : null}
            </div>
          </div>
        </>
      ) : null}
    </main>
  );
}
