import "./admin.css";

import { SignIn, useAuth } from "@pipeline/auth/react";
import { AppBar, Brand, Icon, Spinner } from "@pipeline/ui";
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
      <AppBar
        area="Administración"
        homeHref={import.meta.env.BASE_URL}
        nav={
          <>
            <NavLink to="/" end>
              Resumen
            </NavLink>
            <NavLink to="/sitios">Sitios</NavLink>
            <NavLink to="/cargas">Cargas</NavLink>
            <NavLink to="/equivalencias">Equivalencias</NavLink>
            <NavLink to="/auditoria">Auditoría</NavLink>
          </>
        }
        right={
          <>
            <span className="account-name" data-testid="account-name">
              {account?.name}
            </span>
            <button type="button" className="ghost small" onClick={() => void logout()}>
              <Icon name="log-out" size={18} />
              Salir
            </button>
          </>
        }
      />
      <div id="contenido">{children}</div>
    </>
  );
}

export function App() {
  const { ready, account } = useAuth();
  if (!ready) return <Spinner label="Iniciando" />;
  if (!account || !account.roles.includes("Admin")) {
    return (
      <SignIn
        title="Iniciar sesión"
        requiredRole="Admin"
        brand={<Brand area="Administración" href={import.meta.env.BASE_URL} />}
        lede="Carga sitios, revisa la calidad de la información, devuelve y reasigna sitios, y consulta la bitácora."
      />
    );
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
