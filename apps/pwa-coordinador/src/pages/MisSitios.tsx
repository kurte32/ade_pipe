import { EstatusBadge, ESTATUS_LABELS, Spinner } from "@pipeline/ui";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { useCachedSitios, useOperaciones } from "../lib/useSitios";
import { useSync } from "../sync/context";

export function MisSitios() {
  const sitios = useCachedSitios();
  const ops = useOperaciones();
  const sync = useSync();
  const [q, setQ] = useState("");
  const [estatus, setEstatus] = useState("");

  const pendingBySite = useMemo(() => {
    const m = new Map<number, { pending: number; blocked: number }>();
    for (const op of ops ?? []) {
      const e = m.get(op.sitioId) ?? { pending: 0, blocked: 0 };
      if (op.estado === "bloqueada") e.blocked += 1;
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

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return (sitios ?? []).filter(
      (s) =>
        (!estatus || s.detail.estatus === estatus) &&
        (!needle || s.detail.nombre.toLowerCase().includes(needle) || String(s.detail.origen_id).includes(needle)),
    );
  }, [sitios, q, estatus]);

  if (sitios === undefined) return <Spinner label="Cargando sitios" />;

  return (
    <main>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h1>Mis sitios</h1>
        <button
          type="button"
          className="secondary"
          onClick={() => void sync.syncNow()}
          disabled={sync.syncing || !sync.online}
          data-testid="sync-now"
        >
          {sync.syncing ? "Sincronizando…" : "Sincronizar ahora"}
        </button>
      </div>
      <div className="card">
        <label htmlFor="buscar">Buscar</label>
        <input id="buscar" type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Nombre o número" />
        <label htmlFor="filtro-estatus">Estatus</label>
        <select id="filtro-estatus" value={estatus} onChange={(e) => setEstatus(e.target.value)}>
          <option value="">Todos ({sitios.length})</option>
          {Object.entries(ESTATUS_LABELS).map(([code, label]) => (
            <option key={code} value={code}>
              {label} ({counts[code] ?? 0})
            </option>
          ))}
        </select>
      </div>
      {sitios.length === 0 ? (
        <p className="muted">
          No tienes sitios asignados{sync.online ? "" : " en la caché local"}. {sync.online ? "Sincroniza para actualizar." : ""}
        </p>
      ) : null}
      {filtered.length === 0 && sitios.length > 0 ? <p className="muted">Ningún sitio coincide con el filtro.</p> : null}
      <ul className="list" data-testid="sitios-list">
        {filtered.map(({ detail: s }) => {
          const p = pendingBySite.get(s.id);
          return (
            <li key={s.id} data-testid={`sitio-${s.id}`}>
              <Link to={`/sitios/${s.id}`}>
                <strong>{s.nombre}</strong>{" "}
                <span className="muted">
                  #{s.origen_id} · {s.region}
                </span>
                <div className="row">
                  <EstatusBadge estatus={s.estatus} devuelto={s.devuelto} />
                  {p?.pending ? <span className="pending">pendiente de sincronizar</span> : null}
                  {p?.blocked ? <span className="badge badge-devuelto">bloqueado</span> : null}
                  {s.en_revision_admin ? <span className="muted">en revisión</span> : null}
                </div>
              </Link>
            </li>
          );
        })}
      </ul>
    </main>
  );
}
