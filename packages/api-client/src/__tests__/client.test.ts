import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, NetworkError, createApi, newCorrelationId, stripEtag } from "..";

describe("api-client helpers", () => {
  it("strips quotes and weak prefix from ETags", () => {
    expect(stripEtag('"abc"')).toBe("abc");
    expect(stripEtag('W/"abc"')).toBe("abc");
    expect(stripEtag(null)).toBeUndefined();
  });
  it("generates 32-char hex correlation ids", () => {
    expect(newCorrelationId()).toMatch(/^[0-9a-f]{32}$/);
  });
  it("exposes problem details fields", () => {
    const e = new ApiError(412, {
      type: "https://pipeline.tiendas3b/problems/precondition-failed",
      title: "El registro cambió",
      status: 412,
      detail: "x",
      correlation_id: "c1",
      current: { estatus: "sitio_prospectado" },
    }, "HTTP 412");
    expect(e.isPreconditionFailed).toBe(true);
    expect(e.slug).toBe("precondition-failed");
    expect(e.correlationId).toBe("c1");
    expect((e.current as { estatus: string }).estatus).toBe("sitio_prospectado");
    expect(e.message).toBe("x");
  });
});

const fakeAuth = { mode: "dev", getToken: async () => "t" } as never;

describe("api-client request timeout (FE-3)", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("turns a request that never answers into a NetworkError after timeoutMs", async () => {
    vi.stubGlobal("fetch", (_url: string, init: RequestInit) =>
      new Promise((_resolve, reject) => {
        init.signal?.addEventListener("abort", () => reject(init.signal?.reason));
      }),
    );
    const api = createApi(fakeAuth);
    await expect(api.get("/api/v1/me", { timeoutMs: 20 })).rejects.toBeInstanceOf(NetworkError);
  });

  it("rethrows the caller's own abort instead of masking it as a network error", async () => {
    vi.stubGlobal("fetch", (_url: string, init: RequestInit) =>
      new Promise((_resolve, reject) => {
        const abort = () => reject(new DOMException("aborted", "AbortError"));
        if (init.signal?.aborted) abort(); // real fetch rejects at once on an aborted signal
        else init.signal?.addEventListener("abort", abort);
      }),
    );
    const api = createApi(fakeAuth);
    const controller = new AbortController();
    const pending = api.get("/api/v1/me", { signal: controller.signal, timeoutMs: 5_000 });
    controller.abort();
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
  });
});
