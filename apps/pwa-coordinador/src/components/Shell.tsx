import { useAuth } from "@pipeline/auth/react";
import { Alert, AppBar, Icon, Modal, formatMexicoCity } from "@pipeline/ui";
import { useEffect, useState, type ReactNode } from "react";
import { NavLink } from "react-router-dom";

import { clearLocalData, getDb } from "../db/schema";
import { useNotificaciones } from "../lib/notificaciones";
import { useSync } from "../sync/context";

function SyncChip() {
  const sync = useSync();
  let state = "ok";
  let text = "Al día";
  if (sync.syncing) {
    state = "syncing";
    text = "Sincronizando…";
  } else if (!sync.online) {
    state = "offline";
    text = sync.pendingCount ? `Sin señal · ${sync.pendingCount} por enviar` : "Sin señal";
  } else if (sync.blockedCount) {
    state = "error";
    text = `${sync.blockedCount} requieren atención`;
  } else if (sync.pendingCount || sync.lastOutcome?.offline) {
    state = "pending";
    text = `${sync.pendingCount} por enviar`;
  }
  return (
    <button
      type="button"
      className={`sync-chip is-${state}`}
      onClick={() => void sync.syncNow()}
      disabled={sync.syncing || !sync.online}
      data-testid="sync-now"
      title="Sincronizar ahora"
      aria-label={`${text}. Sincronizar ahora`}
    >
      <span className="dot" aria-hidden="true" />
      <span>{text}</span>
      <Icon name="refresh" size={16} />
    </button>
  );
}

export function Shell({ children, onRequestLogin }: { children: ReactNode; onRequestLogin: () => void }) {
  const { account, logout } = useAuth();
  const sync = useSync();
  const avisos = useNotificaciones();
  const unread = avisos.data?.items.filter((n) => !n.leida).length ?? 0;

  const [confirmSalir, setConfirmSalir] = useState(false);
  // Everything not yet accepted by the server is lost on sign-out: queued, in flight, blocked.
  const sinEnviar = sync.pendingCount + sync.blockedCount;

  // The question becomes moot while the dialog is open (a background sync drained the queue).
  useEffect(() => {
    if (confirmSalir && sinEnviar === 0) setConfirmSalir(false);
  }, [confirmSalir, sinEnviar]);

  async function salirYBorrar() {
    setConfirmSalir(false);
    await clearLocalData(getDb());
    await logout();
  }

  function salir() {
    if (sinEnviar > 0) setConfirmSalir(true);
    else void salirYBorrar();
  }

  async function sincronizarPrimero() {
    setConfirmSalir(false);
    await sync.syncNow();
  }

  return (
    <>
      <AppBar
        narrow
        area="Coordinador"
        nav={
          <>
            <NavLink to="/" end>
              Mis sitios
            </NavLink>
            <NavLink to="/notificaciones" aria-label={unread ? `Avisos, ${unread} sin leer` : "Avisos"}>
              Avisos
              {unread ? (
                <span className="count-pill" aria-hidden="true">
                  {unread}
                </span>
              ) : null}
            </NavLink>
          </>
        }
        right={
          <>
            <SyncChip />
            <span className="account-name" data-testid="account-name">
              {account?.name}
            </span>
            <button type="button" className="ghost small" onClick={salir} title="Cerrar sesión y borrar los datos locales">
              <Icon name="log-out" size={18} />
              Salir
            </button>
          </>
        }
      />
      {!sync.online ? (
        <Alert tone="warning" banner icon="wifi-off" testId="offline-banner">
          Sin señal. Puedes seguir capturando; todo se guarda en el teléfono y se enviará al recuperar señal.
        </Alert>
      ) : null}
      {sync.online && sync.lastOutcome?.offline ? (
        <Alert tone="warning" banner icon="cloud-off" testId="retrying-banner">
          El servidor no responde. Tus capturas están guardadas y se reintentará automáticamente.
        </Alert>
      ) : null}
      {sync.needsLogin ? (
        <Alert
          tone="error"
          banner
          testId="needs-login-banner"
          title="Tu sesión expiró"
          actions={
            <button type="button" className="small" onClick={onRequestLogin}>
              Iniciar sesión para sincronizar
            </button>
          }
        >
          Tus capturas están guardadas en el teléfono.
        </Alert>
      ) : null}
      {sync.lastError ? (
        <Alert tone="error" banner title="Error al sincronizar">
          {sync.lastError}
        </Alert>
      ) : null}
      {confirmSalir ? (
        <Modal
          title="¿Salir sin enviar?"
          testId="dialog-salir"
          onClose={() => setConfirmSalir(false)}
          lede={
            sinEnviar === 1
              ? "Tienes 1 captura sin enviar. Al salir se borra del teléfono y no llegará al servidor."
              : `Tienes ${sinEnviar} capturas sin enviar. Al salir se borran del teléfono y no llegarán al servidor.`
          }
        >
          {sync.blockedCount ? (
            <p className="muted">
              {sync.blockedCount === 1 ? "1 cambio requiere tu atención" : `${sync.blockedCount} cambios requieren tu atención`} (conflicto o error):
              resuélvelo desde el sitio antes de salir.
            </p>
          ) : null}
          <div className="actions">
            <button type="button" className="secondary" onClick={() => setConfirmSalir(false)}>
              Cancelar
            </button>
            {sync.online && sync.pendingCount ? (
              <button type="button" onClick={() => void sincronizarPrimero()}>
                Sincronizar primero
              </button>
            ) : null}
            <button type="button" className="danger" data-testid="salir-borrar" onClick={() => void salirYBorrar()}>
              Salir y borrar
            </button>
          </div>
        </Modal>
      ) : null}
      <div id="contenido">{children}</div>
      <footer className="app-footer">
        {sync.lastSyncAt ? `Última sincronización: ${formatMexicoCity(new Date(sync.lastSyncAt).toISOString())}` : "Sin sincronizar todavía"}
        {sync.pendingCount ? ` · ${sync.pendingCount} pendiente(s) de enviar` : ""}
        {sync.blockedCount ? ` · ${sync.blockedCount} requieren atención` : ""}
        {account?.name ? ` · ${account.name}` : ""}
      </footer>
    </>
  );
}
