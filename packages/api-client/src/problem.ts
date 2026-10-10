/** RFC 9457 Problem Details as produced by the API (app/core/errors.py). */
export interface ProblemDetails {
  type: string;
  title: string;
  status: number;
  detail: string;
  instance?: string;
  correlation_id?: string;
  [extra: string]: unknown;
}

export class ApiError extends Error {
  readonly status: number;
  readonly problem: ProblemDetails | null;
  readonly correlationId: string | undefined;

  constructor(status: number, problem: ProblemDetails | null, fallback: string) {
    super(problem?.detail || problem?.title || fallback);
    this.name = "ApiError";
    this.status = status;
    this.problem = problem;
    this.correlationId = problem?.correlation_id;
  }

  get slug(): string {
    return this.problem?.type.split("/").pop() ?? "http-error";
  }

  get isPreconditionFailed(): boolean {
    return this.status === 412;
  }

  get isUnauthorized(): boolean {
    return this.status === 401;
  }

  /** Current server state attached to a 412. */
  get current(): unknown {
    return this.problem?.["current"];
  }
}

export class NetworkError extends Error {
  constructor(message = "Sin conexión con el servidor") {
    super(message);
    this.name = "NetworkError";
  }
}
