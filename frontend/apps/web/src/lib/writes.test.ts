import { test } from "node:test";
import assert from "node:assert/strict";
import { ApiError } from "./errors.ts";
import { IntentKeys, newIdempotencyKey, sendWrite } from "./writes.ts";

const ok = <T>(data: T) => async () => ({ data, response: new Response(null, { status: 201 }) });
const fail = (status: number, code: string, headers: Record<string, string> = {}) => ({ error: { code }, response: new Response(null, { status, headers }) });

test("the same body keeps its key, a changed body gets a new one, and a finished intent starts over", () => {
  let n = 0;
  const keys = new IntentKeys(() => `k${++n}`);
  assert.equal(keys.keyFor({ pitch: "a" }), "k1");
  assert.equal(keys.keyFor({ pitch: "a" }), "k1");
  assert.equal(keys.keyFor({ pitch: "b" }), "k2");
  assert.equal(keys.keyFor({ pitch: "a" }), "k3");
  keys.done();
  assert.equal(keys.keyFor({ pitch: "a" }), "k4");
});

test("a real key is long and different every time", () => {
  const a = newIdempotencyKey();
  assert.ok(a.length >= 32);
  assert.notEqual(a, newIdempotencyKey());
});

test("success returns the data at once", async () => {
  assert.deepEqual(await sendWrite(ok({ id: "x" })), { id: "x" });
});

test("a busy backend is retried after its Retry-After plus jitter, at most three times", async () => {
  const waits: number[] = [];
  let calls = 0;
  const attempt = async () => (++calls <= 3 ? fail(503, "service_busy", { "Retry-After": "2" }) : { data: "done", response: new Response(null, { status: 201 }) });
  assert.equal(await sendWrite(attempt, { sleep: async (ms) => void waits.push(ms), random: () => 0.5 }), "done");
  assert.equal(calls, 4);
  assert.deepEqual(waits, [2250, 2250, 2250]);
});

test("busy a fourth time gives up with a busy error, so the person decides", async () => {
  let calls = 0;
  const attempt = async () => { calls++; return fail(503, "service_busy"); };
  await assert.rejects(sendWrite(attempt, { sleep: async () => {} }), (e: unknown) => e instanceof ApiError && e.kind === "busy");
  assert.equal(calls, 4);
});

test("a 429 and a 409 are never retried", async () => {
  for (const [status, code, kind] of [[429, "rate_limited", "rate_limited"], [409, "already_applied", "conflict"]] as const) {
    let calls = 0;
    const attempt = async () => { calls++; return fail(status, code, { "Retry-After": "30" }); };
    await assert.rejects(sendWrite(attempt, { sleep: async () => assert.fail("must not wait") }), (e: unknown) => e instanceof ApiError && e.kind === kind && e.code === code);
    assert.equal(calls, 1);
  }
});

test("a dropped connection is a network error, not a crash", async () => {
  await assert.rejects(sendWrite(async () => { throw new TypeError("Failed to fetch"); }), (e: unknown) => e instanceof ApiError && e.kind === "network");
});
