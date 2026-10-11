import { DevAuthProvider } from "./dev";
import { MsalAuthProvider } from "./msal";
import type { AuthConfig, AuthMode, AuthProvider } from "./types";

export * from "./types";
export { DevAuthProvider } from "./dev";
export type { DevUser } from "./dev";
export { MsalAuthProvider } from "./msal";
export { loadRuntimeEnv, RUNTIME_KEYS, RUNTIME_STORE_KEY } from "./runtime";

export interface AuthEnv {
  VITE_AUTH_MODE?: string;
  VITE_TENANT_ID?: string;
  VITE_SPA_CLIENT_ID?: string;
  VITE_API_CLIENT_ID?: string;
  VITE_DEV_IDP_URL?: string;
  VITE_ALLOW_DEV_AUTH?: string;
  PROD?: boolean;
}

export function configFromEnv(env: AuthEnv): AuthConfig {
  const mode = (env.VITE_AUTH_MODE ?? "msal") as AuthMode;
  if (mode !== "dev" && mode !== "msal") throw new Error(`VITE_AUTH_MODE inválido: ${mode}`);
  if (mode === "dev" && env.PROD && env.VITE_ALLOW_DEV_AUTH !== "true") {
    throw new Error("El modo de autenticación de desarrollo no está permitido en producción");
  }
  const required = ["VITE_TENANT_ID", "VITE_SPA_CLIENT_ID", "VITE_API_CLIENT_ID"] as const;
  for (const k of required) {
    if (!env[k]) throw new Error(`Falta la variable ${k}`);
  }
  return {
    mode,
    tenantId: env.VITE_TENANT_ID!,
    spaClientId: env.VITE_SPA_CLIENT_ID!,
    apiClientId: env.VITE_API_CLIENT_ID!,
    devIdpUrl: env.VITE_DEV_IDP_URL ?? "/dev-idp",
  };
}

export function createAuthProvider(config: AuthConfig): AuthProvider {
  return config.mode === "dev" ? new DevAuthProvider(config) : new MsalAuthProvider(config);
}
