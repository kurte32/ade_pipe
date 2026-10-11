import { describe, expect, it } from "vitest";

import { esTerminal, estatusAnteriores } from "./estatus";

describe("estatusAnteriores", () => {
  it("returns nothing for the first status", () => {
    expect(estatusAnteriores("sitio_prospectado")).toEqual([]);
  });
  it("returns all earlier statuses in order", () => {
    expect(estatusAnteriores("primera_visita")).toEqual(["sitio_prospectado", "dueno_localizado"]);
    expect(estatusAnteriores("recepcion_documentos")).toEqual([
      "sitio_prospectado",
      "dueno_localizado",
      "primera_visita",
    ]);
  });
  it("returns nothing for terminal or unknown statuses", () => {
    expect(estatusAnteriores("descartado")).toEqual([]);
    expect(estatusAnteriores("x")).toEqual([]);
  });
});

describe("esTerminal", () => {
  it("detects terminal statuses", () => {
    expect(esTerminal("descartado")).toBe(true);
    expect(esTerminal("entregado")).toBe(true);
    expect(esTerminal("dueno_localizado")).toBe(false);
  });
});
