import { describe, expect, it } from "vitest";

import { configFromEnv } from "../index";
import { RUNTIME_STORE_KEY, loadRuntimeEnv } from "../runtime";

class MemStorage {
  private m = new Map<string, string>();
  getItem(k: string) {
    return this.m.get(k) ?? null;
  }
  setItem(k: string, v: string) {
    this.m.set(k, v);
  }
}

const mem = () => new MemStorage() as unknown as Storage;
const build = { VITE_AUTH_MODE: "msal", PROD: true };
const json = (body: unknown) =>
  (async () => new Response(JSON.stringify(body), { headers: { "content-type": "application/json" } })) as unknown as typeof fetch;

describe("runtime config (audit D-04, D-13)", () => {
  it("takes the environment ids from config.json", async () => {
    const env = await loadRuntimeEnv("/", build, json({ VITE_TENANT_ID: "t", VITE_SPA_CLIENT_ID: "s", VITE_API_CLIENT_ID: "a" }), mem());
    const cfg = configFromEnv(env);
    expect([cfg.mode, cfg.tenantId, cfg.spaClientId, cfg.apiClientId]).toEqual(["msal", "t", "s", "a"]);
  });

  it("cannot switch a production build to dev auth", async () => {
    const env = await loadRuntimeEnv(
      "/",
      build,
      json({ VITE_AUTH_MODE: "dev", VITE_ALLOW_DEV_AUTH: "true", VITE_TENANT_ID: "t", VITE_SPA_CLIENT_ID: "s", VITE_API_CLIENT_ID: "a" }),
      mem(),
    );
    expect(env.VITE_AUTH_MODE).toBe("msal");
    expect(env.VITE_ALLOW_DEV_AUTH).toBeUndefined();
  });

  it("ignores an index.html fallback and uses the last good file when offline", async () => {
    const store = mem();
    store.setItem(RUNTIME_STORE_KEY, JSON.stringify({ VITE_TENANT_ID: "saved" }));
    const html = (async () => new Response("<html></html>", { headers: { "content-type": "text/html" } })) as unknown as typeof fetch;
    expect((await loadRuntimeEnv("/", build, html, store)).VITE_TENANT_ID).toBe("saved");
    const offline = (async () => {
      throw new TypeError("Failed to fetch");
    }) as unknown as typeof fetch;
    expect((await loadRuntimeEnv("/", build, offline, store)).VITE_TENANT_ID).toBe("saved");
  });

  it("without any config a production build fails loudly", async () => {
    const notFound = (async () => new Response("", { status: 404 })) as unknown as typeof fetch;
    const env = await loadRuntimeEnv("/", build, notFound, mem());
    expect(() => configFromEnv(env)).toThrow(/VITE_TENANT_ID/);
  });
});
