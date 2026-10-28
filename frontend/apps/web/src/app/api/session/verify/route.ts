import { cookies } from "next/headers";
import { backendHeaders, backendUrl, forBrowser, isSameOrigin, jsonResponse, problem, refreshCookie, relayFailure, unavailable, type LoginTokens } from "@/lib/server/backend";

// Checks the login code with the backend, keeps the refresh token in an httpOnly cookie, and gives the browser only the access token.
export async function POST(request: Request): Promise<Response> {
  if (!isSameOrigin(request)) return problem(403, "forbidden");
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return problem(400, "bad_request");
  }
  let upstream: Response;
  try {
    upstream = await fetch(`${backendUrl()}/api/v1/auth/otp/verify`, { method: "POST", headers: backendHeaders(request), body: JSON.stringify(body), cache: "no-store" });
  } catch {
    return unavailable();
  }
  if (!upstream.ok) return relayFailure(upstream);
  const tokens = (await upstream.json()) as LoginTokens;
  (await cookies()).set(refreshCookie(tokens.refresh_token, tokens.refresh_expires_in));
  return jsonResponse(forBrowser(tokens));
}
