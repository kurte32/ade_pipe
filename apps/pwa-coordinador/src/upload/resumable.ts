/**
 * Resumable chunked upload for PDFs (RF-08, HU-11). Online only by design (Propuesta A3).
 * The session id is persisted in Dexie `meta` so a reload resumes from the parts the server has.
 */

import { ApiError, type Api } from "@pipeline/api-client";

import { getMeta, setMeta, type PipelineDb } from "../db/schema";
import type { ArchivoMeta, SubidaOut } from "../lib/types";
import { sha256Hex } from "./sha256";

export interface UploadProgress {
  phase: "hash" | "upload" | "verify" | "done";
  sent: number;
  total: number;
}

export interface UploadDocumentArgs {
  api: Api;
  db: PipelineDb;
  sitioId: number;
  tipoDocumento: string;
  file: File;
  onProgress?: (p: UploadProgress) => void;
  signal?: AbortSignal;
}

interface SavedSession {
  sessionId: string;
  sha256: string;
}

function metaKey(sitioId: number, tipoDocumento: string): string {
  return `upload:${sitioId}:${tipoDocumento}`;
}

export type UploadResult = { estado: "publicado"; archivo: ArchivoMeta } | { estado: "escaneando"; subidaId: string };

export async function uploadDocument(args: UploadDocumentArgs): Promise<UploadResult> {
  const { api, db, sitioId, tipoDocumento, file, onProgress, signal } = args;
  onProgress?.({ phase: "hash", sent: 0, total: file.size });
  const sha = await sha256Hex(file);
  const key = metaKey(sitioId, tipoDocumento);

  let session: SubidaOut | null = null;
  const saved = await getMeta<SavedSession>(db, key);
  if (saved && saved.sha256 === sha) {
    try {
      const s = await api.get<SubidaOut>(`/api/v1/subidas/${saved.sessionId}`, { signal });
      if (s.estado === "abierta") session = s;
      else if (s.estado === "publicada" && s.archivo_id) {
        await db.meta.delete(key);
        const archivo = await api.get<ArchivoMeta>(`/api/v1/archivos/${s.archivo_id}/meta`);
        return { estado: "publicado", archivo };
      }
    } catch (e) {
      if (!(e instanceof ApiError && (e.status === 404 || e.status === 410))) throw e;
    }
  }
  if (!session) {
    const created = await api.post<SubidaOut>(
      "/api/v1/subidas",
      {
        sitio_id: sitioId,
        tipo: "documento",
        tipo_documento: tipoDocumento,
        nombre_original: file.name,
        content_type: "application/pdf",
        bytes_total: file.size,
        sha256: sha,
      },
      { signal },
    );
    session = created.data;
    await setMeta(db, key, { sessionId: session.id, sha256: sha } satisfies SavedSession);
  }

  const received = new Set(session.partes_recibidas);
  let sent = received.size * session.tamano_parte;
  onProgress?.({ phase: "upload", sent: Math.min(sent, file.size), total: file.size });
  for (let n = 0; n < session.partes_total; n++) {
    if (received.has(n)) continue;
    signal?.throwIfAborted();
    const slice = file.slice(n * session.tamano_parte, (n + 1) * session.tamano_parte);
    await api.put(`/api/v1/subidas/${session.id}/partes/${n}`, undefined, { raw: slice, signal });
    sent += slice.size;
    onProgress?.({ phase: "upload", sent: Math.min(sent, file.size), total: file.size });
  }
  onProgress?.({ phase: "verify", sent: file.size, total: file.size });
  try {
    const done = await api.post<ArchivoMeta | { estado: string; id: string }>(
      `/api/v1/subidas/${session.id}/completar`,
      undefined,
      { signal },
    );
    await db.meta.delete(key);
    onProgress?.({ phase: "done", sent: file.size, total: file.size });
    if (done.status === 202) return { estado: "escaneando", subidaId: session.id };
    return { estado: "publicado", archivo: done.data as ArchivoMeta };
  } catch (e) {
    // A rejected session cannot be resumed: forget it so the next attempt starts clean.
    if (e instanceof ApiError && e.status === 422) await db.meta.delete(key);
    throw e;
  }
}
