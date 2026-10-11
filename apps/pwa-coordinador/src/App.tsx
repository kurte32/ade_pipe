import { SignIn, useAuth } from "@pipeline/auth/react";
import { Spinner } from "@pipeline/ui";
import { useEffect, useState } from "react";
import { Route, Routes } from "react-router-dom";

import "./app.css";
import { Shell } from "./components/Shell";
import { MisSitios } from "./pages/MisSitios";
import { Notificaciones } from "./pages/Notificaciones";
import { SitioDetalle } from "./pages/SitioDetalle";
import { SyncProvider } from "./sync/context";

export function App() {
  const { ready, account } = useAuth();
  const [forceSignIn, setForceSignIn] = useState(false);
  useEffect(() => {
    if (account) setForceSignIn(false);
  }, [account]);

  if (!ready) return <Spinner label="Iniciando" />;
  if (!account || !account.roles.includes("Coordinador") || forceSignIn) {
    return <SignIn title="Pipeline de Posibles Tiendas" requiredRole="Coordinador" />;
  }
  return (
    <SyncProvider>
      <Shell onRequestLogin={() => setForceSignIn(true)}>
        <Routes>
          <Route path="/" element={<MisSitios />} />
          <Route path="/sitios/:id" element={<SitioDetalle />} />
          <Route path="/notificaciones" element={<Notificaciones />} />
          <Route path="*" element={<MisSitios />} />
        </Routes>
      </Shell>
    </SyncProvider>
  );
}
