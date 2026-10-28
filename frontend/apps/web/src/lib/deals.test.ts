import { test } from "node:test";
import assert from "node:assert/strict";
import { amountOf, applyFilter, boardStages, closedCounts, groupByStage, moveOf, paymentPill, paymentsByMemo, whoFor, type Memo, type Payment } from "./deals.ts";

const memo = (id: string, extra: Partial<Memo> = {}): Memo => ({ id, stage: "in_progress", waiting_on: "creator", content_due_on: "2026-11-10", updated_at: "2026-10-20T10:00:00Z", fee_amount_paise: 500_000, agreed_amount_paise: null, has_open_dispute: false, ...extra } as Memo);

test("a brand also has a Draft column, a creator never does", () => {
  assert.deepEqual(boardStages("creator"), ["memo_sent", "agreed", "in_progress", "payment", "finished"]);
  assert.equal(boardStages("brand")[0], "draft");
  assert.equal(boardStages("brand").length, 6);
});

test("whose move it is, from the API's waiting_on", () => {
  assert.equal(moveOf(memo("a", { waiting_on: "creator" }), "creator"), "yours");
  assert.equal(moveOf(memo("a", { waiting_on: "brand" }), "creator"), "theirs");
  assert.equal(moveOf(memo("a", { waiting_on: null }), "creator"), "ended");
  assert.equal(moveOf(memo("a", { waiting_on: "brand" }), "brand"), "yours");
});

test("columns hold their own stage, ordered: your move first, then the nearest date, then the newest", () => {
  const memos = [
    memo("late", { content_due_on: "2026-12-01", waiting_on: "brand" }),
    memo("soon", { content_due_on: "2026-11-02", waiting_on: "brand" }),
    memo("mine-far", { content_due_on: "2026-12-20", waiting_on: "creator" }),
    memo("nodate", { content_due_on: null, waiting_on: "brand" }),
    memo("other-stage", { stage: "agreed" }),
  ];
  const col = groupByStage(memos, "creator").find((c) => c.stage === "in_progress")!;
  assert.deepEqual(col.memos.map((m) => m.id), ["mine-far", "soon", "late", "nodate"]);
  assert.equal(groupByStage(memos, "creator").find((c) => c.stage === "agreed")!.memos.length, 1);
});

test("the filter keeps only what needs the person, or only what waits on others", () => {
  const memos = [memo("a", { waiting_on: "creator" }), memo("b", { waiting_on: "brand" }), memo("c", { stage: "finished", waiting_on: null })];
  assert.deepEqual(applyFilter(memos, "creator", "mine").map((m) => m.id), ["a"]);
  assert.deepEqual(applyFilter(memos, "creator", "theirs").map((m) => m.id), ["b"]);
  assert.equal(applyFilter(memos, "creator", "all").length, 3);
});

test("declined and cancelled deals are counted apart, not drawn as stages", () => {
  const memos = [memo("a", { stage: "declined" }), memo("b", { stage: "cancelled" }), memo("c", { stage: "cancelled" }), memo("d")];
  assert.deepEqual(closedCounts(memos), { declined: 1, cancelled: 2 });
  assert.equal(groupByStage(memos, "brand").flatMap((c) => c.memos).length, 1);
});

test("names: the memo's own win, a payment fills the gap, and nothing is invented", () => {
  const payment = { deal_memo_id: "m1", brand_name: "Chennai Bakes", creator_display_name: "Lakshmi Loves", campaign_title: "Diwali sweets reel" } as Payment;
  const by = paymentsByMemo([payment]);
  assert.deepEqual(whoFor(memo("m1"), "creator", by), { title: "Diwali sweets reel", name: "Chennai Bakes" });
  assert.deepEqual(whoFor(memo("m1"), "brand", by), { title: "Diwali sweets reel", name: "Lakshmi Loves" });
  assert.deepEqual(whoFor(memo("m1", { campaign_title: "Own title", counterparty_name: "Own name" }), "creator", by), { title: "Own title", name: "Own name" });
  assert.deepEqual(whoFor(memo("m2"), "creator", by), { title: null, name: null });
});

test("the figure is what was agreed once there is an agreement", () => {
  assert.equal(amountOf(memo("a", { fee_amount_paise: 500_000, agreed_amount_paise: 450_000 })), 450_000);
  assert.equal(amountOf(memo("a", { fee_amount_paise: 500_000, agreed_amount_paise: null })), 500_000);
});

test("each payment state says who did what, in the right colour", () => {
  const day = (iso: string) => iso;
  const pill = (state: Payment["state"], days = 0) => paymentPill({ state, due_on: "2026-11-02", days_overdue: days }, day);
  assert.deepEqual(pill("due"), { tone: "neutral", key: "deals.payments.state.due", vars: { date: "2026-11-02" } });
  assert.equal(pill("late", 1).key, "deals.payments.state.late.one");
  assert.deepEqual(pill("late", 4), { tone: "bad", key: "deals.payments.state.late.other", vars: { days: 4 } });
  assert.equal(pill("unpaid", 12).tone, "bad");
  assert.equal(pill("paid").tone, "warn");
  assert.equal(pill("unconfirmed").key, "deals.payments.state.unconfirmed");
  assert.equal(pill("confirmed").tone, "ok");
});
