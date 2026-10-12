import type { AuthProvider } from "@pipeline/auth";

import { ApiError, NetworkError, type ProblemDetails } from "./problem";

export interface RequestOptions {
  body?: unknown;
  /** Raw body (Blob/ArrayBuffer) sent as application/octet-stream. */
  raw?: BodyInit;
  idempotencyKey?: string;
  ifMatch?: string;
  signal?: AbortSignal;
  /** Per-request timeout; defaults to DEFAULT_TIMEOUT_MS. A timeout surfaces as NetworkError. */
  timeoutMs?: number;
  headers?: Record<string, string>;
  /** Send without Authorization (health endpoints). */
  anonymous?: boolean;
}

export interface ApiResponse<T> {
  data: T;
  status: number;
  etag: string | undefined;
  correlationId: string | undefined;
  headers: Headers;
}

export interface Api {
  request<T>(method: string, path: string, opts?: RequestOptions): Promise<ApiResponse<T>>;
  get<T>(path: string, opts?: RequestOptions): Promise<T>;
  post<T>(path: string, body?: unknown, opts?: RequestOptions): Promise<ApiResponse<T>>;
  put<T>(path: string, body?: unknown, opts?: RequestOptions): Promise<ApiResponse<T>>;
  del<T>(path: string, opts?: RequestOptions): Promise<ApiResponse<T>>;
  /** Fetch a binary resource (documents, photos). Returns the Response for streaming. */
  fetchRaw(path: string, opts?: RequestOptions): Promise<Response>;
}

export function newCorrelationId(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

export function stripEtag(etag: string | null | undefined): string | undefined {
  if (!etag) return undefined;
  return etag.replace(/^W\//, "").replace(/^"|"$/g, "");
}

/** No request may hang forever: a stalled fetch would otherwise freeze the sync engine (audit FE-3). */
export const DEFAULT_TIMEOUT_MS = 30_000;

function withTimeout(signal: AbortSignal | undefined, timeoutMs: number): AbortSignal | undefined {
  if (typeof AbortSignal === "undefined" || typeof AbortSignal.timeout !== "function") return signal;
  const timer = AbortSignal.timeout(timeoutMs);
  if (!signal) return timer;
  return typeof AbortSignal.any === "function" ? AbortSignal.any([signal, timer]) : signal;
}

/** A caller's own abort is rethrown; a timeout (or any other fetch failure) is a transient NetworkError. */
function toNetworkError(e: unknown, callerSignal: AbortSignal | undefined): never {
  if (e instanceof DOMException && e.name === "AbortError" && callerSignal?.aborted) throw e;
  throw new NetworkError();
}

export function createApi(auth: AuthProvider, baseUrl = ""): Api {
  const base = baseUrl.replace(/\/$/, "");

  async function request<T>(method: string, path: string, opts: RequestOptions = {}): Promise<ApiResponse<T>> {
    const headers: Record<string, string> = {
      accept: "application/json, application/problem+json",
      "x-correlation-id": newCorrelationId(),
      ...opts.headers,
    };
    if (!opts.anonymous) headers["authorization"] = `Bearer ${await auth.getToken()}`;
    if (opts.idempotencyKey) headers["idempotency-key"] = opts.idempotencyKey;
    if (opts.ifMatch) headers["if-match"] = `"${stripEtag(opts.ifMatch)}"`;
    let body: BodyInit | undefined;
    if (opts.raw !== undefined) {
      headers["content-type"] = "application/octet-stream";
      body = opts.raw;
    } else if (opts.body !== undefined) {
      if (opts.body instanceof FormData) {
        body = opts.body;
      } else {
        headers["content-type"] = "application/json";
        body = JSON.stringify(opts.body);
      }
    }
    let res: Response;
    try {
      const signal = withTimeout(opts.signal, opts.timeoutMs ?? DEFAULT_TIMEOUT_MS);
      res = await fetch(`${base}${path}`, { method, headers, body, signal });
    } catch (e) {
      toNetworkError(e, opts.signal);
    }
    const correlationId = res.headers.get("x-correlation-id") ?? undefined;
    if (!res.ok) {
      let problem: ProblemDetails | null = null;
      try {
        problem = (await res.json()) as ProblemDetails;
      } catch {
        problem = null;
      }
      throw new ApiError(res.status, problem, `HTTP ${res.status}`);
    }
    const etag = stripEtag(res.headers.get("etag"));
    if (res.status === 204) {
      return { data: undefined as T, status: res.status, etag, correlationId, headers: res.headers };
    }
    const data = (await res.json()) as T;
    return { data, status: res.status, etag, correlationId, headers: res.headers };
  }

  async function fetchRaw(path: string, opts: RequestOptions = {}): Promise<Response> {
    const headers: Record<string, string> = { "x-correlation-id": newCorrelationId(), ...opts.headers };
    if (!opts.anonymous) headers["authorization"] = `Bearer ${await auth.getToken()}`;
    let res: Response;
    try {
      const signal = withTimeout(opts.signal, opts.timeoutMs ?? DEFAULT_TIMEOUT_MS);
      res = await fetch(`${base}${path}`, { headers, signal });
    } catch (e) {
      toNetworkError(e, opts.signal);
    }
    if (!res.ok) {
      let problem: ProblemDetails | null = null;
      try {
        problem = (await res.json()) as ProblemDetails;
      } catch {
        problem = null;
      }
      throw new ApiError(res.status, problem, `HTTP ${res.status}`);
    }
    return res;
  }

  return {
    request,
    get: async <T,>(path: string, opts?: RequestOptions) => (await request<T>("GET", path, opts)).data,
    post: <T,>(path: string, body?: unknown, opts?: RequestOptions) => request<T>("POST", path, { ...opts, body }),
    put: <T,>(path: string, body?: unknown, opts?: RequestOptions) => request<T>("PUT", path, { ...opts, body }),
    del: <T,>(path: string, opts?: RequestOptions) => request<T>("DELETE", path, opts),
    fetchRaw,
  };
}
