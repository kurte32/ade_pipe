import { describe, expect, it } from "vitest";

import { configFromEnv } from "..";

const base = {
  VITE_TENANT_ID: "t",
  VITE_SPA_CLIENT_ID: "spa",
  VITE_API_CLIENT_ID: "api",
};

describe("configFromEnv", () => {
  it("defaults to msal and keeps ids", () => {
    const c = configFromEnv({ ...base });
    expect(c.mode).toBe("msal");
    expect(c.apiClientId).toBe("api");
  });
  it("accepts dev mode outside production", () => {
    expect(configFromEnv({ ...base, VITE_AUTH_MODE: "dev", PROD: false }).mode).toBe("dev");
  });
  it("refuses dev mode in production builds unless explicitly allowed", () => {
    expect(() => configFromEnv({ ...base, VITE_AUTH_MODE: "dev", PROD: true })).toThrow(/producción/);
    expect(configFromEnv({ ...base, VITE_AUTH_MODE: "dev", PROD: true, VITE_ALLOW_DEV_AUTH: "true" }).mode).toBe("dev");
  });
  it("fails on missing ids and unknown modes", () => {
    expect(() => configFromEnv({ VITE_AUTH_MODE: "msal" })).toThrow(/VITE_TENANT_ID/);
    expect(() => configFromEnv({ ...base, VITE_AUTH_MODE: "x" })).toThrow(/inválido/);
  });
});
