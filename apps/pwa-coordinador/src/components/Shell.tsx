import { useAuth } from "@pipeline/auth/react";
import { formatMexicoCity } from "@pipeline/ui";
import type { ReactNode } from "react";
import { Link, NavLink } from "react-router-dom";

import { clearLocalData, getDb } from "../db/schema";
import { useSync } from "../sync/context";

export function Shell({ children, onRequestLogin }: { children: ReactNode; onRequestLogin: () => void }) {
  const { account, logout } = useAuth();
  const sync = useSync();

  async function salir() {
    await clearLocalData(getDb());
    await logout();
  }

  return (
    <>
      <header className="topbar">
        <nav aria-label="Principal">
          <NavLink to="/">Mis sitios</NavLink>
          <NavLink to="/notificaciones">Avisos</NavLink>
        </nav>
        <div className="row">
          <span className="muted" data-testid="account-name">
            {account?.name}
          </span>
          <button type="button" className="secondary" onClick={() => void salir()}>
            Salir
          </button>
        </div>
      </header>
      {!sync.online ? (
        <div className="offline-banner" role="status" data-testid="offline-banner">
          Sin conexión. Puedes seguir capturando; se enviará al recuperar señal.
        </div>
      ) : null}
      {sync.online && sync.lastOutcome?.offline ? (
        <div className="offline-banner" role="status" data-testid="retrying-banner">
          El servidor no responde. Tus capturas están guardadas y se reintentará automáticamente.
        </div>
      ) : null}
      {sync.needsLogin ? (
        <div className="offline-banner" role="alert" data-testid="needs-login-banner">
          Tu sesión expiró. Tus capturas están guardadas.{" "}
          <button type="button" onClick={onRequestLogin}>
            Iniciar sesión para sincronizar
          </button>
        </div>
      ) : null}
      {sync.lastError ? (
        <div className="offline-banner" role="alert">
          Error al sincronizar: {sync.lastError}
        </div>
      ) : null}
      {children}
      <footer className="muted" style={{ padding: "8px 16px", fontSize: "0.8rem" }}>
        {sync.lastSyncAt ? `Última sincronización: ${formatMexicoCity(new Date(sync.lastSyncAt).toISOString())}` : "Sin sincronizar"}
        {sync.pendingCount ? ` · ${sync.pendingCount} pendiente(s)` : ""}
        {sync.blockedCount ? ` · ${sync.blockedCount} requieren atención` : ""} · <Link to="/">inicio</Link>
      </footer>
    </>
  );
}
