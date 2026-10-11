import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import type { DevUser } from "./dev";
import { DevAuthProvider } from "./dev";
import type { Account, AuthProvider } from "./types";

interface AuthState {
  provider: AuthProvider;
  account: Account | null;
  ready: boolean;
  login: (hint?: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshAccount: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthContextProvider({ provider, children }: { provider: AuthProvider; children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [account, setAccount] = useState<Account | null>(null);

  useEffect(() => {
    let cancelled = false;
    provider
      .initialize()
      .catch(() => undefined)
      .finally(() => {
        if (!cancelled) {
          setAccount(provider.account());
          setReady(true);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [provider]);

  const refreshAccount = useCallback(() => setAccount(provider.account()), [provider]);
  const login = useCallback(
    async (hint?: string) => {
      await provider.login(hint);
      setAccount(provider.account());
    },
    [provider],
  );
  const logout = useCallback(async () => {
    await provider.logout();
    setAccount(null);
  }, [provider]);

  const value = useMemo(
    () => ({ provider, account, ready, login, logout, refreshAccount }),
    [provider, account, ready, login, logout, refreshAccount],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth debe usarse dentro de AuthContextProvider");
  return ctx;
}

/** Sign-in screen. Dev mode shows the user picker; MSAL mode shows a single button. */
export function SignIn({
  title,
  requiredRole,
  brand,
  lede,
}: {
  title: string;
  requiredRole?: string;
  /** Brand block rendered above the title (the app passes its `<Brand/>`). */
  brand?: ReactNode;
  /** One sentence on what the app is for. */
  lede?: string;
}) {
  const { provider, login, account } = useAuth();
  const [users, setUsers] = useState<DevUser[]>([]);
  const [error, setError] = useState<string>("");

  useEffect(() => {
    if (provider instanceof DevAuthProvider) {
      provider
        .listUsers()
        .then((u) => setUsers(requiredRole ? u.filter((x) => x.roles.includes(requiredRole) || x.roles.length === 0) : u))
        .catch(() => setError("No se pudo contactar al proveedor de identidad de desarrollo"));
    }
  }, [provider, requiredRole]);

  const wrongRole = account && requiredRole && !account.roles.includes(requiredRole);

  return (
    <main className="signin" aria-labelledby="signin-title">
      {brand}
      <h1 id="signin-title">{title}</h1>
      {lede ? <p className="lede">{lede}</p> : null}
      {wrongRole ? (
        <p role="alert" className="problem">
          La cuenta {account?.username} no tiene el rol {requiredRole}. Cierra sesión e ingresa con otra cuenta.
        </p>
      ) : null}
      {provider.mode === "msal" ? (
        <button type="button" className="block" onClick={() => void login().catch((e: Error) => setError(e.message))}>
          Iniciar sesión con cuenta corporativa
        </button>
      ) : (
        <div>
          <p className="muted small">Modo de desarrollo: elige un usuario.</p>
          <ul className="dev-users">
            {users.map((u) => (
              <li key={u.code}>
                <button
                  type="button"
                  data-testid={`dev-user-${u.code}`}
                  onClick={() => void login(u.code).catch((e: Error) => setError(e.message))}
                >
                  <span>{u.name}</span>
                  <small>{u.roles.join(", ") || "sin rol"}</small>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
      {error ? (
        <p role="alert" className="problem">
          {error}
        </p>
      ) : null}
    </main>
  );
}
