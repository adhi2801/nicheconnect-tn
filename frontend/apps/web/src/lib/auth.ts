import { api } from "./api";
import { startSession, type Role } from "./session";

// What went wrong, in the terms a screen needs. The API's stable `code` and the HTTP status decide it, never the wording
// (docs/standards/backend.md section 3).
export type Failure = {
  ok: false;
  kind: "invalid_input" | "invalid_code" | "rate_limited" | "busy" | "suspended" | "role_conflict" | "phone_change_waiting" | "network" | "unknown";
  retryAfter?: number;
  requestId?: string;
};

type Problem = { code?: string; request_id?: string | null } | undefined;

function failureFrom(response: Response, error: unknown, step: "request" | "verify"): Failure {
  const problem = error as Problem;
  const code = problem?.code;
  const retry = Number(response.headers.get("Retry-After"));
  const base = { ok: false as const, requestId: problem?.request_id ?? undefined, retryAfter: Number.isFinite(retry) && retry > 0 ? retry : undefined };
  if (response.status === 429) return { ...base, kind: "rate_limited" };
  if (response.status === 503 || code === "service_busy") return { ...base, kind: "busy" };
  if (response.status === 403 && code === "account_suspended") return { ...base, kind: "suspended" };
  if (response.status === 409 && code === "phone_change_waiting") return { ...base, kind: "phone_change_waiting" };
  if (response.status === 409) return { ...base, kind: "role_conflict" };
  if (response.status === 422) return { ...base, kind: "invalid_input" };
  if (response.status === 400 && step === "verify") return { ...base, kind: "invalid_code" };
  return { ...base, kind: "unknown" };
}

const offline: Failure = { ok: false, kind: "network" };

export async function requestCode(phone: string): Promise<{ ok: true; expiresInSeconds: number } | Failure> {
  try {
    const { data, error, response } = await api.POST("/api/v1/auth/otp/request", { body: { phone } });
    if (data) return { ok: true, expiresInSeconds: data.expires_in_seconds };
    return failureFrom(response, error, "request");
  } catch {
    return offline;
  }
}

// The code is checked through the website's own session route, so the refresh token goes into an httpOnly cookie and never
// reaches this page (app/api/session/verify).
export async function verifyCode(input: { phone: string; code: string; role: Role }): Promise<{ ok: true; role: Role; isNew: boolean } | Failure> {
  try {
    const response = await fetch("/api/session/verify", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(input), cache: "no-store" });
    if (!response.ok) return failureFrom(response, await response.json().catch(() => undefined), "verify");
    const grant = (await response.json()) as { access_token: string; expires_in: number; account: { id: string; role: string; is_new: boolean } };
    startSession(grant);
    return { ok: true, role: input.role, isNew: grant.account.is_new };
  } catch {
    return offline;
  }
}
