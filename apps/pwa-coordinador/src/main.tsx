import "@pipeline/ui/base.css";

import { configFromEnv, createAuthProvider, loadRuntimeEnv } from "@pipeline/auth";
import { AuthContextProvider } from "@pipeline/auth/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import { App } from "./App";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30_000, networkMode: "offlineFirst" } },
});

async function main(): Promise<void> {
  // Tenant and client ids come from the environment's config.json at runtime (audit D-04).
  const env = await loadRuntimeEnv(import.meta.env.BASE_URL, import.meta.env);
  const auth = createAuthProvider(configFromEnv(env));
  createRoot(document.getElementById("root")!).render(
    <React.StrictMode>
      <AuthContextProvider provider={auth}>
        <QueryClientProvider client={queryClient}>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </QueryClientProvider>
      </AuthContextProvider>
    </React.StrictMode>,
  );
}

void main();
