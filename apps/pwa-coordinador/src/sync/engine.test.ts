import "fake-indexeddb/auto";

import { ApiError, NetworkError, type Api, type ApiResponse, type RequestOptions } from "@pipeline/api-client";
import { beforeEach, describe, expect, it } from "vitest";

import { PipelineDb } from "../db/schema";
import type { SitioDetail } from "../lib/types";
import { META_LOST_OPS, META_MAX_ROWVERSION, META_OWNER_OID, ensureOwner, enqueue, pullDelta, retryOperation, syncAll, upsertSitio, type SyncDeps } from "./engine";

function detail(id: number, estatus: string, etag: string, extra: Partial<SitioDetail> = {}): SitioDetail {
  return {
    id,
    origen_id: 1000 + id,
    nombre: `Sitio ${id}`,
    region: "Xalapa",
    lat: "19.5",
    lon: "-96.9",
    potencial: "Alto",
    campos_capturados: 4,
    campos_total: 24,
    estatus,
    devuelto: false,
    usuario_codigo: "ard",
    en_revision_admin: false,
    vigente: true,
    actualizado_utc: "2026-10-10T00:00:00",
    etag,
    gps_texto: null,
    fecha_origen_utc: "2026-10-01T00:00:00",
    devolucion_motivo: null,
    devolucion_comentario: null,
    contacto: null,
    visita: null,
    archivos: [],
    coordinador_oid: null,
    ...extra,
  } as SitioDetail;
}

interface Call {
  method: string;
  path: string;
  opts: RequestOptions;
}

/** Scriptable fake API: handlers decide the response per (method, path). */
class FakeApi implements Api {
  calls: Call[] = [];
  etags = new Map<number, number>(); // site -> version counter
  returned = new Map<number, SitioDetail>();
  failTransitionOnce: { sitioId: number; error: Error } | null = null;
  networkDown = false;
  deltaItems: SitioDetail[] = [];
  removedIds: number[] = [];

  private bump(sitioId: number): string {
    const v = (this.etags.get(sitioId) ?? 0) + 1;
    this.etags.set(sitioId, v);
    return `e${sitioId}-${v}`;
  }

  async request<T>(method: string, path: string, opts: RequestOptions = {}): Promise<ApiResponse<T>> {
    this.calls.push({ method, path, opts });
    if (this.networkDown) throw new NetworkError();
    const m = /^\/api\/v1\/sitios\/(\d+)\/(contacto|visita|transiciones)$/.exec(path);
    if (m) {
      const sitioId = Number(m[1]);
      const kind = m[2];
      if (kind === "transiciones") {
        if (this.failTransitionOnce && this.failTransitionOnce.sitioId === sitioId) {
          const err = this.failTransitionOnce.error;
          this.failTransitionOnce = null;
          // a real server answers the next GET with the same state it reported in `current`
          if (err instanceof ApiError && err.current) this.returned.set(sitioId, err.current as SitioDetail);
          throw err;
        }
        if (!opts.ifMatch) throw new ApiError(428, { type: "x/precondition-required", title: "If-Match", status: 428, detail: "" }, "428");
        const expected = `e${sitioId}-${this.etags.get(sitioId) ?? 0}`;
        if (opts.ifMatch !== expected) {
          throw new ApiError(
            412,
            { type: "x/precondition-failed", title: "cambió", status: 412, detail: "stale", current: detail(sitioId, "sitio_prospectado", expected) },
            "412",
          );
        }
        const etag = this.bump(sitioId);
        const d = detail(sitioId, (opts.body as { estatus_destino: string }).estatus_destino, etag);
        this.returned.set(sitioId, d);
        return { data: d as T, status: 201, etag, correlationId: "c", headers: new Headers() };
      }
      const etag = this.bump(sitioId);
      const body = { ...(opts.body as object), capturado_utc: "2026-10-10T00:00:00", etag };
      return { data: body as T, status: 200, etag, correlationId: "c", headers: new Headers() };
    }
    const g = /^\/api\/v1\/sitios\/(\d+)$/.exec(path);
    if (g && method === "GET") {
      const sitioId = Number(g[1]);
      const d = this.returned.get(sitioId) ?? detail(sitioId, "sitio_prospectado", `e${sitioId}-${this.etags.get(sitioId) ?? 0}`);
      return { data: d as T, status: 200, etag: d.etag, correlationId: "c", headers: new Headers() };
    }
    if (path.startsWith("/api/v1/sitios/delta")) {
      const data = { items: this.deltaItems, removed_ids: this.removedIds, max_rowversion: "00000000000000ff" };
      return { data: data as T, status: 200, etag: undefined, correlationId: "c", headers: new Headers() };
    }
    throw new Error(`unexpected ${method} ${path}`);
  }
  async get<T>(path: string, opts?: RequestOptions): Promise<T> {
    return (await this.request<T>("GET", path, opts)).data;
  }
  post<T>(path: string, body?: unknown, opts?: RequestOptions) {
    return this.request<T>("POST", path, { ...opts, body });
  }
  put<T>(path: string, body?: unknown, opts?: RequestOptions) {
    return this.request<T>("PUT", path, { ...opts, body });
  }
  del<T>(path: string, opts?: RequestOptions) {
    return this.request<T>("DELETE", path, opts);
  }
  async fetchRaw(): Promise<Response> {
    throw new Error("not used");
  }
}

let db: PipelineDb;
let api: FakeApi;
let deps: SyncDeps;
let n = 0;

beforeEach(async () => {
  db = new PipelineDb(`test-${Date.now()}-${n++}`);
  api = new FakeApi();
  deps = { api, db };
  await upsertSitio(db, detail(1, "sitio_prospectado", "e1-0"));
  await upsertSitio(db, detail(2, "sitio_prospectado", "e2-0"));
});

describe("sync engine", () => {
  it("threads the ETag from contacto into the transition If-Match and drains the chain", async () => {
    await enqueue(deps, 1, "contacto", { nombre: "Ana", telefono: "2281234567", correo: null, notas: null });
    await enqueue(deps, 1, "transicion", { estatus_destino: "dueno_localizado", comentario: null });
    const out = await syncAll(deps);
    expect(out.sent).toBe(2);
    const tr = api.calls.find((c) => c.path.endsWith("/transiciones"));
    expect(tr?.opts.ifMatch).toBe("e1-1"); // etag returned by the contacto PUT, not the stale e1-0
    expect(await db.operaciones.count()).toBe(0);
    expect((await db.sitios.get(1))?.detail.estatus).toBe("dueno_localizado");
  });

  it("advance queued while the contact is in flight uses the contact's new ETag (no false 412)", async () => {
    // The coordinator saves the contact and taps "advance" before the contact PUT has returned:
    // the transition is enqueued with the pre-contact ETag and is sent in the next pass.
    await enqueue(deps, 1, "contacto", { nombre: "Ana", telefono: "2281234567", correo: null, notas: null });
    const original = api.request.bind(api);
    let enqueuedDuringFlight = false;
    api.request = async <T,>(method: string, path: string, opts?: RequestOptions) => {
      if (!enqueuedDuringFlight && path.endsWith("/contacto")) {
        enqueuedDuringFlight = true;
        await enqueue(deps, 1, "transicion", { estatus_destino: "dueno_localizado", comentario: null });
      }
      return original<T>(method, path, opts);
    };
    const first = await syncAll(deps);
    expect(first.sent).toBe(1); // only the contact was pending when this pass started
    const second = await syncAll(deps);
    expect(second.blocked).toBe(0);
    expect(second.sent).toBe(1);
    expect(await db.operaciones.count()).toBe(0);
    expect((await db.sitios.get(1))?.detail.estatus).toBe("dueno_localizado");
  });

  it("an admin change between passes still blocks with 412 (successor map only covers own writes)", async () => {
    await enqueue(deps, 1, "transicion", { estatus_destino: "dueno_localizado", comentario: null });
    api.etags.set(1, 5); // someone else moved the server ahead; our base e1-0 is genuinely stale
    const out = await syncAll(deps);
    expect(out.blocked).toBe(1);
  });

  it("keeps a transient 5xx retryable and drains it on the next sync (E-1)", async () => {
    await enqueue(deps, 1, "transicion", { estatus_destino: "dueno_localizado", comentario: null });
    api.failTransitionOnce = {
      sitioId: 1,
      error: new ApiError(503, { type: "x/unavailable", title: "no disponible", status: 503, detail: "" }, "503"),
    };
    let out = await syncAll(deps);
    expect(out.offline).toBe(true); // transient server error, not a terminal error
    const op = (await db.operaciones.where("sitioId").equals(1).toArray())[0];
    expect(op?.estado).toBe("pendiente");
    expect(op?.intentos).toBe(1);
    // the server recovers; the next sync drains the op with no manual per-site retry
    out = await syncAll(deps);
    expect(out.sent).toBe(1);
    expect(await db.operaciones.count()).toBe(0);
  });

  it("treats a 5xx while pulling the delta as transient, not as a sync error (E-1)", async () => {
    const original = api.request.bind(api);
    api.request = async <T,>(method: string, path: string, opts?: RequestOptions) => {
      if (path.startsWith("/api/v1/sitios/delta")) {
        throw new ApiError(502, { type: "x/bad-gateway", title: "x", status: 502, detail: "" }, "502");
      }
      return original<T>(method, path, opts);
    };
    const out = await syncAll(deps);
    expect(out.offline).toBe(true);
  });

  it("sends an Idempotency-Key and reuses it after a network retry", async () => {
    await enqueue(deps, 1, "contacto", { nombre: "Ana", telefono: "2281234567", correo: null, notas: null });
    api.networkDown = true;
    let out = await syncAll(deps);
    expect(out.offline).toBe(true);
    expect((await db.operaciones.toArray())[0]?.estado).toBe("pendiente");
    const firstKey = api.calls[0]?.opts.idempotencyKey;
    api.networkDown = false;
    out = await syncAll(deps);
    expect(out.sent).toBe(1);
    const secondKey = api.calls.filter((c) => c.method === "PUT")[1]?.opts.idempotencyKey;
    expect(firstKey).toBeTruthy();
    expect(secondKey).toBe(firstKey);
  });

  it("blocks the chain of one site on 412 and keeps the other site moving", async () => {
    await enqueue(deps, 1, "transicion", { estatus_destino: "dueno_localizado", comentario: null });
    await enqueue(deps, 1, "visita", { frente_m: 1, fondo_m: 2, area_m2: null, notas: null, fecha_visita_utc: null });
    await enqueue(deps, 2, "contacto", { nombre: "B", telefono: "2281234567", correo: null, notas: null });
    api.failTransitionOnce = {
      sitioId: 1,
      error: new ApiError(
        412,
        { type: "x/precondition-failed", title: "cambió", status: 412, detail: "El registro cambió", current: detail(1, "sitio_prospectado", "e1-9", { devuelto: true, devolucion_comentario: "mal" }) },
        "412",
      ),
    };
    api.etags.set(1, 9); // the server really is at the version reported in `current`
    const out = await syncAll(deps);
    expect(out.blocked).toBe(1);
    expect(out.sent).toBe(1); // site 2 contacto went through
    const ops = await db.operaciones.where("sitioId").equals(1).sortBy("seq");
    expect(ops.map((o) => o.estado)).toEqual(["bloqueada", "pendiente"]);
    expect(ops[0]?.conflict?.devuelto).toBe(true);
    expect((await db.sitios.get(1))?.detail.devuelto).toBe(true); // cache updated with server truth
    // a second sync does not retry the blocked chain until the user resolves it
    const again = await syncAll(deps);
    expect(again.sent).toBe(0);
    // user retries against the current state: chain resumes with the refreshed etag
    await retryOperation(db, ops[0]!.id);
    const after = await syncAll(deps);
    expect(after.sent).toBe(2);
    expect(await db.operaciones.count()).toBe(0);
  });

  it("marks 422 as bloqueada with faltantes and does not send the next op of that site", async () => {
    await enqueue(deps, 1, "transicion", { estatus_destino: "dueno_localizado", comentario: null });
    await enqueue(deps, 1, "transicion", { estatus_destino: "primera_visita", comentario: null });
    api.failTransitionOnce = {
      sitioId: 1,
      error: new ApiError(422, { type: "x/unprocessable", title: "x", status: 422, detail: "faltan", faltantes: ["Captura el contacto"] }, "422"),
    };
    const out = await syncAll(deps);
    expect(out.blocked).toBe(1);
    const ops = await db.operaciones.where("sitioId").equals(1).sortBy("seq");
    expect(ops[0]?.faltantes).toEqual(["Captura el contacto"]);
    expect(ops[1]?.estado).toBe("pendiente");
    expect(api.calls.filter((c) => c.path.endsWith("/transiciones")).length).toBe(1);
  });

  it("flags needsLogin on 401 and keeps the queue", async () => {
    await enqueue(deps, 1, "contacto", { nombre: "Ana", telefono: "2281234567", correo: null, notas: null });
    api.request = async () => {
      throw new ApiError(401, { type: "x/unauthorized", title: "x", status: 401, detail: "" }, "401");
    };
    const out = await syncAll(deps);
    expect(out.needsLogin).toBe(true);
    expect(await db.operaciones.count()).toBe(1);
  });

  it("applies delta items and removed_ids to the cache", async () => {
    api.deltaItems = [detail(3, "primera_visita", "e3-1")];
    api.removedIds = [2];
    await pullDelta(deps);
    expect((await db.sitios.toCollection().primaryKeys()).sort()).toEqual([1, 3]);
    expect((await db.meta.get(META_MAX_ROWVERSION))?.value).toBe("00000000000000ff");
    const call = api.calls.find((c) => c.path.startsWith("/api/v1/sitios/delta"));
    expect(call?.path).toContain("conocidos=1%2C2");
    // second pull sends desde
    await pullDelta(deps);
    const second = api.calls.filter((c) => c.path.startsWith("/api/v1/sitios/delta"))[1];
    expect(second?.path).toContain("desde=00000000000000ff");
  });
});

describe("ensureOwner (FE-1: one store per account)", () => {
  it("clears sites, queued ops and the delta cursor when a different account signs in", async () => {
    const db = new PipelineDb(`owner-${Math.random()}`);
    await db.sitios.put({ id: 1, nombre: "A", estatus: "sitio_prospectado", etag: "e1" } as never);
    await enqueue({ api: new FakeApi(), db }, 1, "contacto", { nombre: "Ana", telefono: "2281234567", correo: null, notas: null });
    await db.meta.put({ key: META_MAX_ROWVERSION, value: "00ff" });
    await db.meta.put({ key: META_OWNER_OID, value: "oid-a" });

    expect(await ensureOwner(db, "oid-b")).toBe(true);
    expect(await db.sitios.count()).toBe(0);
    expect(await db.operaciones.count()).toBe(0);
    expect((await db.meta.get(META_MAX_ROWVERSION))?.value).toBeUndefined();
    expect((await db.meta.get(META_OWNER_OID))?.value).toBe("oid-b");
  });

  it("keeps everything when the same account signs in again", async () => {
    const db = new PipelineDb(`owner-${Math.random()}`);
    await db.sitios.put({ id: 1, nombre: "A", estatus: "sitio_prospectado", etag: "e1" } as never);
    await db.meta.put({ key: META_OWNER_OID, value: "oid-a" });
    expect(await ensureOwner(db, "oid-a")).toBe(false);
    expect(await db.sitios.count()).toBe(1);
  });

  it("claims an unowned store (first sign-in) without data loss on the first run", async () => {
    const db = new PipelineDb(`owner-${Math.random()}`);
    expect(await ensureOwner(db, "oid-a")).toBe(true);
    expect((await db.meta.get(META_OWNER_OID))?.value).toBe("oid-a");
  });
});

describe("sites reassigned away (FE-2)", () => {
  it("drops queued ops and photos of a removed site and counts them as lost", async () => {
    await enqueue(deps, 2, "contacto", { nombre: "Ana", telefono: "2281234567", correo: null, notas: null });
    await db.fotos.put({ id: "f1", sitioId: 2, nombre: "a.jpg", blob: new Blob(["x"]), bytes: 1, sha256: "s", creadoEn: 1 } as never);
    api.removedIds = [2];
    await pullDelta(deps);
    expect(await db.sitios.get(2)).toBeUndefined();
    expect(await db.operaciones.where("sitioId").equals(2).count()).toBe(0);
    expect(await db.fotos.where("sitioId").equals(2).count()).toBe(0);
    expect((await db.meta.get(META_LOST_OPS))?.value).toBe(1);
  });

  it("a 404 on refresh forgets the site and its queue", async () => {
    await enqueue(deps, 1, "contacto", { nombre: "Ana", telefono: "2281234567", correo: null, notas: null });
    const original = api.request.bind(api);
    api.request = async (method, path, opts) => {
      if (method === "GET" && path === "/api/v1/sitios/1") {
        throw new ApiError(404, { type: "x/not-found", title: "x", status: 404, detail: "" }, "404");
      }
      return original(method, path, opts);
    };
    const { refreshSitio } = await import("./engine");
    expect(await refreshSitio(deps, 1)).toBeNull();
    expect(await db.operaciones.count()).toBe(0);
  });
});

describe("photo upload replay (FE-4)", () => {
  function fakeUploadApi(liveEstado: string, created: { estado: string; partes_recibidas: number[] }) {
    const calls: string[] = [];
    const original = api.request.bind(api);
    api.request = async (method, path, opts) => {
      calls.push(`${method} ${path}`);
      const session = { id: "s1", estado: created.estado, partes_recibidas: created.partes_recibidas, partes_total: 1, tamano_parte: 10 };
      if (method === "POST" && path === "/api/v1/subidas") return { data: session as never, status: 201, etag: undefined, correlationId: "c", headers: new Headers() };
      if (method === "GET" && path === "/api/v1/subidas/s1") return { data: { ...session, estado: liveEstado } as never, status: 200, etag: undefined, correlationId: "c", headers: new Headers() };
      if (method === "PUT" && path.startsWith("/api/v1/subidas/s1/partes/")) return { data: { partes_recibidas: [0] } as never, status: 200, etag: undefined, correlationId: "c", headers: new Headers() };
      if (method === "POST" && path === "/api/v1/subidas/s1/completar") return { data: { id: "a1", estado: "publicado" } as never, status: 200, etag: undefined, correlationId: "c", headers: new Headers() };
      return original(method, path, opts);
    };
    return calls;
  }

  it("treats a replayed 'abierta' session that is already published as done", async () => {
    await db.fotos.put({ id: "f1", sitioId: 1, nombre: "a.jpg", blob: new Blob(["0123456789"]), bytes: 10, sha256: "s", creadoEn: 1 } as never);
    await enqueue(deps, 1, "foto", { fotoId: "f1" });
    const calls = fakeUploadApi("publicada", { estado: "abierta", partes_recibidas: [] });
    const out = await syncAll(deps);
    expect(out.blocked).toBe(0);
    expect(await db.operaciones.count()).toBe(0);
    expect(calls.some((c) => c.startsWith("PUT /api/v1/subidas/s1/partes"))).toBe(false);
  });

  it("mints a new idempotency key when the replayed session has expired", async () => {
    await db.fotos.put({ id: "f1", sitioId: 1, nombre: "a.jpg", blob: new Blob(["0123456789"]), bytes: 10, sha256: "s", creadoEn: 1 } as never);
    await enqueue(deps, 1, "foto", { fotoId: "f1" });
    const first = (await db.operaciones.toArray())[0]!.idempotencyKey;
    let gets = 0;
    const original = api.request.bind(api);
    const keys: (string | undefined)[] = [];
    api.request = async (method, path, opts) => {
      const session = { id: "s1", estado: "abierta", partes_recibidas: [0], partes_total: 1, tamano_parte: 10 };
      if (method === "POST" && path === "/api/v1/subidas") {
        keys.push(opts?.idempotencyKey);
        return { data: session as never, status: 201, etag: undefined, correlationId: "c", headers: new Headers() };
      }
      if (method === "GET" && path === "/api/v1/subidas/s1") {
        gets += 1;
        return { data: { ...session, estado: gets === 1 ? "expirada" : "abierta" } as never, status: 200, etag: undefined, correlationId: "c", headers: new Headers() };
      }
      if (method === "PUT" && path.startsWith("/api/v1/subidas/s1/partes/")) return { data: { partes_recibidas: [0] } as never, status: 200, etag: undefined, correlationId: "c", headers: new Headers() };
      if (method === "POST" && path === "/api/v1/subidas/s1/completar") return { data: { id: "a1", estado: "publicado" } as never, status: 200, etag: undefined, correlationId: "c", headers: new Headers() };
      return original(method, path, opts);
    };
    const out = await syncAll(deps);
    expect(out.blocked).toBe(0);
    expect(keys.length).toBe(2);
    expect(keys[1]).not.toBe(first);
    expect(await db.operaciones.count()).toBe(0);
  });
});
