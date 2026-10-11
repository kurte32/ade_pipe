/**
 * Development auth provider backed by tools/dev-idp (a real RS256 issuer, proxied at /dev-idp).
 * Never bundled into production builds: `createAuthProvider` refuses mode "dev" when
 * `import.meta.env.PROD` is true unless VITE_ALLOW_DEV_AUTH=true (test environment only).
 */

import { z } from "zod";

import {
  ACCOUNT_STORAGE_KEY,
  InteractionRequired,
  OfflineError,
  type Account,
  type AuthConfig,
  type AuthProvider,
} from "./types";

const TOKEN_KEY = "pipeline.auth.dev.token";
const REFRESH_MARGIN_SECONDS = 120;

const tokenResponse = z.object({
  access_token: z.string(),
  expires_in: z.number(),
  account: z.object({
    oid: z.string(),
    name: z.string(),
    username: z.string(),
    roles: z.array(z.string()),
  }),
});

export const devUser = z.object({
  code: z.string(),
  name: z.string(),
  email: z.string(),
  oid: z.string(),
  roles: z.array(z.string()),
});
export type DevUser = z.infer<typeof devUser>;

interface StoredToken {
  token: string;
  exp: number; // epoch seconds
  userCode: string;
}

function read<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

function write(key: string, value: unknown): void {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* storage unavailable: session will not persist */
  }
}

export class DevAuthProvider implements AuthProvider {
  readonly mode = "dev" as const;
  private readonly base: string;
  private interaction = false;

  constructor(private readonly config: AuthConfig) {
    this.base = (config.devIdpUrl ?? "/dev-idp").replace(/\/$/, "");
  }

  async initialize(): Promise<void> {
    /* nothing to do: state lives in localStorage */
  }

  account(): Account | null {
    return read<Account>(ACCOUNT_STORAGE_KEY);
  }

  needsInteraction(): boolean {
    return this.interaction;
  }

  async listUsers(): Promise<DevUser[]> {
    const res = await fetch(`${this.base}/users`);
    if (!res.ok) throw new Error(`dev-idp ${res.status}`);
    return z.array(devUser).parse(await res.json());
  }

  async getToken(): Promise<string> {
    const stored = read<StoredToken>(TOKEN_KEY);
    const now = Math.floor(Date.now() / 1000);
    if (stored && stored.exp - REFRESH_MARGIN_SECONDS > now) return stored.token;
    if (!stored) {
      this.interaction = true;
      throw new InteractionRequired();
    }
    if (!navigator.onLine) throw new OfflineError();
    try {
      await this.mint(stored.userCode);
    } catch (e) {
      if (e instanceof TypeError) throw new OfflineError(); // fetch failed
      this.interaction = true;
      throw new InteractionRequired();
    }
    this.interaction = false;
    return read<StoredToken>(TOKEN_KEY)!.token;
  }

  async login(hint?: string): Promise<void> {
    if (!hint) throw new Error("Selecciona un usuario de desarrollo");
    await this.mint(hint);
    this.interaction = false;
  }

  async logout(): Promise<void> {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(ACCOUNT_STORAGE_KEY);
  }

  private async mint(userCode: string): Promise<void> {
    const res = await fetch(`${this.base}/token`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ user_code: userCode, client_id: this.config.spaClientId }),
    });
    if (!res.ok) throw new InteractionRequired(`dev-idp ${res.status}`);
    const data = tokenResponse.parse(await res.json());
    write(TOKEN_KEY, {
      token: data.access_token,
      exp: Math.floor(Date.now() / 1000) + data.expires_in,
      userCode,
    } satisfies StoredToken);
    write(ACCOUNT_STORAGE_KEY, data.account satisfies Account);
  }
}
