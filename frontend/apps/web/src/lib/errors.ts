// What went wrong with a call to the backend, in the terms a screen needs. The status and the stable `code` decide it, never the
// wording (docs/standards/backend.md section 3).
export type ErrorKind = "network" | "busy" | "rate_limited" | "unauthorized" | "forbidden" | "not_found" | "unknown";

export class ApiError extends Error {
  readonly kind: ErrorKind;
  readonly status?: number;
  readonly code?: string;
  readonly requestId?: string;
  /** Seconds the backend asked us to wait. */
  readonly retryAfter?: number;

  constructor(kind: ErrorKind, status?: number, code?: string, requestId?: string, retryAfter?: number) {
    super(kind);
    this.kind = kind;
    this.status = status;
    this.code = code;
    this.requestId = requestId;
    this.retryAfter = retryAfter;
  }
}

type Problem = { code?: string; request_id?: string | null } | undefined;

export function kindFromStatus(status: number, code?: string): ErrorKind {
  if (status === 503 || code === "service_busy") return "busy";
  if (status === 429) return "rate_limited";
  if (status === 401) return "unauthorized";
  if (status === 403) return "forbidden";
  if (status === 404) return "not_found";
  return "unknown";
}

export function apiErrorFrom(response: Response, body: unknown): ApiError {
  const problem = body as Problem;
  const retry = Number(response.headers.get("Retry-After"));
  return new ApiError(kindFromStatus(response.status, problem?.code), response.status, problem?.code, problem?.request_id ?? undefined, Number.isFinite(retry) && retry > 0 ? retry : undefined);
}

/** A 503 `service_busy` is "try again", never an error screen (docs/standards/frontend.md section 5): wait what the backend said,
 *  add a little jitter, repeat the same request, at most three times. A 429 is the person's own pace and is never retried. */
export const shouldRetry = (failures: number, error: unknown): boolean => error instanceof ApiError && error.kind === "busy" && failures < 3;
export const retryDelayMs = (error: unknown, random: () => number = Math.random): number => ((error instanceof ApiError && error.retryAfter) || 2) * 1000 + random() * 500;
