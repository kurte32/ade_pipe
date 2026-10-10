import "@pipeline/ui/base.css";

import { configFromEnv, createAuthProvider } from "@pipeline/auth";
import { AuthContextProvider } from "@pipeline/auth/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import { App } from "./App";

const auth = createAuthProvider(configFromEnv(import.meta.env));
const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30_000, networkMode: "online" } },
});

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
