import { createApi, type Api } from "@pipeline/api-client";
import { runtimeEnv, type AuthProvider } from "@pipeline/auth";
import { useAuth } from "@pipeline/auth/react";
import { useMemo } from "react";

const cache = new WeakMap<AuthProvider, Api>();

export function useApi(): Api {
  const { provider } = useAuth();
  return useMemo(() => {
    let api = cache.get(provider);
    if (!api) {
      // Same origin by default; the Container App's origin where there is no Front Door (INF-2).
      api = createApi(provider, runtimeEnv()?.VITE_API_BASE_URL ?? "");
      cache.set(provider, api);
    }
    return api;
  }, [provider]);
}
