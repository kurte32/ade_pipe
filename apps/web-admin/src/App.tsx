import "./admin.css";

import { SignIn, useAuth } from "@pipeline/auth/react";
import { Spinner } from "@pipeline/ui";
import type { ReactNode } from "react";
import { NavLink, Route, Routes } from "react-router-dom";

import { Auditoria } from "./pages/Auditoria";
import { CargaDetail } from "./pages/CargaDetail";
import { Cargas } from "./pages/Cargas";
import { Equivalencias } from "./pages/Equivalencias";
import { Resumen } from "./pages/Resumen";
import { SitioDetailPage } from "./pages/SitioDetail";
import { Sitios } from "./pages/Sitios";

function Shell({ children }: { children: ReactNode }) {
  const { account, logout } = useAuth();
  return (
    <>
      <header className="topbar">
        <nav aria-label="Principal">
          <NavLink to="/" end>
            Resumen
          </NavLink>
          <NavLink to="/sitios">Sitios</NavLink>
          <NavLink to="/cargas">Cargas</NavLink>
          <NavLink to="/equivalencias">Equivalencias</NavLink>
          <NavLink to="/auditoria">Auditoría</NavLink>
        </nav>
        <div className="row">
          <span className="muted" data-testid="account-name">
            {account?.name}
          </span>
          <button type="button" className="secondary" onClick={() => void logout()}>
            Salir
          </button>
        </div>
      </header>
      {children}
    </>
  );
}

export function App() {
  const { ready, account } = useAuth();
  if (!ready) return <Spinner label="Iniciando" />;
  if (!account || !account.roles.includes("Admin")) {
    return <SignIn title="Administración del Pipeline" requiredRole="Admin" />;
  }
  return (
    <Shell>
      <Routes>
        <Route path="/" element={<Resumen />} />
        <Route path="/sitios" element={<Sitios />} />
        <Route path="/sitios/:id" element={<SitioDetailPage />} />
        <Route path="/cargas" element={<Cargas />} />
        <Route path="/cargas/:id" element={<CargaDetail />} />
        <Route path="/equivalencias" element={<Equivalencias />} />
        <Route path="/auditoria" element={<Auditoria />} />
        <Route path="*" element={<Resumen />} />
      </Routes>
    </Shell>
  );
}
