import { describe, expect, it } from "vitest";

import { ApiError, newCorrelationId, stripEtag } from "..";

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
