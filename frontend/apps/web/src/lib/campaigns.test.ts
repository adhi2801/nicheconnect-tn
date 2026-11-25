import { test } from "node:test";
import assert from "node:assert/strict";
import { activeFilterCount, applicationBody, applyRefusal, checkApplication, discoverQuery, filtersFrom, filtersToSearch, flagsFor, flagWords, payLine, PITCH_MAX, quoteAboveBudget, recordLines, rupeesToPaise, type Reliability } from "./campaigns.ts";

const params = (s: string) => new URLSearchParams(s);

test("pay is a range when the brand gave one, and never a number it did not give", () => {
  assert.deepEqual(payLine({ campaign_type: "paid", budget_min_paise: 500_000, budget_max_paise: 1_500_000 }), { key: "campaigns.pay.range", vars: { min: "₹5,000", max: "₹15,000" } });
  assert.deepEqual(payLine({ campaign_type: "paid", budget_min_paise: 500_000, budget_max_paise: 500_000 }), { key: "campaigns.pay.exact", vars: { amount: "₹5,000" } });
  assert.deepEqual(payLine({ campaign_type: "paid", budget_min_paise: null, budget_max_paise: 800_000 }), { key: "campaigns.pay.upTo", vars: { amount: "₹8,000" } });
  assert.deepEqual(payLine({ campaign_type: "paid", budget_min_paise: 300_000, budget_max_paise: null }), { key: "campaigns.pay.from", vars: { amount: "₹3,000" } });
  assert.equal(payLine({ campaign_type: "barter", budget_min_paise: null, budget_max_paise: null }).key, "campaigns.pay.barter");
  assert.equal(payLine({ campaign_type: "commission", budget_min_paise: null, budget_max_paise: null }).key, "campaigns.pay.commission");
  assert.equal(payLine({ campaign_type: "paid", budget_min_paise: null, budget_max_paise: null }).key, "campaigns.pay.unstated");
  assert.equal(payLine({ campaign_type: "paid", budget_min_paise: 15_000_000, budget_max_paise: 20_000_000 }).vars.max, "₹2,00,000"); // Indian grouping
});

test("filters come from the address, and anything unknown is dropped rather than sent", () => {
  assert.deepEqual(filtersFrom(params("city=Madurai&niche=food&type=paid&min=5000")), { city: "Madurai", niche: "food", type: "paid", minRupees: 5000 });
  assert.deepEqual(filtersFrom(params("niche=gaming&type=free&min=-4&city=M")), {});
  assert.deepEqual(filtersFrom(params("min=12.5")), {});
  assert.deepEqual(filtersFrom(params("min=100000000000")), {}); // above the backend's ceiling
});

test("filters go back to the address in a fixed order, and the query sends money in paise", () => {
  const f = { niche: "food" as const, city: "Salem", minRupees: 2000 };
  assert.equal(filtersToSearch(f), "?city=Salem&niche=food&min=2000");
  assert.equal(filtersToSearch({}), "");
  assert.deepEqual(filtersFrom(params(filtersToSearch(f).slice(1))), f);
  assert.deepEqual(discoverQuery(f, "c1"), { city: "Salem", niche: "food", campaign_type: undefined, min_budget_paise: 200_000, limit: 20, cursor: "c1" });
  assert.equal(activeFilterCount(f), 3);
});

test("a quote typed in rupees becomes whole paise", () => {
  assert.equal(rupeesToPaise(""), null);
  assert.equal(rupeesToPaise("  "), null);
  assert.equal(rupeesToPaise("5000"), 500_000);
  assert.equal(rupeesToPaise("₹5,000"), 500_000);
  assert.equal(rupeesToPaise("1,50,000"), 15_000_000);
  assert.equal(rupeesToPaise("99.5"), 9_950);
  assert.equal(rupeesToPaise("99.05"), 9_905);
  assert.ok(Number.isNaN(rupeesToPaise("5k")));
  assert.ok(Number.isNaN(rupeesToPaise("1.234")));
  assert.ok(Number.isNaN(rupeesToPaise("-50")));
});

test("a pitch is 20 to 1,000 characters once trimmed; a quote is optional but must be a real amount", () => {
  assert.equal(checkApplication("too short", "").pitch, "apply.errors.pitchShort");
  assert.equal(checkApplication(`   ${"a".repeat(19)}   `, "").pitch, "apply.errors.pitchShort");
  assert.equal(checkApplication("a".repeat(20), "").pitch, undefined);
  assert.equal(checkApplication("a".repeat(PITCH_MAX + 1), "").pitch, "apply.errors.pitchLong");
  assert.deepEqual(checkApplication("a".repeat(40), ""), {});
  assert.equal(checkApplication("a".repeat(40), "0").quote, "apply.errors.quoteInvalid");
  assert.equal(checkApplication("a".repeat(40), "abc").quote, "apply.errors.quoteInvalid");
  assert.equal(checkApplication("a".repeat(40), "100000001").quote, "apply.errors.quoteInvalid"); // over ₹10 crore
});

test("the body trims the pitch and sends no quote as null", () => {
  assert.deepEqual(applicationBody("  I make Madurai food reels every week.  ", ""), { pitch: "I make Madurai food reels every week.", quoted_amount_paise: null });
  assert.deepEqual(applicationBody("x".repeat(30), "₹6,000"), { pitch: "x".repeat(30), quoted_amount_paise: 600_000 });
});

test("a quote above the campaign's maximum is noted, at or below it is not, and no maximum means no note", () => {
  assert.equal(quoteAboveBudget("6000", 500_000), true);
  assert.equal(quoteAboveBudget("5000", 500_000), false);
  assert.equal(quoteAboveBudget("", 500_000), false);
  assert.equal(quoteAboveBudget("6000", null), false);
  assert.equal(quoteAboveBudget("abc", 500_000), false);
});

test("each refusal from the backend has words a creator can act on", () => {
  assert.equal(applyRefusal("already_applied", []).key, "apply.refused.alreadyApplied");
  assert.equal(applyRefusal("applications_closed", []).key, "apply.refused.closed");
  assert.equal(applyRefusal("campaign_not_open", []).key, "apply.refused.closed");
  assert.equal(applyRefusal("own_content_withheld", []).key, "apply.refused.withheld");
  assert.deepEqual(applyRefusal("validation_failed", [{ field: "pitch", message: "x" }]), { key: "apply.errors.pitchShort", field: "pitch" });
  assert.deepEqual(applyRefusal("validation_failed", [{ field: "quoted_amount_paise", message: "x" }]), { key: "apply.errors.quoteInvalid", field: "quote" });
  assert.equal(applyRefusal("something_new", []).key, "common.somethingWrong");
});

const record = (extra: Partial<Reliability>): Reliability => ({ brand_id: "b", status: "has_payment_history", deals_completed: 9, deals_paid: 8, deals_unpaid: 1, currently_overdue: 0, paid_on_time_share: 0.875, median_days_to_pay: 3.4, distinct_creators: 6, ...extra } as Reliability);

test("a brand's record is facts with what they rest on; a new brand is 'no history yet', never a zero", () => {
  assert.deepEqual(recordLines(record({ status: "new_brand_no_history_yet", deals_paid: 0 })), [{ key: "campaign.record.noHistory", vars: {} }]);
  const lines = recordLines(record({}));
  assert.deepEqual(lines.map((l) => l.key), ["campaign.record.paid", "campaign.record.onTime", "campaign.record.medianDays"]);
  assert.deepEqual(lines[0].vars, { paid: 8, settled: 9, creators: 6 });
  assert.equal(lines[1].vars.percent, 88);
  assert.equal(recordLines(record({ distinct_creators: 1 }))[0].key, "campaign.record.paidOne");
  assert.deepEqual(recordLines(record({ paid_on_time_share: null, median_days_to_pay: null })).map((l) => l.key), ["campaign.record.paid"]);
});

test("money owed right now always shows, even for a brand too new to have a history", () => {
  const owing = recordLines(record({ status: "new_brand_no_history_yet", deals_completed: 1, currently_overdue: 2 }));
  assert.deepEqual(owing.map((l) => l.key), ["campaign.record.noHistory", "campaign.record.overdue"]);
  assert.equal(owing[1].tone, "bad");
  assert.equal(recordLines(record({ currently_overdue: 1 })).at(-1)?.key, "campaign.record.overdueOne");
  assert.ok(!recordLines(record({ currently_overdue: 0 })).some((l) => l.tone === "bad"));
});

test("warnings belong to their own field, once each, and an unknown kind still shows", () => {
  const flags = [{ field: "description", flag: "asks_for_money" as const }, { field: "description", flag: "asks_for_money" as const }, { field: "title", flag: "email" as const }];
  assert.deepEqual(flagsFor(flags, "description"), ["asks_for_money"]);
  assert.deepEqual(flagsFor(flags, "deliverables"), []);
  assert.deepEqual(flagsFor(null, "title"), []);
  assert.equal(flagWords("asks_for_money"), "flags.asksForMoney");
  assert.equal(flagWords("new_kind_from_backend"), "flags.other");
});
