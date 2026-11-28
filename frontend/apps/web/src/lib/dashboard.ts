import type { components } from "@colyv/api";
import type { Memo } from "./deals.ts";
import { moveOf } from "./deals.ts";
import type { Role } from "./session.ts";

// The facts behind the two Today dashboards (frontend/design/dashboard-plan.md). The API says every status and every number; this file
// only adds them up and sorts them, and never invents one: a share with nothing to divide is `null` ("not enough to say"), a number the
// screenshots did not show is `null`, and neither is ever shown as zero.
export type Report = components["schemas"]["CampaignReportRead"];
export type ReportDeal = components["schemas"]["ReportDealRead"];
export type Numbers = components["schemas"]["ReportNumbersRead"];
type CampaignStatus = { id: string; status: string; updated_at: string };

/** How many campaigns get a card (and a report read): the newest ongoing ones. Pilot scale; the rest are a click away. */
export const ONGOING_LIMIT = 6;

/** A campaign worth a card: taking applications, or closed with deals still going. Drafts and cancelled ones are not ongoing. */
export function ongoing<T extends CampaignStatus>(campaigns: T[]): T[] {
  return campaigns
    .filter((c) => c.status === "open" || c.status === "closed")
    .sort((a, b) => (a.updated_at < b.updated_at ? 1 : a.updated_at > b.updated_at ? -1 : 0))
    .slice(0, ONGOING_LIMIT);
}

// ---- Progress: what share of the way each step has come (brand) ----

export type Share = { done: number; of: number } | null;
export const share = (done: number, of: number): Share => (of > 0 ? { done, of } : null);
/** Whole percent, or null when there is nothing to divide. */
export const percent = (s: Share): number | null => (s ? Math.round((s.done / s.of) * 100) : null);

export type Progress = { applications: Share; memos: Share; work: Share; paid: Share };

const sum = (reports: Report[], pick: (r: Report) => number): number => reports.reduce((n, r) => n + pick(r), 0);
const dealsAt = (r: Report, stages: string[]): number => r.deals.filter((d) => stages.includes(d.stage)).length;

/** The four steps of a collaboration across the campaigns given: applications looked at, memos agreed, work approved, paid and confirmed. */
export function progressOf(reports: Report[]): Progress {
  const decided = (r: Report) => r.totals.applications.shortlisted + r.totals.applications.accepted + r.totals.applications.rejected;
  const total = (r: Report) => r.totals.applications.submitted + decided(r);
  const agreed = sum(reports, (r) => r.totals.deals_agreed);
  return {
    applications: share(sum(reports, decided), sum(reports, total)),
    memos: share(agreed, sum(reports, (r) => r.totals.deals)),
    work: share(sum(reports, (r) => dealsAt(r, ["payment", "finished"])), agreed),
    paid: share(sum(reports, (r) => r.totals.deals_finished), agreed),
  };
}

/** Applications received across the campaigns, for the figure at the top: everyone who applied and is still in the running or answered. */
export const applicantsOf = (reports: Report[]): number =>
  sum(reports, (r) => r.totals.applications.submitted + r.totals.applications.shortlisted + r.totals.applications.accepted + r.totals.applications.rejected);

// ---- Performance: what the creators' screenshots said (D-070) ----

const KEYS = ["views", "reach", "impressions", "likes", "comments", "saves", "shares"] as const;
export type Key = (typeof KEYS)[number];
export const NUMBER_KEYS: readonly Key[] = KEYS;

export type Post = {
  dealId: string;
  creator: string;
  handle: string;
  numbers: Numbers;
  readings: number;
  markedWrong: number;
  /** A figure was shown abbreviated on screen (12.5K), so it is not exact. */
  approximate: boolean;
  link: string | null;
};

/** The approved posts that have at least one reading. A deal whose screenshots said nothing has no post here, not a post of zeros. */
export function postsOf(report: Report): Post[] {
  return report.deals
    .filter((d) => d.results.readings > 0)
    .map((d) => ({
      dealId: d.deal_memo_id,
      creator: d.creator.display_name,
      handle: d.creator.handle,
      numbers: d.results.numbers,
      readings: d.results.readings,
      markedWrong: d.results.readings_marked_wrong,
      approximate: d.results.includes_abbreviated,
      link: d.content_url ?? null,
    }));
}

/** Adds numbers up. A number nobody reported stays `null`; one reported by some is the sum of those. */
export function addNumbers(all: Numbers[]): Numbers {
  const out = {} as Record<Key, number | null>;
  for (const key of KEYS) {
    const present = all.map((n) => n[key]).filter((v): v is number => typeof v === "number");
    out[key] = present.length === 0 ? null : present.reduce((a, b) => a + b, 0);
  }
  return out;
}

export type Performance = { numbers: Numbers; readings: number; posts: number; approximate: boolean };

/** Every campaign's posts together. */
export function performanceOf(reports: Report[]): Performance {
  const posts = reports.flatMap(postsOf);
  return {
    numbers: addNumbers(posts.map((p) => p.numbers)),
    readings: posts.reduce((n, p) => n + p.readings, 0),
    posts: posts.length,
    approximate: posts.some((p) => p.approximate),
  };
}

/** The headline figure of a post: views, or reach when the screenshot showed no views. */
export const headlineOf = (n: Numbers): { key: "views" | "reach"; value: number } | null =>
  typeof n.views === "number" ? { key: "views", value: n.views } : typeof n.reach === "number" ? { key: "reach", value: n.reach } : null;

/** 48200 as "48.2K", 1250000 as "12.5L" (Indian grouping). Under a thousand, as it is. */
export const formatCount = (n: number): string => new Intl.NumberFormat("en-IN", { notation: "compact", maximumFractionDigits: 1 }).format(n);

// ---- Dates ----

const dayNumber = (iso: string): number => {
  const [y = 0, m = 1, d = 1] = iso.slice(0, 10).split("-").map(Number);
  return Date.UTC(y, m - 1, d) / 86_400_000;
};
/** Whole days from `today` to `iso` (both Tamil Nadu dates, YYYY-MM-DD); negative when it has passed. */
export const daysUntil = (iso: string, today: string): number => Math.round(dayNumber(iso) - dayNumber(today));

const OVER: string[] = ["finished", "declined", "cancelled"];
/** A deal still going: not finished, not declined, not cancelled, and (for a creator) not a draft nobody has sent. */
export const isOpenDeal = (memo: Memo): boolean => !OVER.includes(memo.stage) && memo.stage !== "draft";
export const openDeals = (memos: Memo[]): number => memos.filter(isOpenDeal).length;

export type Coming = { memo: Memo; on: string; days: number; yours: boolean };

/** Deals whose work is still to be made or approved. At the payment stage the work is done, so its work date means nothing any more. */
const WORK_STAGES: string[] = ["memo_sent", "agreed", "in_progress"];

/** The next dated things across the deals, nearest first: the day the work is due by (or the content date agreed). */
export function comingUp(memos: Memo[], role: Role, today: string, limit = 4): Coming[] {
  return memos
    .filter((m) => isOpenDeal(m) && WORK_STAGES.includes(m.stage))
    .map((memo) => ({ memo, on: memo.work_due_on ?? memo.content_due_on ?? null }))
    .filter((x): x is { memo: Memo; on: string } => x.on !== null)
    .map(({ memo, on }) => ({ memo, on, days: daysUntil(on, today), yours: moveOf(memo, role) === "yours" }))
    .sort((a, b) => a.days - b.days)
    .slice(0, limit);
}

// ---- A campaign's own page (frontend/design/dashboard-plan.md, D-205) ----

/** The figures a brand can compare posts by, in the order they are offered. Impressions are rarely on a screenshot and are shown in a post's own detail. */
export const METRICS = ["views", "reach", "likes", "comments", "saves", "shares"] as const;
export type Metric = (typeof METRICS)[number];
export const isMetric = (value: string | null | undefined): value is Metric => METRICS.includes(value as Metric);

export type Engagement = { rate: number; partial: boolean };

/**
 * How much the people who saw a post did something about it, CALCULATED from the numbers read: likes, comments, saves and shares over
 * views (or over reach when the screenshot showed no views). It needs a base above zero and at least likes or comments; `partial` says
 * some of the four were not shown, so the real rate is at least this. Never a guess for a post whose screenshot said too little.
 */
export function engagementOf(n: Numbers): Engagement | null {
  const base = typeof n.views === "number" ? n.views : typeof n.reach === "number" ? n.reach : null;
  if (base === null || base <= 0) return null;
  if (typeof n.likes !== "number" && typeof n.comments !== "number") return null;
  const parts = [n.likes, n.comments, n.saves, n.shares];
  const shown = parts.filter((v): v is number => typeof v === "number");
  return { rate: shown.reduce((a, b) => a + b, 0) / base, partial: shown.length < parts.length };
}

export type Ranked = { post: Post; value: number | null };

/** Posts by one figure, biggest first; a post whose screenshot did not show it goes last, with no value (not zero). */
export function rankPosts(posts: Post[], metric: Metric): Ranked[] {
  return posts
    .map((post) => ({ post, value: post.numbers[metric] }))
    .sort((a, b) => (b.value ?? -1) - (a.value ?? -1));
}

export type Funnel = { status: "submitted" | "shortlisted" | "accepted" | "rejected"; count: number }[];

/** Where the applications to a campaign stand: every status, zeros included, withdrawn left out. */
export const funnelOf = (report: Report): Funnel => {
  const a = report.totals.applications;
  return [
    { status: "submitted", count: a.submitted },
    { status: "shortlisted", count: a.shortlisted },
    { status: "accepted", count: a.accepted },
    { status: "rejected", count: a.rejected },
  ];
};

const STAGES = ["memo_sent", "agreed", "in_progress", "payment", "finished"] as const;
export type StageKey = (typeof STAGES)[number];
export const STAGE_ORDER: readonly StageKey[] = STAGES;

/** Deals at each stage of the journey, in order, zeros included. Declined and cancelled deals are not stages. */
export const stageCountsOf = (report: Report): { stage: StageKey; count: number }[] => STAGES.map((stage) => ({ stage, count: report.deals.filter((d) => d.stage === stage).length }));

/** 0.0912 as "9.1%". */
export const formatPercent = (rate: number): string => new Intl.NumberFormat("en-IN", { style: "percent", maximumFractionDigits: 1 }).format(rate);

/** The average engagement across the posts that had enough shown to calculate one, and how many those were. Null when none did. */
export function averageEngagement(posts: Post[]): { rate: number; partial: boolean; count: number } | null {
  const all = posts.map((p) => engagementOf(p.numbers)).filter((e): e is Engagement => e !== null);
  if (all.length === 0) return null;
  return { rate: all.reduce((a, e) => a + e.rate, 0) / all.length, partial: all.some((e) => e.partial), count: all.length };
}
