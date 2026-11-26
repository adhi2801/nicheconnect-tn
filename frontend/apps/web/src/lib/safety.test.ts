import { test } from "node:test";
import assert from "node:assert/strict";
import { answeredWithin, noteTooLong, REPORT_CATEGORIES, reportBody } from "./safety.ts";

test("every category the contract has is offered, once", () => {
  assert.deepEqual([...REPORT_CATEGORIES].sort(), ["abuse", "fake_profile", "impersonation", "intimate_content", "non_payment", "other", "spam"]);
});

test("how soon a report is looked at follows the backend's promise per category", () => {
  assert.equal(answeredWithin("impersonation"), "safety.report.within2h");
  assert.equal(answeredWithin("intimate_content"), "safety.report.within2h");
  assert.equal(answeredWithin("non_payment"), "safety.report.within7d");
  for (const c of ["spam", "fake_profile", "abuse", "other"] as const) assert.equal(answeredWithin(c), "safety.report.within36h", c);
});

test("a report names what it is about; an empty note is sent as none", () => {
  assert.deepEqual(reportBody({ kind: "campaign", id: "c1" }, "spam", "  "), { subject_kind: "campaign", subject_id: "c1", category: "spam", note: null });
  assert.deepEqual(reportBody({ kind: "brand", id: "b1" }, "abuse", "  asked for a fee  "), { subject_kind: "brand", subject_id: "b1", category: "abuse", note: "asked for a fee" });
});

test("a note is at most 1,000 characters, an emoji counting once", () => {
  assert.equal(noteTooLong("a".repeat(1000)), false);
  assert.equal(noteTooLong("a".repeat(1001)), true);
  assert.equal(noteTooLong("🍛".repeat(1000)), false);
});
