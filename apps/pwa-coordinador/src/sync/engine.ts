/**
 * Offline queue and synchronization engine (ADR-005, TO_BE.md 6.2).
 *
 * - One FIFO chain per site; chains are independent (a conflict in one site never blocks another).
 * - The ETag returned by the previous operation is threaded into the next transition's If-Match.
 * - Every write carries an Idempotency-Key, so a retry after a lost response never duplicates.
 * - 412 / 422 / 404 / 409 block that operation and stop that site's chain; the server's current
 *   state (412 `current`) is stored for the conflict panel.
 * - Network failures and transient server errors (429, 5xx, timeouts) keep operations `pendiente`
 *   and auto-retry on the next sync, capped at MAX_TRANSIENT_RETRIES before surfacing as `error`.
 *   401 or InteractionRequired flags "needs login".
 * - Runs in the foreground only (the service worker cannot obtain tokens).
 */

import { ApiError, NetworkError, type Api } from "@pipeline/api-client";
import { InteractionRequired, OfflineError } from "@pipeline/auth";

import type { FotoLocal, Operacion, OperacionTipo, PipelineDb } from "../db/schema";
import { clearLocalData, getMeta, setMeta } from "../db/schema";
import type {
  ArchivoMeta,
  ContactoIn,
  ContactoResponse,
  SitioDelta,
  SitioDetail,
  SubidaOut,
  TransicionIn,
  VisitaIn,
  VisitaResponse,
} from "../lib/types";

/** How many times a transient (429/5xx/timeout) failure is auto-retried before it surfaces (E-1). */
export const MAX_TRANSIENT_RETRIES = 5;

export const META_MAX_ROWVERSION = "sitios.maxRowversion";
export const META_LAST_SYNC = "sync.lastAt";
/** oid of the account the local store belongs to; a different account must start empty (FE-1). */
export const META_OWNER_OID = "sync.ownerOid";

/**
 * Make the local store belong to `oid`. When another account owned it (or nobody did), every
 * cached site, queued operation, photo and cursor is dropped first: a second coordinator on the
 * same phone must never see the first one's data, send their queued writes, or inherit their
 * delta watermark. Returns true when the store was cleared.
 */
export async function ensureOwner(db: PipelineDb, oid: string): Promise<boolean> {
  const owner = await getMeta<string>(db, META_OWNER_OID);
  if (owner === oid) return false;
  await clearLocalData(db);
  await setMeta(db, META_OWNER_OID, oid);
  return true;
}
/** "site:etag" -> etag produced by this device's own successful write on top of it. */
export const META_ETAG_SUCCESSORS = "sync.etagSuccessors";
const MAX_SUCCESSORS = 200;

/**
 * An op is enqueued with the ETag the coordinator saw. If an earlier op of the same site was still
 * in flight, that ETag is superseded by this device's own write, and sending it would earn a
 * false 412 (risk R24). Follow the chain of our own successful writes to the current ETag. A
 * change by anyone else never enters this map, so a genuinely stale ETag still gets its 412.
 */
async function resolveEtag(db: PipelineDb, sitioId: number, etag: string): Promise<string> {
  const map = (await getMeta<Record<string, string>>(db, META_ETAG_SUCCESSORS)) ?? {};
  let current = etag;
  for (let hops = 0; hops < 50 && map[`${sitioId}:${current}`]; hops++) current = map[`${sitioId}:${current}`]!;
  return current;
}

async function recordSuccessor(db: PipelineDb, sitioId: number, from: string, to: string): Promise<void> {
  if (!from || !to || from === to) return;
  const map = (await getMeta<Record<string, string>>(db, META_ETAG_SUCCESSORS)) ?? {};
  map[`${sitioId}:${from}`] = to;
  const keys = Object.keys(map);
  for (const k of keys.slice(0, Math.max(0, keys.length - MAX_SUCCESSORS))) delete map[k];
  await setMeta(db, META_ETAG_SUCCESSORS, map);
}

export interface SyncOutcome {
  sent: number;
  blocked: number;
  errors: number;
  offline: boolean;
  needsLogin: boolean;
}

export interface SyncDeps {
  api: Api;
  db: PipelineDb;
  now?: () => number;
  newId?: () => string;
}

function uuid(): string {
  return crypto.randomUUID();
}

export async function upsertSitio(db: PipelineDb, detail: SitioDetail): Promise<void> {
  await db.sitios.put({ id: detail.id, detail, etag: detail.etag, updatedAt: Date.now() });
}

export async function enqueue(
  deps: SyncDeps,
  sitioId: number,
  tipo: OperacionTipo,
  payload: unknown,
): Promise<Operacion> {
  const { db } = deps;
  const now = deps.now?.() ?? Date.now();
  const cached = await db.sitios.get(sitioId);
  const last = await db.operaciones.where("[sitioId+seq]").between([sitioId, Dexie_MIN], [sitioId, Dexie_MAX]).last();
  const op: Operacion = {
    id: deps.newId?.() ?? uuid(),
    sitioId,
    tipo,
    payload,
    idempotencyKey: deps.newId?.() ?? uuid(),
    etagBase: cached?.etag ?? "",
    createdAt: now,
    seq: (last?.seq ?? 0) + 1,
    estado: "pendiente",
  };
  await db.operaciones.add(op);
  return op;
}

const Dexie_MIN = -Infinity;
const Dexie_MAX = Infinity;

export async function pendingForSitio(db: PipelineDb, sitioId: number): Promise<Operacion[]> {
  const ops = await db.operaciones.where("sitioId").equals(sitioId).sortBy("seq");
  return ops;
}

export async function discardOperation(db: PipelineDb, opId: string): Promise<void> {
  const op = await db.operaciones.get(opId);
  if (!op) return;
  if (op.tipo === "foto") {
    const fotoId = (op.payload as { fotoId: string }).fotoId;
    await db.fotos.delete(fotoId);
  }
  await db.operaciones.delete(opId);
}

/** User acknowledged the server change: retry against the current cached ETag. */
export async function retryOperation(db: PipelineDb, opId: string): Promise<void> {
  const op = await db.operaciones.get(opId);
  if (!op) return;
  const cached = await db.sitios.get(op.sitioId);
  await db.operaciones.update(opId, {
    estado: "pendiente",
    error: undefined,
    conflict: undefined,
    faltantes: undefined,
    intentos: 0, // a manual retry starts the transient-retry budget over (audit E-1 follow-up)
    etagBase: cached?.etag ?? op.etagBase,
  });
}

type StepResult =
  | { kind: "ok"; etag: string }
  | { kind: "blocked" }
  | { kind: "error" }
  | { kind: "offline" }
  | { kind: "login" };

async function sendOne(deps: SyncDeps, op: Operacion, etag: string): Promise<StepResult> {
  const { api, db } = deps;
  const path = `/api/v1/sitios/${op.sitioId}`;
  try {
    if (op.tipo === "contacto") {
      const r = await api.put<ContactoResponse>(`${path}/contacto`, op.payload as ContactoIn, {
        idempotencyKey: op.idempotencyKey,
      });
      await patchCached(db, op.sitioId, (d) => ({ ...d, contacto: r.data, etag: r.data.etag }));
      return { kind: "ok", etag: r.data.etag };
    }
    if (op.tipo === "visita") {
      const r = await api.put<VisitaResponse>(`${path}/visita`, op.payload as VisitaIn, {
        idempotencyKey: op.idempotencyKey,
      });
      await patchCached(db, op.sitioId, (d) => ({ ...d, visita: r.data, etag: r.data.etag }));
      return { kind: "ok", etag: r.data.etag };
    }
    if (op.tipo === "transicion") {
      const r = await api.post<SitioDetail>(`${path}/transiciones`, op.payload as TransicionIn, {
        idempotencyKey: op.idempotencyKey,
        ifMatch: etag,
      });
      await upsertSitio(db, r.data);
      return { kind: "ok", etag: r.data.etag };
    }
    // foto
    const { fotoId } = op.payload as { fotoId: string };
    const foto = await db.fotos.get(fotoId);
    if (!foto) {
      await db.operaciones.delete(op.id); // nothing to upload (blob gone)
      return { kind: "ok", etag };
    }
    await uploadFoto(api, op, foto);
    await db.fotos.delete(fotoId);
    return { kind: "ok", etag };
  } catch (e) {
    return await classifyFailure(db, op, e);
  }
}

async function uploadFoto(api: Api, op: Operacion, foto: FotoLocal): Promise<ArchivoMeta | null> {
  const created = await api.post<SubidaOut>(
    "/api/v1/subidas",
    {
      sitio_id: op.sitioId,
      tipo: "foto",
      nombre_original: foto.nombre,
      content_type: foto.blob.type || "image/jpeg",
      bytes_total: foto.bytes,
      sha256: foto.sha256,
    },
    { idempotencyKey: op.idempotencyKey },
  );
  const session = created.data;
  if (session.estado === "publicada") return null;
  const received = new Set(session.partes_recibidas);
  for (let n = 0; n < session.partes_total; n++) {
    if (received.has(n)) continue;
    const slice = foto.blob.slice(n * session.tamano_parte, (n + 1) * session.tamano_parte);
    await api.put(`/api/v1/subidas/${session.id}/partes/${n}`, undefined, { raw: slice });
  }
  const done = await api.post<ArchivoMeta | { estado: string; id: string }>(
    `/api/v1/subidas/${session.id}/completar`,
  );
  return done.status === 200 ? (done.data as ArchivoMeta) : null;
}

function isTransient(e: unknown): boolean {
  return e instanceof ApiError && (e.status === 429 || e.status >= 500);
}

async function classifyFailure(db: PipelineDb, op: Operacion, e: unknown): Promise<StepResult> {
  if (e instanceof OfflineError || e instanceof NetworkError) return { kind: "offline" };
  if (e instanceof InteractionRequired) return { kind: "login" };
  if (e instanceof ApiError) {
    if (e.status === 401) return { kind: "login" };
    if ([412, 422, 404, 409, 428, 410].includes(e.status)) {
      const current = (e.current as SitioDetail | undefined) ?? null;
      const faltantes = (e.problem?.["faltantes"] as string[] | undefined) ?? undefined;
      const siguiente = e.problem?.["estatus_siguiente"] as string | undefined;
      let message = e.message;
      if (e.status === 404) message = "El sitio ya no está asignado a ti o no existe.";
      if (siguiente) message = `${message} (siguiente: ${siguiente})`;
      await db.operaciones.update(op.id, { estado: "bloqueada", error: message, conflict: current, faltantes });
      if (current) await upsertSitio(db, current);
      return { kind: "blocked" };
    }
    // Transient server errors (429 and 5xx) are retryable. Behind a reverse proxy (Front Door ->
    // Container Apps) a deploy, scale event or brief DB failover surfaces as a 5xx, not a
    // NetworkError, so treating these as terminal would wedge the whole site chain with no
    // auto-retry (audit E-1). Keep the op pending and let the next sync drain it, capping attempts
    // so a genuinely poisoned request eventually surfaces for manual resolution.
    if (isTransient(e)) {
      const intentos = (op.intentos ?? 0) + 1;
      if (intentos >= MAX_TRANSIENT_RETRIES) {
        await db.operaciones.update(op.id, {
          estado: "error",
          intentos,
          error: "No se pudo sincronizar tras varios intentos. Reintenta cuando la conexión sea estable.",
        });
        return { kind: "error" };
      }
      await db.operaciones.update(op.id, { estado: "pendiente", intentos });
      return { kind: "offline" };
    }
    await db.operaciones.update(op.id, { estado: "error", error: `${e.message} (${e.status})` });
    return { kind: "error" };
  }
  await db.operaciones.update(op.id, { estado: "error", error: e instanceof Error ? e.message : String(e) });
  return { kind: "error" };
}

async function patchCached(db: PipelineDb, sitioId: number, fn: (d: SitioDetail) => SitioDetail): Promise<void> {
  const cached = await db.sitios.get(sitioId);
  if (!cached) return;
  const detail = fn(cached.detail);
  await db.sitios.put({ id: sitioId, detail, etag: detail.etag, updatedAt: Date.now() });
}

let running = false;

/** Push every pending chain, then pull the delta. Safe to call often; concurrent calls coalesce. */
export async function syncAll(deps: SyncDeps): Promise<SyncOutcome> {
  const outcome: SyncOutcome = { sent: 0, blocked: 0, errors: 0, offline: false, needsLogin: false };
  if (running) return outcome;
  running = true;
  try {
    const { db } = deps;
    const pending = await db.operaciones.where("estado").anyOf(["pendiente", "enviando"]).sortBy("seq");
    const bySite = new Map<number, Operacion[]>();
    for (const op of pending) {
      const list = bySite.get(op.sitioId) ?? [];
      list.push(op);
      bySite.set(op.sitioId, list);
    }
    const blockedSites = new Set(
      (await db.operaciones.where("estado").anyOf(["bloqueada", "error"]).toArray()).map((o) => o.sitioId),
    );
    const touched = new Set<number>();
    siteLoop: for (const [sitioId, ops] of bySite) {
      if (blockedSites.has(sitioId)) continue; // chain stays halted until the user resolves it
      let etag = await resolveEtag(db, sitioId, ops[0]?.etagBase ?? "");
      for (const op of ops) {
        await db.operaciones.update(op.id, { estado: "enviando" });
        const r = await sendOne(deps, op, etag);
        if (r.kind === "ok") {
          await recordSuccessor(db, sitioId, etag, r.etag);
          etag = r.etag || etag;
          await db.operaciones.delete(op.id);
          outcome.sent += 1;
          touched.add(sitioId);
          continue;
        }
        if (r.kind === "blocked") {
          outcome.blocked += 1;
          // Show the server's state next to the blocked change, even when the rejection was a
          // business rule (422) rather than a precondition (412).
          try {
            const current = await refreshSitio(deps, sitioId);
            const stored = await db.operaciones.get(op.id);
            if (current && stored && !stored.conflict) {
              await db.operaciones.update(op.id, { conflict: current });
            }
          } catch {
            /* offline while refreshing: the panel still shows the message */
          }
          break; // stop this chain only
        }
        if (r.kind === "error") {
          outcome.errors += 1;
          break;
        }
        await db.operaciones.update(op.id, { estado: "pendiente" });
        if (r.kind === "offline") {
          outcome.offline = true;
          break siteLoop;
        }
        outcome.needsLogin = true;
        break siteLoop;
      }
    }
    if (!outcome.offline && !outcome.needsLogin) {
      try {
        for (const id of touched) await refreshSitio(deps, id);
        await pullDelta(deps);
        await setMeta(db, META_LAST_SYNC, deps.now?.() ?? Date.now());
      } catch (e) {
        // A transient server error while pulling is retried like being offline (audit E-1).
        if (e instanceof OfflineError || e instanceof NetworkError || isTransient(e)) outcome.offline = true;
        else if (e instanceof InteractionRequired || (e instanceof ApiError && e.status === 401)) {
          outcome.needsLogin = true;
        } else throw e;
      }
    }
    return outcome;
  } finally {
    running = false;
  }
}

export async function refreshSitio(deps: SyncDeps, sitioId: number): Promise<SitioDetail | null> {
  try {
    const detail = await deps.api.get<SitioDetail>(`/api/v1/sitios/${sitioId}`);
    await upsertSitio(deps.db, detail);
    return detail;
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) {
      await deps.db.sitios.delete(sitioId);
      return null;
    }
    throw e;
  }
}

/** Fetch changes since the last known rowversion and apply removals (reassigned sites). */
export async function pullDelta(deps: SyncDeps): Promise<SitioDelta> {
  const { api, db } = deps;
  const desde = await getMeta<string>(db, META_MAX_ROWVERSION);
  const known = await db.sitios.toCollection().primaryKeys();
  const params = new URLSearchParams();
  if (desde) params.set("desde", desde);
  if (known.length) params.set("conocidos", known.join(","));
  const qs = params.toString();
  const delta = await api.get<SitioDelta>(`/api/v1/sitios/delta${qs ? `?${qs}` : ""}`);
  await db.transaction("rw", db.sitios, db.meta, async () => {
    for (const item of delta.items) {
      await db.sitios.put({ id: item.id, detail: item, etag: item.etag, updatedAt: Date.now() });
    }
    if (delta.removed_ids.length) await db.sitios.bulkDelete(delta.removed_ids);
    await db.meta.put({ key: META_MAX_ROWVERSION, value: delta.max_rowversion });
  });
  return delta;
}
