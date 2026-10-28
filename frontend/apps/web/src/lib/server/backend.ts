// Server-side helpers for the session routes under app/api/session. The browser never receives the refresh token:
// it lives in an httpOnly cookie that only these routes read (docs/standards/frontend.md section 10).
import type { components } from "@colyv/api";

export type LoginTokens = components["schemas"]["LoginTokens"];

export const REFRESH_COOKIE = "colyv_rt";
export const backendUrl = (): string => process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Only the website's own pages may call these routes. SameSite=Strict on the cookie is the first defence; this is the second. */
export function isSameOrigin(request: Request): boolean {
  const origin = request.headers.get("origin");
  const host = request.headers.get("host");
  if (!origin || !host) return false;
  try {
    return new URL(origin).host === host;
  } catch {
    return false;
  }
}

/** Headers for a call to the backend. The person's address goes along so the backend's per-address limits count the person,
 *  not this server (app/core/client_ip.py reads X-Forwarded-For from the proxies in TRUSTED_PROXIES). */
export function backendHeaders(request: Request): Headers {
  const headers = new Headers({ "content-type": "application/json", accept: "application/json" });
  const forwarded = request.headers.get("x-forwarded-for");
  if (forwarded) headers.set("x-forwarded-for", forwarded);
  return headers;
}

export function refreshCookie(value: string, maxAge: number) {
  return { name: REFRESH_COOKIE, value, httpOnly: true, secure: process.env.NODE_ENV === "production", sameSite: "strict" as const, path: "/api/session", maxAge };
}

const noStore = { "cache-control": "no-store" };

export const jsonResponse = (body: unknown, status = 200): Response =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json", ...noStore } });

export const problem = (status: number, code: string): Response =>
  new Response(JSON.stringify({ type: `about:blank`, title: code, status, code, request_id: null }), { status, headers: { "content-type": "application/problem+json", ...noStore } });

/** The backend could not be reached. Nothing was done, so the client treats it like "busy, try again". */
export const unavailable = (): Response => {
  const res = problem(503, "service_busy");
  res.headers.set("retry-after", "5");
  return res;
};

/** Hand a backend failure to the browser unchanged: its status, its problem body and its Retry-After. */
export async function relayFailure(upstream: Response): Promise<Response> {
  const headers = new Headers({ "content-type": upstream.headers.get("content-type") ?? "application/problem+json", ...noStore });
  const retry = upstream.headers.get("retry-after");
  if (retry) headers.set("retry-after", retry);
  return new Response(await upstream.text(), { status: upstream.status, headers });
}

/** What the browser may know about a login: everything except the refresh token. */
export const forBrowser = (t: LoginTokens) => ({ access_token: t.access_token, expires_in: t.expires_in, account: t.account });
