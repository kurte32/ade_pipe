import type { components } from "@pipeline/api-client";
import { SignIn, useAuth } from "@pipeline/auth/react";
import { EstatusBadge, ProblemAlert, Spinner } from "@pipeline/ui";
import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { Link, Route, Routes } from "react-router-dom";

import { useApi } from "./api";

type SitioPage = components["schemas"]["SitioPage"];

function Shell({ children }: { children: ReactNode }) {
  const { account, logout } = useAuth();
  return (
    <>
      <header className="topbar">
        <nav>
          <Link to="/">Mis sitios</Link>
        </nav>
        <div className="row">
          <span className="muted">{account?.name}</span>
          <button type="button" className="secondary" onClick={() => void logout()}>
            Salir
          </button>
        </div>
      </header>
      {children}
    </>
  );
}

function MisSitios() {
  const api = useApi();
  const q = useQuery({
    queryKey: ["sitios"],
    queryFn: () => api.get<SitioPage>("/api/v1/sitios?limit=200"),
  });
  if (q.isPending) return <Spinner label="Cargando sitios" />;
  if (q.isError) return <ProblemAlert error={q.error} onRetry={() => void q.refetch()} />;
  return (
    <main>
      <h1>Mis sitios</h1>
      {q.data.items.length === 0 ? <p className="muted">No tienes sitios asignados.</p> : null}
      <ul className="list" data-testid="sitios-list">
        {q.data.items.map((s) => (
          <li key={s.id}>
            <Link to={`/sitios/${s.id}`}>
              <strong>{s.nombre}</strong> <span className="muted">#{s.origen_id} · {s.region}</span>
              <div>
                <EstatusBadge estatus={s.estatus} devuelto={s.devuelto} />
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </main>
  );
}

export function App() {
  const { ready, account } = useAuth();
  if (!ready) return <Spinner label="Iniciando" />;
  if (!account || !account.roles.includes("Coordinador")) {
    return <SignIn title="Pipeline de Posibles Tiendas" requiredRole="Coordinador" />;
  }
  return (
    <Shell>
      <Routes>
        <Route path="/" element={<MisSitios />} />
        <Route path="*" element={<MisSitios />} />
      </Routes>
    </Shell>
  );
}
