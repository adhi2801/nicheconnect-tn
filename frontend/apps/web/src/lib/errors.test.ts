import { test } from "node:test";
import assert from "node:assert/strict";
import { ApiError, apiErrorFrom, commonWordsKey, kindFromStatus, retryDelayMs, shouldRetry } from "./errors.ts";

test("status and code decide the kind", () => {
  assert.equal(kindFromStatus(503), "busy");
  assert.equal(kindFromStatus(500, "service_busy"), "busy");
  assert.equal(kindFromStatus(429), "rate_limited");
  assert.equal(kindFromStatus(401), "unauthorized");
  assert.equal(kindFromStatus(403), "forbidden");
  assert.equal(kindFromStatus(404), "not_found");
  assert.equal(kindFromStatus(409), "conflict");
  assert.equal(kindFromStatus(422), "invalid");
  assert.equal(kindFromStatus(400), "invalid");
  assert.equal(kindFromStatus(451), "withheld");
  assert.equal(kindFromStatus(500), "unknown");
});

test("a 422's field errors are kept, and a body of the wrong shape gives none instead of a crash", () => {
  const response = new Response(null, { status: 422 });
  const error = apiErrorFrom(response, { code: "validation_failed", errors: [{ field: "handle", message: "bad" }, { field: 3 }, null, "x"] });
  assert.deepEqual(error.fields, [{ field: "handle", message: "bad" }]);
  assert.deepEqual(apiErrorFrom(response, { errors: "nope" }).fields, []);
  assert.deepEqual(apiErrorFrom(response, undefined).fields, []);
});

test("a failure with no words of its own gets the common ones, never a status code", () => {
  assert.equal(commonWordsKey(new ApiError("network")), "common.offline");
  assert.equal(commonWordsKey(new ApiError("busy", 503)), "common.busy");
  assert.equal(commonWordsKey(new ApiError("rate_limited", 429)), "common.rateLimited");
  assert.equal(commonWordsKey(new ApiError("unknown", 500)), "common.somethingWrong");
  assert.equal(commonWordsKey(new Error("x")), "common.somethingWrong");
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
