import { cookies } from "next/headers";
import { REFRESH_COOKIE, backendHeaders, backendUrl, forBrowser, isSameOrigin, jsonResponse, problem, refreshCookie, relayFailure, unavailable, type LoginTokens } from "@/lib/server/backend";

// Swaps the cookie's refresh token for a new access token and a new refresh token (the backend ends the old one). A refused
// token clears the cookie; a busy or unreachable backend does not, because the person is still signed in.
export async function POST(request: Request): Promise<Response> {
  if (!isSameOrigin(request)) return problem(403, "forbidden");
  const jar = await cookies();
  const token = jar.get(REFRESH_COOKIE)?.value;
  if (!token) return problem(401, "no_session");
  let upstream: Response;
  try {
    upstream = await fetch(`${backendUrl()}/api/v1/auth/refresh`, { method: "POST", headers: backendHeaders(request), body: JSON.stringify({ refresh_token: token }), cache: "no-store" });
  } catch {
    return unavailable();
  }
  if (upstream.status === 401 || upstream.status === 422) {
    jar.delete({ name: REFRESH_COOKIE, path: "/api/session" });
    return relayFailure(upstream);
  }
  if (!upstream.ok) return relayFailure(upstream);
  const tokens = (await upstream.json()) as LoginTokens;
  jar.set(refreshCookie(tokens.refresh_token, tokens.refresh_expires_in));
  return jsonResponse(forBrowser(tokens));
}
