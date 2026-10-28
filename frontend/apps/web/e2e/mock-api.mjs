// A stand-in for the backend's login endpoints, written to docs/api/openapi.json. It is NOT the real backend: it exists so the
// browser tests run anywhere. It refuses a refresh token used twice and ends every login, as the real one does (POST /auth/refresh).
import { createServer } from "node:http";

const port = Number(process.env.PORT ?? 8098);
const cors = { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "*", "Access-Control-Allow-Methods": "POST, GET, OPTIONS", "Access-Control-Expose-Headers": "Retry-After, X-Request-ID, WWW-Authenticate" };

let n, valid, used, reuseDetected, refreshCalls, lastForwardedFor, refreshDelayMs;
const reset = () => { n = 0; valid = new Map(); used = new Set(); reuseDetected = false; refreshCalls = 0; lastForwardedFor = null; refreshDelayMs = 0; };
reset();

const send = (res, status, body, extra = {}) => { res.writeHead(status, { ...cors, "Content-Type": status >= 400 ? "application/problem+json" : "application/json", ...extra }); res.end(body === undefined ? undefined : JSON.stringify(body)); };
const fail = (res, status, code, extra) => send(res, status, { type: "https://example.test/errors/" + code, title: code, status, code, detail: null, errors: null, request_id: "01MOCKREQUEST" }, extra);
const grant = (role, isNew) => {
  n += 1;
  const refresh = `mock-refresh-${n}-${Math.random().toString(36).slice(2)}-0123456789`;
  valid.set(refresh, role);
  return { access_token: `mock-access-${n}`, refresh_token: refresh, token_type: "bearer", expires_in: 900, refresh_expires_in: 2592000, account: { id: `acc-${role}`, role, is_new: isNew } };
};

createServer((req, res) => {
  if (req.method === "OPTIONS") { res.writeHead(204, cors); return res.end(); }
  let raw = "";
  req.on("data", (c) => (raw += c));
  req.on("end", async () => {
    const body = raw ? JSON.parse(raw) : {};
    if (req.url === "/__state") return send(res, 200, { reuseDetected, refreshCalls, lastForwardedFor, liveLogins: valid.size });
    if (req.url === "/__reset") { reset(); return send(res, 200, {}); }
    if (req.url === "/__slow-refresh") { refreshDelayMs = Number(body.ms ?? 0); return send(res, 200, {}); }
    if (req.url === "/api/v1/auth/otp/request") {
      if (body.phone === "+919000000429") return fail(res, 429, "rate_limited", { "Retry-After": "45" });
      return send(res, 202, { expires_in_seconds: 300 });
    }
    if (req.url === "/api/v1/auth/otp/verify") {
      lastForwardedFor = req.headers["x-forwarded-for"] ?? null;
      if (body.code === "429429") return fail(res, 429, "rate_limited", { "Retry-After": "30" });
      if (body.code !== "123456") return fail(res, 400, "otp_invalid");
      return send(res, 200, grant(body.role, true));
    }
    if (req.url === "/api/v1/auth/refresh") {
      refreshCalls += 1;
      if (refreshDelayMs) await new Promise((r) => setTimeout(r, refreshDelayMs));
      const token = body.refresh_token;
      if (used.has(token)) { reuseDetected = true; valid.clear(); return fail(res, 401, "refresh_reused"); }
      const role = valid.get(token);
      if (!role) return fail(res, 401, "refresh_invalid");
      valid.delete(token); used.add(token);
      return send(res, 200, grant(role, false));
    }
    if (req.url === "/api/v1/auth/logout") { valid.delete(body.refresh_token); res.writeHead(204, cors); return res.end(); }
    fail(res, 404, "not_found");
  });
}).listen(port, () => console.log(`mock api on ${port}`));
