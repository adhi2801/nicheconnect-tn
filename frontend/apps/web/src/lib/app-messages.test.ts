import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

// lib/app-messages.ts merges the shared and the signed-in catalogues one level deep. A top-level key in both would make the signed-in
// one replace the shared subtree, and every shared key under it would show as its raw key, while the types still compile.
const read = (name: string): Record<string, unknown> => JSON.parse(readFileSync(new URL(`../messages/${name}`, import.meta.url), "utf8"));

test("the shared and the signed-in catalogues share no top-level key", () => {
  const base = Object.keys(read("en.json"));
  const app = Object.keys(read("en-app.json"));
  assert.deepEqual(base.filter((k) => app.includes(k)), []);
  assert.ok(base.length > 0 && app.length > 0);
});
