import { ESTATUS_LABELS, EstatusBadge, ProblemAlert, Spinner, formatMexicoCity } from "@pipeline/ui";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { useApi } from "../api";
import type { LoteSummary, SitioPage } from "../lib/types";

export function Resumen() {
  const api = useApi();
  const resumen = useQuery({
    queryKey: ["resumen"],
    queryFn: () => api.get<Record<string, number>>("/api/v1/sitios/resumen"),
  });
  const revision = useQuery({
    queryKey: ["sitios", "revision"],
    queryFn: () => api.get<SitioPage>("/api/v1/sitios?limit=200"),
    select: (p) => p.items.filter((s) => s.en_revision_admin),
  });
  const cargas = useQuery({
    queryKey: ["cargas"],
    queryFn: () => api.get<LoteSummary[]>("/api/v1/admin/cargas?limit=5"),
  });

  return (
    <main>
      <h1>Resumen</h1>
      {resumen.isPending ? <Spinner /> : null}
      {resumen.isError ? <ProblemAlert error={resumen.error} onRetry={() => void resumen.refetch()} /> : null}
      {resumen.data ? (
        <div className="cards" data-testid="resumen-cards">
          {Object.keys(ESTATUS_LABELS).map((k) => (
            <div className="card" key={k}>
              <strong>{resumen.data[k] ?? 0}</strong>
              <span className="muted">{ESTATUS_LABELS[k]}</span>
            </div>
          ))}
        </div>
      ) : null}

      <h2>Sitios en revisión del administrador</h2>
      {revision.data && revision.data.length === 0 ? <p className="muted">Ninguno.</p> : null}
      {revision.data && revision.data.length > 0 ? (
        <ul className="list">
          {revision.data.map((s) => (
            <li key={s.id}>
              <Link to={`/sitios/${s.id}`}>
                <strong>{s.nombre}</strong> <span className="muted">#{s.origen_id} · {s.usuario_codigo}</span>{" "}
                <EstatusBadge estatus={s.estatus} devuelto={s.devuelto} />
              </Link>
            </li>
          ))}
        </ul>
      ) : null}

      <h2>Últimas cargas</h2>
      {cargas.data && cargas.data.length === 0 ? <p className="muted">Sin cargas.</p> : null}
      {cargas.data && cargas.data.length > 0 ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Fecha</th>
                <th>Archivo</th>
                <th>Filas</th>
                <th>Estado</th>
              </tr>
            </thead>
            <tbody>
              {cargas.data.map((l) => (
                <tr key={l.id}>
                  <td className="nowrap">{formatMexicoCity(l.fecha_utc)}</td>
                  <td>
                    <Link to={`/cargas/${l.id}`}>{l.archivo_nombre}</Link>
                  </td>
                  <td>
                    {l.filas_total} ({l.filas_ok} ok, {l.filas_advertencia} adv., {l.filas_error} err.)
                  </td>
                  <td>{l.estado}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </main>
  );
}
