import { cookies } from "next/headers";
import { REFRESH_COOKIE, backendHeaders, backendUrl, isSameOrigin, problem } from "@/lib/server/backend";

// Ends the login at the backend and clears the cookie. The cookie is cleared even if the backend cannot be reached.
export async function POST(request: Request): Promise<Response> {
  if (!isSameOrigin(request)) return problem(403, "forbidden");
  const jar = await cookies();
  const token = jar.get(REFRESH_COOKIE)?.value;
  jar.delete({ name: REFRESH_COOKIE, path: "/api/session" });
  if (token) {
    try {
      await fetch(`${backendUrl()}/api/v1/auth/logout`, { method: "POST", headers: backendHeaders(request), body: JSON.stringify({ refresh_token: token }), cache: "no-store" });
    } catch {
      // The cookie is already gone; the backend ends the login when the token expires.
    }
  }
  return new Response(null, { status: 204, headers: { "cache-control": "no-store" } });
}
