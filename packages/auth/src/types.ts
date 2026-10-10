export interface Account {
  oid: string;
  name: string;
  username: string;
  roles: string[];
}

export type AuthMode = "dev" | "msal";

export interface AuthConfig {
  mode: AuthMode;
  /** Entra tenant id (both modes; the dev issuer mimics it). */
  tenantId: string;
  /** This SPA's client id (azp in the token). */
  spaClientId: string;
  /** The API registration client id; scope is api://{apiClientId}/access_as_user. */
  apiClientId: string;
  /** Base path of the dev identity provider, proxied by Vite. Dev mode only. */
  devIdpUrl?: string;
}

export interface AuthProvider {
  readonly mode: AuthMode;
  /** Resolve cached session (no network needed when offline). */
  initialize(): Promise<void>;
  /** Account from the cached session, or null. Available offline. */
  account(): Account | null;
  /** Fresh access token. Throws `InteractionRequired` when the user must sign in again. */
  getToken(): Promise<string>;
  /** Start interactive sign-in. In dev mode `hint` is the dev user code. */
  login(hint?: string): Promise<void>;
  logout(): Promise<void>;
  /** True when a valid session exists but a token could not be refreshed (offline or expired). */
  needsInteraction(): boolean;
}

export class InteractionRequired extends Error {
  constructor(message = "Se requiere iniciar sesión") {
    super(message);
    this.name = "InteractionRequired";
  }
}

export class OfflineError extends Error {
  constructor(message = "Sin conexión") {
    super(message);
    this.name = "OfflineError";
  }
}

export const ACCOUNT_STORAGE_KEY = "pipeline.auth.account";
