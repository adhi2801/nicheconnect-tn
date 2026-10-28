import { test } from "node:test";
import assert from "node:assert/strict";
import { ApiError, apiErrorFrom, kindFromStatus, retryDelayMs, shouldRetry } from "./errors.ts";

test("status and code decide the kind", () => {
  assert.equal(kindFromStatus(503), "busy");
  assert.equal(kindFromStatus(500, "service_busy"), "busy");
  assert.equal(kindFromStatus(429), "rate_limited");
  assert.equal(kindFromStatus(401), "unauthorized");
  assert.equal(kindFromStatus(403), "forbidden");
  assert.equal(kindFromStatus(404), "not_found");
  assert.equal(kindFromStatus(500), "unknown");
});

test("the problem body's reference and the Retry-After wait are kept", () => {
  const response = new Response(null, { status: 503, headers: { "Retry-After": "7" } });
  const error = apiErrorFrom(response, { code: "service_busy", request_id: "01ABC" });
  assert.equal(error.kind, "busy");
  assert.equal(error.requestId, "01ABC");
  assert.equal(error.retryAfter, 7);
});

test("only a busy backend is retried, and at most three times", () => {
  const busy = new ApiError("busy", 503);
  assert.equal(shouldRetry(0, busy), true);
  assert.equal(shouldRetry(2, busy), true);
  assert.equal(shouldRetry(3, busy), false);
  assert.equal(shouldRetry(0, new ApiError("rate_limited", 429)), false);
  assert.equal(shouldRetry(0, new ApiError("network")), false);
  assert.equal(shouldRetry(0, new Error("other")), false);
});

test("the wait is what the backend asked, plus a little jitter", () => {
  assert.equal(retryDelayMs(new ApiError("busy", 503, undefined, undefined, 4), () => 0), 4000);
  assert.equal(retryDelayMs(new ApiError("busy", 503), () => 0), 2000);
  assert.equal(retryDelayMs(new ApiError("busy", 503, undefined, undefined, 4), () => 0.5), 4250);
});
