import "@pipeline/ui/base.css";

import { configFromEnv, createAuthProvider, loadRuntimeEnv } from "@pipeline/auth";
import { AuthContextProvider } from "@pipeline/auth/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import { App } from "./App";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30_000, networkMode: "online" } },
});

async function main(): Promise<void> {
  // Tenant and client ids come from the environment's config.json at runtime (audit D-04).
  const env = await loadRuntimeEnv(import.meta.env.BASE_URL, import.meta.env);
  const auth = createAuthProvider(configFromEnv(env));
  createRoot(document.getElementById("root")!).render(
    <React.StrictMode>
      <AuthContextProvider provider={auth}>
        <QueryClientProvider client={queryClient}>
          <BrowserRouter basename={import.meta.env.BASE_URL}>
            <App />
          </BrowserRouter>
        </QueryClientProvider>
      </AuthContextProvider>
    </React.StrictMode>,
  );
}

main().catch((e: unknown) => {
  // A missing or invalid config.json used to leave a blank page (audit FE-13).
  const root = document.getElementById("root");
  if (root) {
    root.innerHTML = "";
    const box = document.createElement("div");
    box.setAttribute("role", "alert");
    box.style.cssText = "font-family: system-ui, sans-serif; max-width: 36rem; margin: 3rem auto; padding: 1rem;";
    const h = document.createElement("h1");
    h.textContent = "No se pudo iniciar la aplicación";
    const p = document.createElement("p");
    p.textContent = "Falta la configuración del entorno o no es válida. Avisa a soporte con este detalle:";
    const pre = document.createElement("pre");
    pre.textContent = e instanceof Error ? e.message : String(e);
    box.append(h, p, pre);
    root.append(box);
  }
});
