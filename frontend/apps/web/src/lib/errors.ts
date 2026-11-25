// What went wrong with a call to the backend, in the terms a screen needs. The status and the stable `code` decide it, never the
// wording (docs/standards/backend.md section 3).
// conflict: the state on the server says no (a handle taken, already applied). invalid: the input was refused (422, or a 400).
// withheld: taken down for legal reasons (451), so it exists but cannot be shown.
export type ErrorKind = "network" | "busy" | "rate_limited" | "unauthorized" | "forbidden" | "not_found" | "conflict" | "invalid" | "withheld" | "unknown";

/** One refused field, as the backend's 422 names it. The message is the backend's; screens show their own words, keyed by field. */
export type FieldError = { field: string; message: string };

export class ApiError extends Error {
  readonly kind: ErrorKind;
  readonly status?: number;
  readonly code?: string;
  readonly requestId?: string;
  /** Seconds the backend asked us to wait. */
  readonly retryAfter?: number;
  readonly fields: FieldError[];

  constructor(kind: ErrorKind, status?: number, code?: string, requestId?: string, retryAfter?: number, fields: FieldError[] = []) {
    super(kind);
    this.kind = kind;
    this.status = status;
    this.code = code;
    this.requestId = requestId;
    this.retryAfter = retryAfter;
    this.fields = fields;
  }
}

type Problem = { code?: string; request_id?: string | null; errors?: unknown } | undefined;

export function kindFromStatus(status: number, code?: string): ErrorKind {
  if (status === 503 || code === "service_busy") return "busy";
  if (status === 429) return "rate_limited";
  if (status === 401) return "unauthorized";
  if (status === 403) return "forbidden";
  if (status === 404) return "not_found";
  if (status === 409) return "conflict";
  if (status === 451) return "withheld";
  if (status === 422 || status === 400) return "invalid";
  return "unknown";
}

// Only well-formed entries are kept: a body we do not recognise gives no field errors, never a crash.
function fieldsOf(errors: unknown): FieldError[] {
  if (!Array.isArray(errors)) return [];
  return errors.filter((e): e is FieldError => typeof e === "object" && e !== null && typeof (e as FieldError).field === "string" && typeof (e as FieldError).message === "string");
}

export function apiErrorFrom(response: Response, body: unknown): ApiError {
  const problem = body as Problem;
  const retry = Number(response.headers.get("Retry-After"));
  return new ApiError(kindFromStatus(response.status, problem?.code), response.status, problem?.code, problem?.request_id ?? undefined, Number.isFinite(retry) && retry > 0 ? retry : undefined, fieldsOf(problem?.errors));
}

/** The words for a failure no screen has its own words for. Never a status code, never "error" alone (frontend.md section 5). */
export function commonWordsKey(error: unknown): "common.offline" | "common.busy" | "common.rateLimited" | "common.somethingWrong" {
  if (!(error instanceof ApiError)) return "common.somethingWrong";
  if (error.kind === "network") return "common.offline";
  if (error.kind === "busy") return "common.busy";
  if (error.kind === "rate_limited") return "common.rateLimited";
  return "common.somethingWrong";
}

/** A 503 `service_busy` is "try again", never an error screen (docs/standards/frontend.md section 5): wait what the backend said,
 *  add a little jitter, repeat the same request, at most three times. A 429 is the person's own pace and is never retried. */
export const shouldRetry = (failures: number, error: unknown): boolean => error instanceof ApiError && error.kind === "busy" && failures < 3;
export const retryDelayMs = (error: unknown, random: () => number = Math.random): number => ((error instanceof ApiError && error.retryAfter) || 2) * 1000 + random() * 500;
