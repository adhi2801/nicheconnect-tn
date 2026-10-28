// A stand-in for the backend's login endpoints, written to docs/api/openapi.json. It is NOT the real backend: it exists so the
// browser tests run anywhere. It refuses a refresh token used twice and ends every login, as the real one does (POST /auth/refresh).
import { createServer } from "node:http";

const port = Number(process.env.PORT ?? 8098);
const cors = { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "*", "Access-Control-Allow-Methods": "POST, GET, PUT, PATCH, DELETE, OPTIONS", "Access-Control-Expose-Headers": "Retry-After, X-Request-ID, WWW-Authenticate" };

let n, valid, used, reuseDetected, refreshCalls, lastForwardedFor, refreshDelayMs, tokens, scenario, calls;
const defaults = () => ({ attention: "items", profile: "found", totals: "money", unread: 3, busyOnce: false, deals: "full", names: true });
const reset = () => { n = 0; valid = new Map(); used = new Set(); tokens = new Map(); reuseDetected = false; refreshCalls = 0; lastForwardedFor = null; refreshDelayMs = 0; scenario = defaults(); calls = {}; };
reset();

const send = (res, status, body, extra = {}) => { res.writeHead(status, { ...cors, "Content-Type": status >= 400 ? "application/problem+json" : "application/json", ...extra }); res.end(body === undefined ? undefined : JSON.stringify(body)); };
const fail = (res, status, code, extra) => send(res, status, { type: "https://example.test/errors/" + code, title: code, status, code, detail: null, errors: null, request_id: "01MOCKREQUEST" }, extra);
const grant = (role, isNew) => {
  n += 1;
  const refresh = `mock-refresh-${n}-${Math.random().toString(36).slice(2)}-0123456789`;
  valid.set(refresh, role);
  tokens.set(`mock-access-${n}`, role);
  return { access_token: `mock-access-${n}`, refresh_token: refresh, token_type: "bearer", expires_in: 900, refresh_expires_in: 2592000, account: { id: `acc-${role}`, role, is_new: isNew } };
};

createServer((req, res) => {
  if (req.method === "OPTIONS") { res.writeHead(204, cors); return res.end(); }
  let raw = "";
  req.on("data", (c) => (raw += c));
  req.on("end", async () => {
    const body = raw ? JSON.parse(raw) : {};
    if (req.url === "/__state") return send(res, 200, { reuseDetected, refreshCalls, lastForwardedFor, liveLogins: valid.size, calls });
    if (req.url === "/__scenario") { scenario = { ...defaults(), ...body }; return send(res, 200, scenario); }
    if (req.url === "/__reset") { reset(); return send(res, 200, {}); }
    if (req.url === "/__slow-refresh") { refreshDelayMs = Number(body.ms ?? 0); return send(res, 200, {}); }

    // ---- Today's data. Each answers only to a token this mock issued, as the real ones do. ----
    const role = tokens.get((req.headers.authorization ?? "").replace("Bearer ", ""));
    const path = req.url.split("?")[0];
    if (path.startsWith("/api/v1/") && !path.startsWith("/api/v1/auth/")) {
      calls[path] = (calls[path] ?? 0) + 1;
      if (!role) return fail(res, 401, "not_authenticated");
      if (path === "/api/v1/creators/me" || path === "/api/v1/brands/me") {
        if (scenario.profile === "missing") return fail(res, 404, "profile_not_found");
        return send(res, 200, role === "creator" ? { id: "cr-1", display_name: "Lakshmi Loves", handle: "lakshmi" } : { id: "br-1", name: "Chennai Bakes" });
      }
      if (path === "/api/v1/notifications/unread-count") return send(res, 200, { unread: scenario.unread });
      if (path === "/api/v1/payments/mine/totals") {
        if (scenario.totals === "error") return fail(res, 500, "unexpected_error");
        const z = { amount_paise: 0, count: 0, currency: "INR" };
        if (scenario.totals === "zero") return send(res, 200, { as_of: "2026-10-28", to_pay: z, overdue: z, awaiting_confirmation: z, finished: z });
        return send(res, 200, { as_of: "2026-10-28", to_pay: { amount_paise: 1_150_000, count: 2, currency: "INR" }, overdue: { amount_paise: 650_000, count: 1, currency: "INR" }, awaiting_confirmation: { amount_paise: 700_000, count: 1, currency: "INR" }, finished: { amount_paise: 12_500_000, count: 9, currency: "INR" } });
      }

      if (path === "/api/v1/deal-memos/mine") {
        if (scenario.deals === "error") return fail(res, 500, "unexpected_error");
        if (scenario.deals === "empty") return send(res, 200, { items: [], next_cursor: null });
        // [id, stage, waiting_on, fee, content_due_on, brand name, creator name, campaign, dispute]
        const rows = [
          ["m-1", "payment", "creator", 700_000, "2026-10-14", "Chennai Bakes", "Lakshmi Loves", "Diwali sweets reel", false],
          ["m-2", "in_progress", "creator", 650_000, "2026-10-25", "Madurai Masala Co.", "Lakshmi Loves", "Spice box unboxing", false],
          ["m-3", "in_progress", "brand", 550_000, "2026-10-30", "Tanjore Coffee", "Priya Eats", "Filter coffee tasting", false],
          ["m-4", "memo_sent", "creator", 500_000, "2026-11-06", "Kovai Organics", "Karthik Bites", "Millet snacks launch", false],
          ["m-5", "agreed", "creator", 420_000, "2026-11-12", "Karur Kitchenware", "Divya Daily", "Kolu set styling", false],
          ["m-6", "finished", null, 800_000, "2026-10-02", "Anbu Sweets", "Arun Tastes", "Mithai box reel", false],
          ["m-7", "declined", null, 300_000, null, "Salem Spice House", "Rohit Reels", "Chilli powder shoot", false],
          ["m-8", "cancelled", null, 300_000, null, "Erode Textiles", "Kavya Plates", "Saree styling", false],
          ["m-11", "payment", "brand", 650_000, "2026-10-20", "Trichy Tiffins", "Suresh Snaps", "Combo meal reels", true],
        ];
        if (role === "brand") rows.push(["m-9", "draft", "brand", null, null, "Chennai Bakes", "Anand Cuts", "Protein laddu launch", false]);
        const items = rows.map(([id, stage, waiting, fee, due, brandName, creatorName, title, dispute]) => ({
          id, application_id: "a-" + id, stage, status: stage === "draft" ? "draft" : stage === "declined" ? "declined" : stage === "cancelled" ? "cancelled" : stage === "memo_sent" ? "sent" : "accepted",
          waiting_on: waiting, fee_amount_paise: fee, agreed_amount_paise: stage === "memo_sent" || stage === "draft" ? null : fee, content_due_on: due, updated_at: "2026-10-2" + (id.length % 9) + "T10:00:00Z", has_open_dispute: dispute, currency: "INR",
          ...(scenario.names ? { campaign_title: title, counterparty_name: role === "creator" ? brandName : creatorName } : {}),
        }));
        return send(res, 200, { items, next_cursor: null });
      }
      if (path === "/api/v1/payments/mine") {
        const pay = (id, memo, amount, state, due, days, brandName, creatorName, handle, title) => ({ id, deal_memo_id: memo, amount_paise: amount, state, due_on: due, days_overdue: days, brand_name: brandName, creator_display_name: creatorName, creator_handle: handle, campaign_title: title, campaign_id: "c-1", brand_id: "b-1", creator_id: "cr-9", currency: "INR", has_open_dispute: false, created_at: "2026-10-01T00:00:00Z", updated_at: "2026-10-01T00:00:00Z", marked_paid_at: null, confirmed_at: null, method: null, reference: null, reference_auto_matchable: false });
        if (scenario.deals === "empty") return send(res, 200, { items: [], next_cursor: null });
        return send(res, 200, { next_cursor: null, items: [
          pay("p-1", "m-1", 700_000, "paid", "2026-10-21", 0, "Chennai Bakes", "Lakshmi Loves", "lakshmi", "Diwali sweets reel"),
          pay("p-2", "m-11", 650_000, "late", "2026-10-25", 3, "Trichy Tiffins", "Suresh Snaps", "suresh", "Combo meal reels"),
          pay("p-3", "m-6", 800_000, "confirmed", "2026-10-09", 0, "Anbu Sweets", "Arun Tastes", "arun", "Mithai box reel"),
          pay("p-4", "m-20", 450_000, "due", "2026-11-05", 0, "Kovai Organics", "Karthik Bites", "karthik", "Millet snacks launch"),
        ] });
      }
      if (path === "/api/v1/me/attention") {
        if (scenario.attention === "error") return fail(res, 500, "unexpected_error");
        if (scenario.busyOnce && calls[path] === 1) return fail(res, 503, "service_busy", { "Retry-After": "1" });
        const item = (kind, extra) => ({ kind, memo_id: null, application_id: null, campaign_id: null, proof_id: null, session_id: null, counterparty: null, campaign_title: null, amount_paise: null, currency: null, count: null, days_left: null, due_on: null, device_label: null, device_platform: null, domain: null, signed_in_at: null, signed_in_with: null, ...extra });
        const creator = [
          item("new_sign_in", { session_id: "s-1", device_label: "Chrome on Windows", device_platform: "web" }),
          item("confirm_payment", { memo_id: "m-1", counterparty: "Chennai Bakes", campaign_title: "Diwali sweets reel", amount_paise: 700_000, currency: "INR", days_left: 0, due_on: "2026-10-28" }),
          item("deliver_work", { memo_id: "m-2", counterparty: "Madurai Masala Co.", campaign_title: "Spice box unboxing", days_left: -3, due_on: "2026-10-25" }),
          item("resubmit_work", { memo_id: "m-3", counterparty: "Tanjore Coffee", campaign_title: "Filter coffee tasting", days_left: 2, due_on: "2026-10-30" }),
          item("answer_memo", { memo_id: "m-4", counterparty: "Kovai Organics", campaign_title: "Millet snacks launch", amount_paise: 500_000, currency: "INR", days_left: 9, due_on: "2026-11-06" }),
          item("answer_invitation", { application_id: "a-1", counterparty: "Karur Kitchenware", campaign_title: "Kolu set styling" }),
          item("upi_change_pending", { days_left: 1, due_on: "2026-10-29" }),
        ];
        const brand = [
          item("review_applications", { campaign_id: "c-1", campaign_title: "Diwali sweets reel", count: 3 }),
          item("review_proof", { memo_id: "m-5", counterparty: "priya", campaign_title: "Diwali sweets reel", days_left: 2, due_on: "2026-10-30" }),
          item("pay_creator", { memo_id: "m-6", counterparty: "suresh", campaign_title: "Spice box unboxing", amount_paise: 650_000, currency: "INR", days_left: -2, due_on: "2026-10-26" }),
          item("draft_memo", { application_id: "a-2", campaign_id: "c-2", counterparty: "karthik", campaign_title: "Filter coffee tasting" }),
        ];
        const items = scenario.attention === "empty" ? [] : role === "creator" ? creator : brand;
        return send(res, 200, { role, as_of: "2026-10-28", total: items.length, truncated: false, counts: {}, items });
      }
    }
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
