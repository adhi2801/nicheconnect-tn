import { test } from "node:test";
import assert from "node:assert/strict";
import { dropAllDrafts, dropDraft, readDraft, saveDraft } from "./drafts.ts";

function memoryStore(initial: Record<string, string> = {}) {
  const data = new Map(Object.entries(initial));
  return {
    data,
    get length() { return data.size; },
    key: (i: number) => [...data.keys()][i] ?? null,
    getItem: (k: string) => data.get(k) ?? null,
    setItem: (k: string, v: string) => void data.set(k, v),
    removeItem: (k: string) => void data.delete(k),
  };
}

test("a draft is kept and read back", () => {
  const s = memoryStore();
  saveDraft("apply:c1", { pitch: "hello", quote: "5000" }, s);
  assert.deepEqual(readDraft("apply:c1", s), { pitch: "hello", quote: "5000" });
  dropDraft("apply:c1", s);
  assert.equal(readDraft("apply:c1", s), null);
});

test("a broken or foreign value reads as no draft, never a crash", () => {
  const s = memoryStore({ "colyv-draft:a": "{not json", "colyv-draft:b": "[1,2]", "colyv-draft:c": "7" });
  assert.equal(readDraft("a", s), null);
  assert.equal(readDraft("b", s), null);
  assert.equal(readDraft("c", s), null);
});

test("storage that refuses (a private window) leaves the form working", () => {
  const refusing = { length: 0, key: () => null, getItem: () => { throw new Error("denied"); }, setItem: () => { throw new Error("full"); }, removeItem: () => { throw new Error("denied"); } };
  assert.equal(readDraft("x", refusing), null);
  assert.doesNotThrow(() => saveDraft("x", { a: 1 }, refusing));
  assert.doesNotThrow(() => dropDraft("x", refusing));
  assert.doesNotThrow(() => dropAllDrafts(refusing));
  assert.equal(readDraft("x", null), null);
});

test("sign-out wipes every draft and nothing else", () => {
  const s = memoryStore({ "colyv-draft:apply:c1": "{}", "colyv-draft:onboarding": "{}", "theme": "dark" });
  dropAllDrafts(s);
  assert.deepEqual([...s.data.keys()], ["theme"]);
});
