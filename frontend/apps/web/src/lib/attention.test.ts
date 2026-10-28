import { test } from "node:test";
import assert from "node:assert/strict";
import en from "../messages/en.json" with { type: "json" };
import { deviceWords, toRow, type AttentionItem, type Kind } from "./attention.ts";

const ALL_KINDS: Kind[] = ["respond_to_dispute", "pay_creator", "review_proof", "revise_memo", "draft_memo", "review_applications", "fix_domain_record", "domain_lapsed", "domain_claim_expired", "confirm_payment", "payment_overdue", "resubmit_work", "deliver_work", "answer_memo", "answer_invitation", "upi_change_pending", "phone_change_pending", "deletion_pending", "new_sign_in"];

const base = (kind: Kind, extra: Partial<AttentionItem> = {}): AttentionItem => ({
  kind, memo_id: "11111111-1111-1111-1111-111111111111", application_id: "22222222-2222-2222-2222-222222222222", campaign_id: "33333333-3333-3333-3333-333333333333",
  proof_id: null, session_id: null, counterparty: "Chennai Bakes", campaign_title: "Diwali sweets reel", amount_paise: 700_000, currency: "INR",
  count: null, days_left: 5, due_on: "2026-11-02", device_label: null, device_platform: null, domain: "chennaibakes.in", signed_in_at: null, signed_in_with: null, ...extra,
} as AttentionItem);

const lookup = (key: string): unknown => key.split(".").reduce<unknown>((n, part) => (n as Record<string, unknown> | undefined)?.[part], en);

test("every kind the API can send has a title and a button in the catalogue", () => {
  for (const kind of ALL_KINDS) {
    const row = toRow(base(kind, { count: 2 }), "creator");
    assert.equal(typeof lookup(row.titleKey), "string", `${kind} title ${row.titleKey}`);
    assert.equal(typeof lookup(row.ctaKey), "string", `${kind} cta ${row.ctaKey}`);
    if (row.contextKey) assert.equal(typeof lookup(row.contextKey), "string", `${kind} context`);
    if (row.due) assert.equal(typeof lookup(row.due.key), "string", `${kind} due ${row.due.key}`);
    assert.match(row.href, /^\/app/, kind);
  }
});

test("applications to review say one or several, and keep the count", () => {
  assert.equal(toRow(base("review_applications", { count: 1 }), "brand").titleKey, "attention.kind.review_applications.title.one");
  const many = toRow(base("review_applications", { count: 3 }), "brand");
  assert.equal(many.titleKey, "attention.kind.review_applications.title.other");
  assert.equal(many.titleVars.count, 3);
});

test("a creator's handle shows as @handle to a brand, and a brand's name stays a name", () => {
  assert.equal(toRow(base("review_proof", { counterparty: "lakshmi" }), "brand").context, "@lakshmi · Diwali sweets reel");
  assert.equal(toRow(base("answer_memo"), "creator").context, "Chennai Bakes · Diwali sweets reel");
});

test("deadlines: late, today, tomorrow, soon and a date; and 'approves itself' for work under review", () => {
  const due = (days: number | null, kind: Kind = "deliver_work") => toRow(base(kind, { days_left: days, due_on: days === null ? null : "2026-11-02" }), "creator").due;
  assert.deepEqual(due(-3), { key: "attention.due.late.other", vars: { days: 3 }, tone: "late" });
  assert.equal(due(-1)?.key, "attention.due.late.one");
  assert.deepEqual(due(0), { key: "attention.due.today", vars: {}, tone: "soon" });
  assert.equal(due(1)?.key, "attention.due.tomorrow");
  assert.deepEqual(due(3), { key: "attention.due.soon", vars: { days: 3 }, tone: "normal" });
  assert.deepEqual(due(9), { key: "attention.due.date", vars: { date: "2 Nov" }, tone: "normal" });
  assert.equal(due(null), null);
  assert.equal(due(2, "review_proof")?.key, "attention.approves.soon");
  assert.equal(due(2, "deletion_pending")?.key, "attention.effective.soon");
});

test("each row has an id that is stable and different for different things", () => {
  const a = toRow(base("answer_memo", { memo_id: "aaaaaaaa-0000-0000-0000-000000000000" }), "creator").id;
  const b = toRow(base("answer_memo", { memo_id: "bbbbbbbb-0000-0000-0000-000000000000" }), "creator").id;
  assert.notEqual(a, b);
  assert.equal(a, toRow(base("answer_memo", { memo_id: "aaaaaaaa-0000-0000-0000-000000000000" }), "creator").id);
});

test("a new sign-in names the device the app gave, or says what it is, or says another device", () => {
  assert.equal(deviceWords(base("new_sign_in", { device_label: "Chrome on Windows" })).label, "Chrome on Windows");
  assert.equal(deviceWords(base("new_sign_in", { device_platform: "ios" })).fallbackKey, "attention.device.ios");
  assert.equal(deviceWords(base("new_sign_in")).fallbackKey, "attention.device.unknown");
});
