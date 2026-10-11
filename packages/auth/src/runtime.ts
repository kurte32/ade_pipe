/**
 * Per-environment configuration read at runtime from `<base>/config.json` (audit D-04, D-13).
 *
 * One SPA build is promoted unchanged from dev to test to prod; the deploy step writes the
 * environment's tenant and client ids into config.json next to the bundle. Only those ids may come
 * from the file: the auth mode and the dev-auth permission stay compile-time, so a deployed file
 * can never switch a production build to the development sign-in. The last good file is kept in
 * localStorage so the installed PWA still starts offline.
 */
import type { AuthEnv } from "./index";

export const RUNTIME_KEYS = ["VITE_TENANT_ID", "VITE_SPA_CLIENT_ID", "VITE_API_CLIENT_ID"] as const;
type RuntimeKey = (typeof RUNTIME_KEYS)[number];
export const RUNTIME_STORE_KEY = "pipeline.runtimeConfig";

function pick(raw: unknown): Partial<Record<RuntimeKey, string>> | null {
  if (!raw || typeof raw !== "object") return null;
  const out: Partial<Record<RuntimeKey, string>> = {};
  for (const k of RUNTIME_KEYS) {
    const v = (raw as Record<string, unknown>)[k];
    if (typeof v === "string" && v.trim() !== "") out[k] = v.trim();
  }
  return Object.keys(out).length ? out : null;
}

function defaultStorage(): Storage | undefined {
  try {
    return typeof localStorage === "undefined" ? undefined : localStorage;
  } catch {
    return undefined;
  }
}

export async function loadRuntimeEnv(
  baseUrl: string,
  buildEnv: AuthEnv,
  fetchImpl: typeof fetch = fetch,
  storage: Storage | undefined = defaultStorage(),
): Promise<AuthEnv> {
  let runtime: Partial<Record<RuntimeKey, string>> | null = null;
  try {
    const res = await fetchImpl(`${baseUrl.replace(/\/?$/, "/")}config.json`, { cache: "no-store" });
    const type = res.headers.get("content-type") ?? "";
    // A missing file can come back as the SPA's index.html with 200; only accept JSON.
    if (res.ok && type.includes("json")) {
      runtime = pick(await res.json());
      if (runtime) {
        try {
          storage?.setItem(RUNTIME_STORE_KEY, JSON.stringify(runtime));
        } catch {
          /* storage full or blocked: still usable for this session */
        }
      }
    }
  } catch {
    /* offline: fall back to the last good file */
  }
  if (!runtime) {
    try {
      const saved = storage?.getItem(RUNTIME_STORE_KEY);
      if (saved) runtime = pick(JSON.parse(saved));
    } catch {
      /* corrupt entry: ignore */
    }
  }
  return { ...buildEnv, ...(runtime ?? {}) };
}
