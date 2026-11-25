import type { components } from "@colyv/api";
import type { MessageKey } from "./messages.ts";
import type { Tone } from "./tone.ts";

// My applications (frontend/design/screen-plan.md C5): where each one stands, dated, with the reason when a brand said no.

export type Application = components["schemas"]["ApplicationRead"];
export type Status = Application["status"];
export type Feedback = components["schemas"]["ApplicationFeedbackRead"];

/** The order a creator reads them: what is still moving first, then what ended. */
export const GROUPS: readonly { id: "moving" | "invited" | "ended"; statuses: readonly Status[] }[] = [
  { id: "moving", statuses: ["shortlisted", "submitted", "accepted"] },
  { id: "invited", statuses: ["invited"] },
  { id: "ended", statuses: ["rejected", "withdrawn", "declined"] },
];

const STATUS_RANK: Record<Status, number> = { shortlisted: 0, submitted: 1, accepted: 2, invited: 3, rejected: 4, withdrawn: 5, declined: 6 };

/** Grouped, each group newest change first. An empty group is left out. A status the app does not know yet goes last, never lost. */
export type GroupId = (typeof GROUPS)[number]["id"] | "other";

export function groupApplications(items: readonly Application[]): { id: GroupId; items: Application[] }[] {
  const known = new Set<string>(GROUPS.flatMap((g) => g.statuses));
  const newestFirst = (a: Application, b: Application) => (STATUS_RANK[a.status] ?? 9) - (STATUS_RANK[b.status] ?? 9) || b.status_changed_at.localeCompare(a.status_changed_at) || a.id.localeCompare(b.id);
  const groups: { id: GroupId; items: Application[] }[] = GROUPS.map((g) => ({ id: g.id, items: items.filter((a) => g.statuses.includes(a.status)).sort(newestFirst) }));
  const other = items.filter((a) => !known.has(a.status));
  if (other.length > 0) groups.push({ id: "other", items: [...other] });
  return groups.filter((g) => g.items.length > 0);
}

export const STATUS_WORDS: Record<Status, MessageKey> = {
  submitted: "applications.status.submitted",
  shortlisted: "applications.status.shortlisted",
  accepted: "applications.status.accepted",
  rejected: "applications.status.rejected",
  withdrawn: "applications.status.withdrawn",
  invited: "applications.status.invited",
  declined: "applications.status.declined",
};

export const STATUS_TONE: Record<Status, Tone> = { submitted: "neutral", shortlisted: "ok", accepted: "ok", invited: "dark", rejected: "bad", withdrawn: "neutral", declined: "neutral" };

export const statusWords = (status: string): MessageKey => STATUS_WORDS[status as Status] ?? "applications.status.other";
export const statusTone = (status: string): Tone => STATUS_TONE[status as Status] ?? "neutral";

export const REASON_WORDS: Record<NonNullable<Application["rejection_reason"]>, MessageKey> = {
  budget_mismatch: "applications.reason.budget_mismatch",
  audience_mismatch: "applications.reason.audience_mismatch",
  timing: "applications.reason.timing",
  chose_another_creator: "applications.reason.chose_another_creator",
  incomplete_profile: "applications.reason.incomplete_profile",
  other: "applications.reason.other",
};
export const reasonWords = (reason: string): MessageKey => REASON_WORDS[reason as keyof typeof REASON_WORDS] ?? "applications.reason.other";

/** A creator can take back only what a brand has not answered for good: submitted or shortlisted. */
export const canWithdraw = (a: Pick<Application, "status">): boolean => a.status === "submitted" || a.status === "shortlisted";

/** The campaigns these applications are for, once each, so the stopgap fetches each campaign once (request R7). */
export const campaignIdsOf = (items: readonly Pick<Application, "campaign_id">[]): string[] => [...new Set(items.map((a) => a.campaign_id))];

/** Facts from the feedback, only those that rest on enough to say something. "Not enough to say" shows nothing, never a zero. */
export function feedbackLines(f: Feedback): { key: MessageKey; vars: Record<string, string | number>; reason?: string }[] {
  const lines: { key: MessageKey; vars: Record<string, string | number>; reason?: string }[] = [];
  if (f.most_common_reason) lines.push({ key: "applications.feedback.commonReason", vars: { count: f.rejections }, reason: f.most_common_reason });
  if (f.quotes_compared >= 3 && f.quotes_above_budget > 0) lines.push({ key: "applications.feedback.quotesAbove", vars: { above: f.quotes_above_budget, compared: f.quotes_compared } });
  if (f.open_campaigns_in_your_niches > 0) lines.push({ key: f.open_campaigns_in_your_niches === 1 ? "applications.feedback.openOne" : "applications.feedback.open", vars: { count: f.open_campaigns_in_your_niches } });
  return lines;
}
