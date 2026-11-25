import { test } from "node:test";
import assert from "node:assert/strict";
import { campaignIdsOf, canWithdraw, feedbackLines, groupApplications, reasonWords, statusWords, type Application, type Feedback } from "./applications.ts";

const app = (id: string, status: string, changed: string, campaign = "c1"): Application => ({ id, status, status_changed_at: changed, campaign_id: campaign } as Application);

test("applications group as moving, invited, ended; each newest change first; empty groups left out", () => {
  const groups = groupApplications([
    app("a", "submitted", "2026-11-01T10:00:00Z"),
    app("b", "rejected", "2026-11-03T10:00:00Z"),
    app("c", "shortlisted", "2026-10-30T10:00:00Z"),
    app("d", "submitted", "2026-11-05T10:00:00Z"),
    app("e", "withdrawn", "2026-11-04T10:00:00Z"),
  ]);
  assert.deepEqual(groups.map((g) => g.id), ["moving", "ended"]);
  assert.deepEqual(groups[0].items.map((a) => a.id), ["c", "d", "a"]); // shortlisted leads, then the newest submitted
  assert.deepEqual(groups[1].items.map((a) => a.id), ["b", "e"]);
});

test("a status the app does not know yet is kept, last, never dropped", () => {
  const groups = groupApplications([app("a", "submitted", "2026-11-01T10:00:00Z"), app("z", "paused_by_brand", "2026-11-02T10:00:00Z")]);
  assert.deepEqual(groups.map((g) => g.id), ["moving", "other"]);
  assert.equal(statusWords("paused_by_brand"), "applications.status.other");
  assert.equal(statusWords("shortlisted"), "applications.status.shortlisted");
});

test("no applications, no groups", () => {
  assert.deepEqual(groupApplications([]), []);
});

test("only submitted and shortlisted can be withdrawn", () => {
  for (const s of ["submitted", "shortlisted"]) assert.equal(canWithdraw({ status: s } as Application), true, s);
  for (const s of ["accepted", "rejected", "withdrawn", "invited", "declined"]) assert.equal(canWithdraw({ status: s } as Application), false, s);
});

test("each campaign is fetched once, whatever the number of applications to it", () => {
  assert.deepEqual(campaignIdsOf([app("a", "submitted", "x", "c1"), app("b", "rejected", "x", "c2"), app("c", "rejected", "x", "c1")]), ["c1", "c2"]);
});

test("a reason the app does not know reads as 'another reason'", () => {
  assert.equal(reasonWords("budget_mismatch"), "applications.reason.budget_mismatch");
  assert.equal(reasonWords("brand_paused"), "applications.reason.other");
});

const feedback = (extra: Partial<Feedback>): Feedback => ({ as_of: "2026-11-25", applications: 10, by_status: {}, rejections: 4, rejections_by_reason: {}, most_common_reason: null, quotes_compared: 0, quotes_above_budget: 0, open_campaigns_in_your_niches: 0, open_campaigns_in_your_niches_and_city: 0, has_bio: true, passport_published: false, ...extra } as Feedback);

test("feedback shows only facts that rest on enough to say something", () => {
  assert.deepEqual(feedbackLines(feedback({})), []);
  assert.deepEqual(feedbackLines(feedback({ most_common_reason: "budget_mismatch" })), [{ key: "applications.feedback.commonReason", vars: { count: 4 }, reason: "budget_mismatch" }]);
  assert.deepEqual(feedbackLines(feedback({ quotes_compared: 2, quotes_above_budget: 2 })), []); // two is not enough to say
  assert.equal(feedbackLines(feedback({ quotes_compared: 5, quotes_above_budget: 3 }))[0].key, "applications.feedback.quotesAbove");
  assert.equal(feedbackLines(feedback({ quotes_compared: 5, quotes_above_budget: 0 })).length, 0);
  assert.equal(feedbackLines(feedback({ open_campaigns_in_your_niches: 1 }))[0].key, "applications.feedback.openOne");
  assert.equal(feedbackLines(feedback({ open_campaigns_in_your_niches: 7 }))[0].key, "applications.feedback.open");
});
