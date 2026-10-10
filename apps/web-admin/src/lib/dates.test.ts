import { describe, expect, it } from "vitest";

import { localToUtcIso, zoneOffsetMs } from "./dates";

describe("localToUtcIso", () => {
  it("converts Mexico City local time (UTC-6) to UTC", () => {
    expect(localToUtcIso("2026-10-10T14:37")).toBe("2026-10-10T20:37:00.000Z");
    expect(localToUtcIso("2026-01-01T00:00:00")).toBe("2026-01-01T06:00:00.000Z");
  });
  it("returns undefined for empty or malformed values", () => {
    expect(localToUtcIso("")).toBeUndefined();
    expect(localToUtcIso("ayer")).toBeUndefined();
  });
  it("computes offsets for other zones", () => {
    expect(zoneOffsetMs(new Date("2026-07-01T12:00:00Z"), "UTC")).toBe(0);
    expect(zoneOffsetMs(new Date("2026-07-01T12:00:00Z"), "America/Mexico_City")).toBe(-6 * 3600 * 1000);
  });
});
