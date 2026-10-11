// @vitest-environment node
// jsdom's Blob has no slice().arrayBuffer(); browsers and Node do, and the e2e PDF flow covers the browser.
import { describe, expect, it } from "vitest";

import { sha256Hex } from "./sha256";

async function reference(bytes: Uint8Array): Promise<string> {
  const d = await crypto.subtle.digest("SHA-256", bytes as unknown as BufferSource);
  return Array.from(new Uint8Array(d), (b) => b.toString(16).padStart(2, "0")).join("");
}

describe("sha256Hex (streaming)", () => {
  it("matches WebCrypto on an empty blob and on a blob spanning several 4 MiB slices", async () => {
    expect(await sha256Hex(new Blob([]))).toBe(await reference(new Uint8Array()));
    const big = new Uint8Array(9 * 1024 * 1024 + 123);
    for (let i = 0; i < big.length; i++) big[i] = (i * 31 + 7) & 0xff;
    expect(await sha256Hex(new Blob([big]))).toBe(await reference(big));
  });
});
