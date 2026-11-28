import { strict as assert } from "node:assert";
import { test } from "node:test";
import { addNumbers, applicantsOf, comingUp, daysUntil, formatCount, headlineOf, ongoing, openDeals, percent, performanceOf, postsOf, progressOf, share, type Numbers, type Report } from "./dashboard.ts";
import type { Memo } from "./deals.ts";

const none: Numbers = { views: null, reach: null, impressions: null, likes: null, comments: null, saves: null, shares: null };
const counts = { submitted: 0, shortlisted: 0, accepted: 0, rejected: 0, withdrawn: 0, invited: 0, declined: 0 };
const deal = (stage: string, results: Partial<{ numbers: Partial<Numbers>; readings: number; wrong: number; abbreviated: boolean }> = {}) => ({
  deal_memo_id: `d-${Math.random()}`, stage, creator: { display_name: "Meena", handle: "meena" }, content_url: null,
  results: { numbers: { ...none, ...results.numbers }, readings: results.readings ?? 0, readings_marked_wrong: results.wrong ?? 0, includes_abbreviated: results.abbreviated ?? false, source: "screenshot" },
});
const report = (o: { applications?: Partial<typeof counts>; deals?: number; agreed?: number; finished?: number; list?: ReturnType<typeof deal>[] }): Report =>
  ({ totals: { applications: { ...counts, ...o.applications }, deals: o.deals ?? 0, deals_agreed: o.agreed ?? 0, deals_finished: o.finished ?? 0 }, deals: o.list ?? [] }) as unknown as Report;

test("a share with nothing to divide is null, never zero percent", () => {
  assert.equal(share(0, 0), null);
  assert.equal(percent(share(0, 0)), null);
  assert.equal(percent(share(0, 4)), 0);
  assert.equal(percent(share(1, 3)), 33);
});

test("the four steps add up across campaigns, from what the API counted", () => {
  const a = report({ applications: { submitted: 2, shortlisted: 1, accepted: 1, rejected: 1, withdrawn: 9 }, deals: 3, agreed: 2, finished: 1, list: [deal("payment"), deal("finished"), deal("in_progress")] });
  const b = report({ applications: { submitted: 1 }, deals: 0 });
  const p = progressOf([a, b]);
  assert.deepEqual(p.applications, { done: 3, of: 6 }, "withdrawn applications are not counted; shortlisted, accepted and rejected are looked at");
  assert.deepEqual(p.memos, { done: 2, of: 3 });
  assert.deepEqual(p.work, { done: 2, of: 2 }, "approved work is a deal at payment or finished");
  assert.deepEqual(p.paid, { done: 1, of: 2 });
  assert.equal(applicantsOf([a, b]), 6);
  assert.deepEqual(progressOf([]), { applications: null, memos: null, work: null, paid: null });
});

test("only open and closed campaigns are ongoing, newest first, at most six", () => {
  const c = (id: string, status: string, updated_at: string) => ({ id, status, updated_at });
  const list = [c("a", "draft", "2026-11-01"), c("b", "open", "2026-11-02"), c("c", "cancelled", "2026-11-09"), c("d", "closed", "2026-11-05"), ...["e", "f", "g", "h", "i"].map((id, i) => c(id, "open", `2026-10-0${i + 1}`))];
  assert.deepEqual(ongoing(list).map((x) => x.id), ["d", "b", "i", "h", "g", "f"]);
});

test("a number nobody reported stays null; one some reported is the sum of those", () => {
  const sum = addNumbers([{ ...none, views: 100, likes: 5 }, { ...none, views: 50 }, { ...none, reach: 70 }]);
  assert.equal(sum.views, 150);
  assert.equal(sum.likes, 5);
  assert.equal(sum.reach, 70);
  assert.equal(sum.saves, null, "no screenshot showed saves: null, not 0");
  assert.deepEqual(addNumbers([]), none);
});

test("a deal whose screenshots said nothing is not a post of zeros", () => {
  const r = report({ list: [deal("finished", { numbers: { views: 900 }, readings: 2, abbreviated: true, wrong: 1 }), deal("finished"), deal("in_progress")] });
  const posts = postsOf(r);
  assert.equal(posts.length, 1);
  assert.equal(posts[0]?.approximate, true);
  assert.equal(posts[0]?.markedWrong, 1);
  const total = performanceOf([r, report({ list: [deal("finished", { numbers: { views: 100, likes: 4 }, readings: 1 })] })]);
  assert.equal(total.posts, 2);
  assert.equal(total.readings, 3);
  assert.equal(total.numbers.views, 1000);
  assert.equal(total.approximate, true);
  assert.deepEqual(performanceOf([]).numbers, none);
});

test("a post's headline is its views, or its reach when no views were shown, or nothing", () => {
  assert.deepEqual(headlineOf({ ...none, views: 10, reach: 99 }), { key: "views", value: 10 });
  assert.deepEqual(headlineOf({ ...none, reach: 99 }), { key: "reach", value: 99 });
  assert.equal(headlineOf(none), null);
  assert.deepEqual(headlineOf({ ...none, views: 0 }), { key: "views", value: 0 }, "a reported zero is a zero");
});

test("counts read the Indian way", () => {
  assert.equal(formatCount(950), "950");
  assert.equal(formatCount(48_200), "48.2K");
  assert.equal(formatCount(1_250_000), "12.5L");
});

test("days run in Tamil Nadu dates, across month and year ends", () => {
  assert.equal(daysUntil("2026-12-02", "2026-11-28"), 4);
  assert.equal(daysUntil("2027-01-01", "2026-12-31"), 1);
  assert.equal(daysUntil("2026-11-27", "2026-11-28"), -1);
  assert.equal(daysUntil("2026-11-28", "2026-11-28"), 0);
});

const memo = (id: string, stage: string, over: Partial<Memo> = {}): Memo => ({ id, stage, waiting_on: "creator", work_due_on: null, content_due_on: null, updated_at: "2026-11-01", ...over }) as unknown as Memo;

test("coming up: deals whose work is still to come, nearest first, yours marked; finished, paying and drafts left out", () => {
  const memos = [
    memo("far", "in_progress", { work_due_on: "2026-12-20" }),
    memo("near", "in_progress", { content_due_on: "2026-11-30", waiting_on: "brand" }),
    memo("late", "agreed", { work_due_on: "2026-11-25" }),
    memo("done", "finished", { work_due_on: "2026-11-29" }),
    memo("paying", "payment", { work_due_on: "2026-11-01" }),
    memo("draft", "draft", { work_due_on: "2026-11-29" }),
    memo("undated", "memo_sent"),
  ];
  const next = comingUp(memos, "creator", "2026-11-28");
  assert.deepEqual(next.map((x) => x.memo.id), ["late", "near", "far"]);
  assert.deepEqual(next.map((x) => x.days), [-3, 2, 22]);
  assert.deepEqual(next.map((x) => x.yours), [true, false, true]);
  assert.equal(comingUp(memos, "creator", "2026-11-28", 1).length, 1);
  assert.equal(openDeals(memos), 5, "a deal at payment is still open, but its work date no longer counts as coming up");
});
