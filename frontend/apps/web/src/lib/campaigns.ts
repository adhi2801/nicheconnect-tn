import type { components } from "@colyv/api";
import type { FieldError } from "./errors.ts";
import { formatPaise } from "./format.ts";
import type { MessageKey } from "./app-messages.ts";
import { NICHES, type Niche } from "./onboarding.ts";

// Discover, a campaign and applying to it (frontend/design/screen-plan.md C2, C3, C4). Pure rules, no React, so the apps can reuse them.

export type Campaign = components["schemas"]["CampaignRead"];
export type CampaignType = Campaign["campaign_type"];
export type Reliability = components["schemas"]["BrandReliabilityRead"];
export type FieldFlag = components["schemas"]["FieldFlag"];

export const CAMPAIGN_TYPES: readonly CampaignType[] = ["paid", "barter", "commission", "local_business"];
export const PITCH_MIN = 20;
export const PITCH_MAX = 1000;
/** The backend's ceiling on a quote: ₹10 crore, in paise. */
export const QUOTE_MAX_PAISE = 10_000_000_000;

// ---- Pay, in words ----

export type PayLine = { key: MessageKey; vars: Record<string, string> };

/** What a campaign pays, as one line. A range when it has one; never a number the brand did not give. */
export function payLine(c: Pick<Campaign, "campaign_type" | "budget_min_paise" | "budget_max_paise">): PayLine {
  const min = c.budget_min_paise ?? null;
  const max = c.budget_max_paise ?? null;
  if (min !== null && max !== null && min !== max) return { key: "campaigns.pay.range", vars: { min: formatPaise(min), max: formatPaise(max) } };
  if (max !== null) return { key: min === max ? "campaigns.pay.exact" : "campaigns.pay.upTo", vars: { amount: formatPaise(max) } };
  if (min !== null) return { key: "campaigns.pay.from", vars: { amount: formatPaise(min) } };
  if (c.campaign_type === "barter") return { key: "campaigns.pay.barter", vars: {} };
  if (c.campaign_type === "commission") return { key: "campaigns.pay.commission", vars: {} };
  return { key: "campaigns.pay.unstated", vars: {} };
}

// ---- Discover filters, kept in the URL so a filtered list can be shared and the back button works ----

export type Filters = { city?: string; niche?: Niche; type?: CampaignType; minRupees?: number };

const isNiche = (v: string | null): v is Niche => v !== null && (NICHES as readonly string[]).includes(v);
const isType = (v: string | null): v is CampaignType => v !== null && (CAMPAIGN_TYPES as readonly string[]).includes(v);

/** Reads filters from the address. A value we do not know is dropped, never sent to the backend. */
export function filtersFrom(params: { get(name: string): string | null }): Filters {
  const f: Filters = {};
  const city = params.get("city")?.trim();
  if (city && city.length >= 2 && city.length <= 60) f.city = city;
  const niche = params.get("niche");
  if (isNiche(niche)) f.niche = niche;
  const type = params.get("type");
  if (isType(type)) f.type = type;
  const min = Number(params.get("min"));
  if (Number.isInteger(min) && min > 0 && min * 100 <= QUOTE_MAX_PAISE) f.minRupees = min;
  return f;
}

/** The address for these filters: only what is set, in a fixed order. */
export function filtersToSearch(f: Filters): string {
  const p = new URLSearchParams();
  if (f.city) p.set("city", f.city);
  if (f.niche) p.set("niche", f.niche);
  if (f.type) p.set("type", f.type);
  if (f.minRupees) p.set("min", String(f.minRupees));
  const s = p.toString();
  return s ? `?${s}` : "";
}

/** The query for GET /campaigns/discover. Money goes to the API in paise. */
export function discoverQuery(f: Filters, cursor?: string) {
  return { city: f.city, niche: f.niche, campaign_type: f.type, min_budget_paise: f.minRupees ? f.minRupees * 100 : undefined, limit: 20, cursor };
}

export const activeFilterCount = (f: Filters): number => [f.city, f.niche, f.type, f.minRupees].filter((v) => v !== undefined).length;

// ---- Applying ----

/** A quote typed in rupees ("5,000", "₹5000", "5000.50") as whole paise. null when blank; NaN when it is not an amount. */
export function rupeesToPaise(typed: string): number | null {
  const clean = typed.replace(/[₹,\s]/g, "");
  if (clean === "") return null;
  if (!/^\d+(\.\d{1,2})?$/.test(clean)) return Number.NaN;
  const [whole, fraction = ""] = clean.split(".");
  return Number(whole) * 100 + Number(fraction.padEnd(2, "0"));
}

export type ApplyProblems = { pitch?: MessageKey; quote?: MessageKey };

/** A pitch's length as the backend counts it: characters (code points), not UTF-16 units, so an emoji counts once. */
export const pitchLength = (pitch: string): number => [...pitch.trim()].length;

export function checkApplication(pitch: string, quoteTyped: string): ApplyProblems {
  const problems: ApplyProblems = {};
  const length = pitchLength(pitch);
  if (length < PITCH_MIN) problems.pitch = "apply.errors.pitchShort";
  else if (length > PITCH_MAX) problems.pitch = "apply.errors.pitchLong";
  const quote = rupeesToPaise(quoteTyped);
  if (quote !== null && (Number.isNaN(quote) || quote <= 0 || quote > QUOTE_MAX_PAISE)) problems.quote = "apply.errors.quoteInvalid";
  return problems;
}

/** The body for POST /campaigns/{id}/applications. No quote is sent as null: barter and commission campaigns need none. */
export function applicationBody(pitch: string, quoteTyped: string): components["schemas"]["ApplicationCreate"] {
  const quote = rupeesToPaise(quoteTyped);
  return { pitch: pitch.trim(), quoted_amount_paise: quote === null || Number.isNaN(quote) ? null : quote };
}

/** A quote above the campaign's own maximum earns a gentle note, never a block (screen-plan C4). */
export function quoteAboveBudget(quoteTyped: string, budgetMaxPaise: number | null | undefined): boolean {
  const quote = rupeesToPaise(quoteTyped);
  return quote !== null && !Number.isNaN(quote) && budgetMaxPaise != null && quote > budgetMaxPaise;
}

/** Why the backend refused an application, in words a creator can act on. */
export function applyRefusal(code: string | undefined, fields: FieldError[]): { key: MessageKey; field?: "pitch" | "quote" } {
  switch (code) {
    case "already_applied": return { key: "apply.refused.alreadyApplied" };
    case "applications_closed":
    case "campaign_not_open": return { key: "apply.refused.closed" };
    case "creator_profile_required": return { key: "apply.refused.noProfile" };
    case "own_content_withheld": return { key: "apply.refused.withheld" };
    case "content_withheld": return { key: "apply.refused.campaignWithheld" };
    case "campaign_not_found": return { key: "apply.refused.gone" };
    case "invitation_pending": return { key: "apply.refused.invited" };
  }
  if (fields.some((f) => f.field === "pitch")) return { key: "apply.errors.pitchCheck", field: "pitch" };
  if (fields.some((f) => f.field === "quoted_amount_paise")) return { key: "apply.errors.quoteInvalid", field: "quote" };
  return { key: "common.somethingWrong" };
}

// ---- The brand, in facts ----

export type RecordLine = { key: MessageKey; vars: Record<string, string | number>; tone?: "bad" };

/**
 * A brand's payment record as facts, each with what it rests on (D-027): never a score, never a zero for "nothing yet".
 * Below three settled deals the backend withholds the figures and says "no history yet". Money owed right now is shown whatever the
 * history, so a brand that owes creators can never read as simply new (backend payment_status/reliability.py, rule 2).
 */
export function recordLines(r: Reliability): RecordLine[] {
  const lines: RecordLine[] = [];
  if (r.status === "new_brand_no_history_yet") {
    lines.push({ key: "campaign.record.noHistory", vars: {} });
  } else {
    lines.push({ key: r.distinct_creators === 1 ? "campaign.record.paidOne" : "campaign.record.paid", vars: { paid: r.deals_paid, settled: r.deals_completed, creators: r.distinct_creators } });
    if (r.paid_on_time_share !== null && r.paid_on_time_share !== undefined) lines.push({ key: "campaign.record.onTime", vars: { percent: Math.round(r.paid_on_time_share * 100), settled: r.deals_completed } });
    if (r.median_days_to_pay !== null && r.median_days_to_pay !== undefined) lines.push({ key: "campaign.record.medianDays", vars: { days: Math.round(r.median_days_to_pay) } });
  }
  if (r.currently_overdue > 0) lines.push({ key: r.currently_overdue === 1 ? "campaign.record.overdueOne" : "campaign.record.overdue", vars: { count: r.currently_overdue }, tone: "bad" });
  return lines;
}

/** A domain registered this many days ago or fewer is called recent: what scams use (trust-and-safety.md section 5). */
export const RECENT_DOMAIN_DAYS = 90;

export type DomainFacts = { domain: string; verifiedSince: string; registeredOn: string | null; recent: boolean };

/**
 * A verified domain as what was checked (legal.md section 3, item 74, D-106): the domain, since when it is verified, and when the
 * registry says it was registered, with "recent" said plainly. Never "verified brand". `today` and the dates are Tamil Nadu dates.
 */
export function domainFacts(d: { domain: string; verified_since: string; registered_on?: string | null }, today: string, indiaDay: (ts: string) => string): DomainFacts {
  const registeredOn = d.registered_on ?? null;
  const days = registeredOn ? (Date.UTC(...ymd(today)) - Date.UTC(...ymd(registeredOn))) / 86_400_000 : null;
  return { domain: d.domain, verifiedSince: indiaDay(d.verified_since), registeredOn, recent: days !== null && days <= RECENT_DOMAIN_DAYS };
}
const ymd = (iso: string): [number, number, number] => { const [y, m, d] = iso.split("-").map(Number); return [y, m - 1, d]; };

/** The warnings for one field, to show beside it (trust-and-safety.md section 5). Unknown flags still show, with general words. */
export function flagsFor(flags: readonly FieldFlag[] | null | undefined, field: string): FieldFlag["flag"][] {
  return [...new Set((flags ?? []).filter((f) => f.field === field).map((f) => f.flag))];
}

export const FLAG_WORDS: Record<string, MessageKey> = {
  asks_for_money: "flags.asksForMoney",
  phone_number: "flags.contact",
  email: "flags.contact",
  upi_id: "flags.upi",
  messaging_link: "flags.contact",
};
export const flagWords = (flag: string): MessageKey => FLAG_WORDS[flag] ?? "flags.other";
