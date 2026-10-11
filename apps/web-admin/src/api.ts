import { createApi, type Api } from "@pipeline/api-client";
import type { AuthProvider } from "@pipeline/auth";
import { useAuth } from "@pipeline/auth/react";
import { useMemo } from "react";

const cache = new WeakMap<AuthProvider, Api>();

export function useApi(): Api {
  const { provider } = useAuth();
  return useMemo(() => {
    let api = cache.get(provider);
    if (!api) {
      api = createApi(provider);
      cache.set(provider, api);
    }
    return api;
  }, [provider]);
}
