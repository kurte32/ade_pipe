import { EmptyState, EstatusBadge, ESTATUS_LABELS, Icon, PageHeader, Spinner, usePageTitle } from "@pipeline/ui";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import type { CachedSitio } from "../db/schema";
import { useCatalogos } from "../lib/catalogos";
import { siguientePaso } from "../lib/siguiente";
import { useCachedSitios, useOperaciones } from "../lib/useSitios";
import { useSync } from "../sync/context";

const STAGE_FILTERS = ["sitio_prospectado", "dueno_localizado", "primera_visita", "recepcion_documentos"] as const;

interface Flags {
  pending: number;
  blocked: number;
}

function SitioRow({ cached, flags, catalogoMotivos }: { cached: CachedSitio; flags: Flags | undefined; catalogoMotivos?: Record<string, string> }) {
  const s = cached.detail;
  const attention = s.devuelto || !!flags?.blocked;
  const next = siguientePaso(s);
  return (
    <li className={attention ? "is-attention" : undefined} data-testid={`sitio-${s.id}`}>
      <Link to={`/sitios/${s.id}`} className="list-row site-row">
        <div className="body">
          <span className="list-title">{s.nombre}</span>
          <span className="list-sub">
            #{s.origen_id} · {s.region}
          </span>
          <div className="badges">
            <EstatusBadge estatus={s.estatus} devuelto={s.devuelto} />
            {flags?.pending ? <span className="pending">pendiente de sincronizar</span> : null}
            {flags?.blocked ? <span className="tag tag-error">requiere atención</span> : null}
            {s.en_revision_admin ? <span className="tag tag-info">en revisión</span> : null}
          </div>
          {s.devuelto ? (
            <div className="list-next" style={{ color: "var(--color-brand-strong)" }}>
              <Icon name="alert-circle" size={16} />
              {catalogoMotivos?.[s.devolucion_motivo ?? ""] ?? s.devolucion_motivo ?? "Devuelto"}
              {s.devolucion_comentario ? `: ${s.devolucion_comentario}` : ""}
            </div>
          ) : next ? (
            <div className="list-next">
              <Icon name="arrow-right" size={16} />
              {next}
            </div>
          ) : null}
        </div>
        <Icon name="chevron-right" className="chev" />
      </Link>
    </li>
  );
}

export function MisSitios() {
  usePageTitle("Mis sitios");
  const sitios = useCachedSitios();
  const ops = useOperaciones();
  const sync = useSync();
  const [q, setQ] = useState("");
  const [estatus, setEstatus] = useState("");
  const catalogos = useCatalogos();
  const motivos = useMemo(() => Object.fromEntries(catalogos.motivos_devolucion.map((m) => [m.codigo, m.nombre])), [catalogos]);

  const flagsBySite = useMemo(() => {
    const m = new Map<number, Flags>();
    for (const op of ops ?? []) {
      const e = m.get(op.sitioId) ?? { pending: 0, blocked: 0 };
      if (op.estado === "bloqueada" || op.estado === "error") e.blocked += 1;
      else e.pending += 1;
      m.set(op.sitioId, e);
    }
    return m;
  }, [ops]);

  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const s of sitios ?? []) c[s.detail.estatus] = (c[s.detail.estatus] ?? 0) + 1;
    return c;
  }, [sitios]);

  const { attention, rest } = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const matches = (s: CachedSitio) =>
      (!estatus || s.detail.estatus === estatus) &&
      (!needle || s.detail.nombre.toLowerCase().includes(needle) || String(s.detail.origen_id).includes(needle));
    const needsAttention = (s: CachedSitio) => s.detail.devuelto || !!flagsBySite.get(s.id)?.blocked;
    const all = (sitios ?? []).filter(matches);
    return { attention: all.filter(needsAttention), rest: all.filter((s) => !needsAttention(s)) };
  }, [sitios, flagsBySite, q, estatus]);

  if (sitios === undefined) return <Spinner label="Cargando sitios" />;

  const terminalCount = (sitios ?? []).filter((s) => !(STAGE_FILTERS as readonly string[]).includes(s.detail.estatus)).length;

  return (
    <main className="narrow">
      <PageHeader
        title="Mis sitios"
        description={sitios.length ? `${sitios.length} sitios asignados` : undefined}
        actions={
          sync.online ? (
            <button
              type="button"
              className="ghost small"
              onClick={() => void sync.redownload()}
              disabled={sync.syncing}
              title="Vuelve a descargar todos tus sitios del servidor. Tus capturas pendientes se conservan."
              data-testid="redownload"
            >
              <Icon name="refresh" size={16} />
              Volver a descargar
            </button>
          ) : null
        }
      />

      {sitios.length === 0 ? (
        <EmptyState icon="store" title="Todavía no tienes sitios asignados">
          {sync.online
            ? "Cuando el administrador cargue sitios a tu nombre aparecerán aquí. Si esperabas verlos, sincroniza con el botón de arriba."
            : "No hay sitios en la memoria del teléfono. Conéctate para descargarlos."}
        </EmptyState>
      ) : (
        <>
          <div className="site-search">
            <Icon name="search" size={18} />
            <label htmlFor="buscar" className="visually-hidden">
              Buscar por nombre o número
            </label>
            <input id="buscar" type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar por nombre o número" autoComplete="off" />
          </div>
          <div className="chips site-filters" role="group" aria-label="Filtrar por estatus">
            <button type="button" className="chip" aria-pressed={estatus === ""} onClick={() => setEstatus("")}>
              Todos <span className="n">{sitios.length}</span>
            </button>
            {STAGE_FILTERS.map((code) => (
              <button key={code} type="button" className="chip" aria-pressed={estatus === code} onClick={() => setEstatus(estatus === code ? "" : code)}>
                {ESTATUS_LABELS[code]} <span className="n">{counts[code] ?? 0}</span>
              </button>
            ))}
            {terminalCount
              ? ["descartado", "entregado"]
                  .filter((code) => counts[code])
                  .map((code) => (
                    <button key={code} type="button" className="chip" aria-pressed={estatus === code} onClick={() => setEstatus(estatus === code ? "" : code)}>
                      {ESTATUS_LABELS[code]} <span className="n">{counts[code]}</span>
                    </button>
                  ))
              : null}
          </div>

          {attention.length ? (
            <section aria-labelledby="atencion-h">
              <h2 id="atencion-h">Requieren tu atención</h2>
              <p className="section-sub">Devueltos por el administrador o con cambios que no se pudieron enviar.</p>
              <ul className="list">
                {attention.map((c) => (
                  <SitioRow key={c.id} cached={c} flags={flagsBySite.get(c.id)} catalogoMotivos={motivos} />
                ))}
              </ul>
            </section>
          ) : null}

          {attention.length && rest.length ? <h2>Los demás</h2> : null}
          {attention.length + rest.length === 0 ? (
            <EmptyState icon="search" title="Ningún sitio coincide">
              Prueba con otro nombre o quita el filtro de estatus.
            </EmptyState>
          ) : null}
          <ul className="list" data-testid="sitios-list">
            {rest.map((c) => (
              <SitioRow key={c.id} cached={c} flags={flagsBySite.get(c.id)} catalogoMotivos={motivos} />
            ))}
          </ul>
        </>
      )}
    </main>
  );
}
