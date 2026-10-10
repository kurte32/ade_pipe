/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_AUTH_MODE?: string;
  readonly VITE_TENANT_ID?: string;
  readonly VITE_SPA_CLIENT_ID?: string;
  readonly VITE_API_CLIENT_ID?: string;
  readonly VITE_DEV_IDP_URL?: string;
  readonly VITE_ALLOW_DEV_AUTH?: string;
}
