/**
 * Microsoft Entra ID provider (MSAL Browser). Mirrors the Entra guide Part B with the
 * decisions from ADR-005: localStorage cache so the PWA opens offline, redirect flow only,
 * no token request while an interaction is in progress.
 *
 * Status: written and type-checked; NOT verified against a real tenant in this build.
 */

import {
  BrowserCacheLocation,
  InteractionRequiredAuthError,
  PublicClientApplication,
  type AccountInfo,
  type AuthenticationResult,
} from "@azure/msal-browser";

import {
  ACCOUNT_STORAGE_KEY,
  InteractionRequired,
  OfflineError,
  type Account,
  type AuthConfig,
  type AuthProvider,
} from "./types";

function toAccount(info: AccountInfo): Account {
  const claims = (info.idTokenClaims ?? {}) as Record<string, unknown>;
  const roles = Array.isArray(claims["roles"]) ? (claims["roles"] as string[]) : [];
  return {
    oid: String(claims["oid"] ?? info.localAccountId),
    name: info.name ?? "",
    username: info.username,
    roles,
  };
}

export class MsalAuthProvider implements AuthProvider {
  readonly mode = "msal" as const;
  private readonly pca: PublicClientApplication;
  private readonly scopes: string[];
  private busy = false;
  private interaction = false;

  constructor(config: AuthConfig) {
    this.pca = new PublicClientApplication({
      auth: {
        clientId: config.spaClientId,
        authority: `https://login.microsoftonline.com/${config.tenantId}`,
        redirectUri: window.location.origin,
        postLogoutRedirectUri: window.location.origin,
        navigateToLoginRequestUrl: true,
      },
      cache: { cacheLocation: BrowserCacheLocation.LocalStorage },
      system: { allowRedirectInIframe: false },
    });
    this.scopes = [`api://${config.apiClientId}/access_as_user`];
  }

  async initialize(): Promise<void> {
    await this.pca.initialize();
    this.busy = true;
    try {
      const result: AuthenticationResult | null = await this.pca.handleRedirectPromise();
      const account = result?.account ?? this.pca.getAllAccounts()[0] ?? null;
      if (account) {
        this.pca.setActiveAccount(account);
        try {
          localStorage.setItem(ACCOUNT_STORAGE_KEY, JSON.stringify(toAccount(account)));
        } catch {
          /* ignore */
        }
      }
    } finally {
      this.busy = false;
    }
  }

  account(): Account | null {
    const active = this.pca.getActiveAccount();
    if (active) return toAccount(active);
    try {
      const raw = localStorage.getItem(ACCOUNT_STORAGE_KEY);
      return raw ? (JSON.parse(raw) as Account) : null;
    } catch {
      return null;
    }
  }

  needsInteraction(): boolean {
    return this.interaction;
  }

  async getToken(): Promise<string> {
    const account = this.pca.getActiveAccount();
    if (!account) {
      this.interaction = true;
      throw new InteractionRequired();
    }
    if (!navigator.onLine) throw new OfflineError();
    try {
      const r = await this.pca.acquireTokenSilent({ scopes: this.scopes, account });
      this.interaction = false;
      return r.accessToken;
    } catch (e) {
      if (e instanceof InteractionRequiredAuthError) {
        this.interaction = true;
        throw new InteractionRequired();
      }
      throw e;
    }
  }

  async login(): Promise<void> {
    if (this.busy) return; // never start a redirect while one is in progress (guide B7)
    this.busy = true;
    await this.pca.loginRedirect({ scopes: this.scopes });
  }

  async logout(): Promise<void> {
    try {
      localStorage.removeItem(ACCOUNT_STORAGE_KEY);
    } catch {
      /* ignore */
    }
    await this.pca.logoutRedirect();
  }
}
