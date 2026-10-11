import Dexie, { type EntityTable } from "dexie";

import type { SitioDetail } from "../lib/types";

export interface CachedSitio {
  id: number;
  detail: SitioDetail;
  etag: string;
  updatedAt: number;
}

export type OperacionTipo = "contacto" | "visita" | "transicion" | "foto";
export type OperacionEstado = "pendiente" | "enviando" | "bloqueada" | "error";

export interface Operacion {
  id: string;
  sitioId: number;
  tipo: OperacionTipo;
  /** ContactoIn | VisitaIn | TransicionIn | { fotoId: string } */
  payload: unknown;
  idempotencyKey: string;
  /** Site ETag known when the user decided. Threaded forward inside a chain. */
  etagBase: string;
  createdAt: number;
  seq: number;
  estado: OperacionEstado;
  /** Transient-failure (429/5xx/timeout) retry count; a terminal `error` is set once it caps out. */
  intentos?: number;
  error?: string;
  /** Server state attached to a 412, shown in the conflict panel. */
  conflict?: SitioDetail | null;
  /** Detail list from a 422 (missing requirements). */
  faltantes?: string[];
}

export interface FotoLocal {
  id: string;
  sitioId: number;
  blob: Blob;
  nombre: string;
  sha256: string;
  bytes: number;
  createdAt: number;
}

export interface MetaRow {
  key: string;
  value: unknown;
}

export class PipelineDb extends Dexie {
  sitios!: EntityTable<CachedSitio, "id">;
  operaciones!: EntityTable<Operacion, "id">;
  fotos!: EntityTable<FotoLocal, "id">;
  meta!: EntityTable<MetaRow, "key">;

  constructor(name = "pipeline-coordinador") {
    super(name);
    this.version(1).stores({
      sitios: "id, updatedAt",
      operaciones: "id, sitioId, estado, seq, [sitioId+seq]",
      fotos: "id, sitioId",
      meta: "key",
    });
  }
}

let instance: PipelineDb | null = null;

export function getDb(): PipelineDb {
  if (!instance) instance = new PipelineDb();
  return instance;
}

export async function getMeta<T>(db: PipelineDb, key: string): Promise<T | undefined> {
  const row = await db.meta.get(key);
  return row?.value as T | undefined;
}

export async function setMeta(db: PipelineDb, key: string, value: unknown): Promise<void> {
  await db.meta.put({ key, value });
}

/** Clear every local table. Called on logout (TDD 5.4: cache is removed when the session ends). */
export async function clearLocalData(db: PipelineDb): Promise<void> {
  await db.transaction("rw", db.sitios, db.operaciones, db.fotos, db.meta, async () => {
    await Promise.all([db.sitios.clear(), db.operaciones.clear(), db.fotos.clear(), db.meta.clear()]);
  });
}
