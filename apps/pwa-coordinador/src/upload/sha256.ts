import { createSHA256 } from "hash-wasm";

/** 4 MiB slices: the file is never held in memory at once. */
const CHUNK = 4 * 1024 * 1024;

/**
 * Streaming SHA-256 of a Blob (backlog SHA-STREAM). `crypto.subtle.digest` needs the whole file as
 * one ArrayBuffer, which a 150 MB PDF on a phone could not afford; hash-wasm hashes slice by slice.
 */
export async function sha256Hex(blob: Blob): Promise<string> {
  const hasher = await createSHA256();
  hasher.init();
  for (let offset = 0; offset < blob.size; offset += CHUNK) {
    const part = await blob.slice(offset, Math.min(offset + CHUNK, blob.size)).arrayBuffer();
    hasher.update(new Uint8Array(part));
  }
  return hasher.digest("hex");
}
