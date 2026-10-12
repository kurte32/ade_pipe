import { ESTATUS_LABELS, ESTATUS_ORDER, EstatusBadge, Icon, LOTE_ESTADO, PageHeader, ProblemAlert, Spinner, formatMexicoCity, usePageTitle } from "@pipeline/ui";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { useApi } from "../api";
import { useCoordinadores } from "../lib/equivalencias";
import type { LoteSummary, SitioPage } from "../lib/types";

const MAX_LIST = 6;

export function Resumen() {
  usePageTitle("Resumen");
  const api = useApi();
  const coords = useCoordinadores();
  const resumen = useQuery({
    queryKey: ["resumen"],
    queryFn: () => api.get<Record<string, number>>("/api/v1/sitios/resumen"),
  });
  // Server-side queues (audit FE-9): each one is complete up to 200 items and says when there
  // are more, instead of a client-side filter over the first 200 sites by id.
  const revisionQ = useQuery({
    queryKey: ["sitios", "panel", "revision"],
    queryFn: () => api.get<SitioPage>("/api/v1/sitios?en_revision_admin=true&limit=200"),
  });
  const devueltosQ = useQuery({
    queryKey: ["sitios", "panel", "devueltos"],
    queryFn: () => api.get<SitioPage>("/api/v1/sitios?devuelto=true&limit=200"),
  });
  const cargas = useQuery({
    queryKey: ["cargas"],
    queryFn: () => api.get<LoteSummary[]>("/api/v1/admin/cargas?limit=10"),
  });

  const enRevision = revisionQ.data?.items ?? [];
  const devueltos = devueltosQ.data?.items.filter((s) => !s.en_revision_admin) ?? [];
  const more = (q: { data?: SitioPage }) => (q.data?.next_cursor ? "+" : "");
  const previas = cargas.data?.filter((l) => l.estado === "vista_previa") ?? [];
  const total = Object.values(resumen.data ?? {}).reduce((a, b) => a + b, 0);
  const max = Math.max(1, ...Object.values(resumen.data ?? {}));

  return (
    <main>
      <PageHeader title="Resumen" description="Lo que requiere tu decisión y el estado del pipeline." />
      {revisionQ.isError ? <ProblemAlert error={revisionQ.error} onRetry={() => void revisionQ.refetch()} /> : null}
      {devueltosQ.isError ? <ProblemAlert error={devueltosQ.error} onRetry={() => void devueltosQ.refetch()} /> : null}
      {cargas.isError ? <ProblemAlert error={cargas.error} onRetry={() => void cargas.refetch()} /> : null}

      <div className="queues">
        <section className={`card queue${enRevision.length ? " has-items" : ""}`} aria-labelledby="q-revision">
          <span className="queue-count">{revisionQ.data ? `${enRevision.length}${more(revisionQ)}` : "…"}</span>
          <h2 id="q-revision">Sitios en revisión</h2>
          <p className="queue-sub">Una carga los asignó a otro coordinador. Reasigna, devuelve o descarta.</p>
          <ul>
            {enRevision.slice(0, MAX_LIST).map((s) => (
              <li key={s.id}>
                <Link to={`/sitios/${s.id}`}>{s.nombre}</Link>
                <span className="muted nowrap">{coords.nombre(s.usuario_codigo).split(" ")[0]}</span>
              </li>
            ))}
          </ul>
          {revisionQ.data && enRevision.length === 0 ? <p className="muted small">Ninguno pendiente.</p> : null}
          {enRevision.length > MAX_LIST ? <p className="queue-more">y {enRevision.length - MAX_LIST} más</p> : null}
        </section>

        <section className={`card queue${previas.length ? " has-items" : ""}`} aria-labelledby="q-cargas">
          <span className="queue-count">{cargas.data ? previas.length : "…"}</span>
          <h2 id="q-cargas">Cargas sin confirmar</h2>
          <p className="queue-sub">Vistas previas que esperan decisiones y confirmación.</p>
          <ul>
            {previas.slice(0, MAX_LIST).map((l) => (
              <li key={l.id}>
                <Link to={`/cargas/${l.id}`}>{l.archivo_nombre}</Link>
                <span className="muted nowrap">{l.pendientes_decision} por decidir</span>
              </li>
            ))}
          </ul>
          {cargas.data && previas.length === 0 ? <p className="muted small">Ninguna pendiente.</p> : null}
          <p className="queue-more">
            <Link to="/cargas">Nueva carga</Link>
          </p>
        </section>

        <section className={`card queue${devueltos.length ? " has-items" : ""}`} aria-labelledby="q-devueltos">
          <span className="queue-count">{devueltosQ.data ? `${devueltos.length}${more(devueltosQ)}` : "…"}</span>
          <h2 id="q-devueltos">Devueltos sin corregir</h2>
          <p className="queue-sub">Esperan que el coordinador corrija y vuelva a avanzar.</p>
          <ul>
            {devueltos.slice(0, MAX_LIST).map((s) => (
              <li key={s.id}>
                <Link to={`/sitios/${s.id}`}>{s.nombre}</Link>
                <span className="muted nowrap">{coords.nombre(s.usuario_codigo).split(" ")[0]}</span>
              </li>
            ))}
          </ul>
          {devueltosQ.data && devueltos.length === 0 ? <p className="muted small">Ninguno.</p> : null}
          {devueltos.length > MAX_LIST ? <p className="queue-more">y {devueltos.length - MAX_LIST} más</p> : null}
        </section>
      </div>

      <div className="two-col">
        <section className="card" aria-labelledby="pipeline-h">
          <div className="card-head">
            <h2 id="pipeline-h">Pipeline</h2>
            <span className="muted small">{resumen.data ? `${total} sitios vigentes` : ""}</span>
          </div>
          {resumen.isPending ? <Spinner /> : null}
          {resumen.isError ? <ProblemAlert error={resumen.error} onRetry={() => void resumen.refetch()} /> : null}
          {resumen.data ? (
            <ul className="funnel" data-testid="resumen-cards">
              {[...ESTATUS_ORDER, "descartado", "entregado"].map((k) => {
                const n = resumen.data[k] ?? 0;
                const terminal = !(ESTATUS_ORDER as readonly string[]).includes(k);
                return (
                  <li key={k} className={terminal ? "terminal" : ""}>
                    <Link to={`/sitios?estatus=${k}`} style={{ textDecoration: "none" }}>
                      {ESTATUS_LABELS[k]}
                    </Link>
                    <span className="bar" aria-hidden="true">
                      <i style={{ width: `${Math.round((n / max) * 100)}%` }} />
                    </span>
                    <span className="n num">{n}</span>
                  </li>
                );
              })}
            </ul>
          ) : null}
        </section>

        <section className="card" aria-labelledby="cargas-h">
          <div className="card-head">
            <h2 id="cargas-h">Últimas cargas</h2>
            <Link to="/cargas" className="small">
              Ver todas
            </Link>
          </div>
          {cargas.isPending ? <Spinner /> : null}
          {cargas.data && cargas.data.length === 0 ? <p className="muted">Todavía no hay cargas.</p> : null}
          {cargas.data && cargas.data.length > 0 ? (
            <ul className="list">
              {cargas.data.slice(0, 5).map((l) => (
                <li key={l.id}>
                  <Link to={`/cargas/${l.id}`} className="list-row">
                    <div className="body">
                      <span className="list-title">{l.archivo_nombre}</span>
                      <span className="list-sub">
                        {formatMexicoCity(l.fecha_utc)} · {l.filas_total} filas · {l.filas_advertencia} adv. · {l.filas_error} err.
                      </span>
                    </div>
                    <span className={`tag ${LOTE_ESTADO[l.estado]?.tone ?? ""}`}>{LOTE_ESTADO[l.estado]?.label ?? l.estado}</span>
                    <Icon name="chevron-right" className="chev" />
                  </Link>
                </li>
              ))}
            </ul>
          ) : null}
        </section>
      </div>
      <p className="helper" style={{ marginTop: "var(--space-3)" }}>
        Estatus: <EstatusBadge estatus="sitio_prospectado" /> → <EstatusBadge estatus="dueno_localizado" /> → <EstatusBadge estatus="primera_visita" /> →{" "}
        <EstatusBadge estatus="recepcion_documentos" />
      </p>
    </main>
  );
}
