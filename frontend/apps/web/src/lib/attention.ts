import type { components } from "@colyv/api";
import { formatDayMonth } from "./format.ts";
import type { MessageKey } from "./messages.ts";
import type { Role } from "./session.ts";

// Turns one item of GET /me/attention into the facts a row shows. The API sends a `kind` and the facts; the words are ours
// (messages/en.json), so this returns message keys, never text. Names (a brand, a campaign) are data, not copy.
export type AttentionItem = components["schemas"]["AttentionItemRead"];
export type Kind = AttentionItem["kind"];

export type Row = {
  id: string;
  kind: Kind;
  tone: "money" | "work" | "account" | "security";
  titleKey: MessageKey;
  titleVars: Record<string, string | number>;
  /** Names from the data, such as "Chennai Bakes · Diwali sweets reel". */
  context: string | null;
  contextKey: MessageKey | null;
  amountPaise: number | null;
  ctaKey: MessageKey;
  href: string;
  due: { key: MessageKey; vars: Record<string, string | number>; tone: "late" | "soon" | "normal" } | null;
};

const MONEY: Kind[] = ["pay_creator", "confirm_payment", "payment_overdue"];
const SECURITY: Kind[] = ["new_sign_in"];
const ACCOUNT: Kind[] = ["upi_change_pending", "phone_change_pending", "deletion_pending", "fix_domain_record", "domain_lapsed", "domain_claim_expired"];
const TAKES_EFFECT: Kind[] = ["upi_change_pending", "phone_change_pending", "deletion_pending"];

export const toneOf = (kind: Kind): Row["tone"] => (SECURITY.includes(kind) ? "security" : ACCOUNT.includes(kind) ? "account" : MONEY.includes(kind) ? "money" : "work");

function dueFor(item: AttentionItem): Row["due"] {
  const { days_left: days, due_on: dueOn, kind } = item;
  if (days === null || days === undefined || !dueOn) return null;
  const group = kind === "review_proof" ? "approves" : TAKES_EFFECT.includes(kind) ? "effective" : "due";
  if (days < 0) return { key: (-days === 1 ? "attention.due.late.one" : "attention.due.late.other") as MessageKey, vars: { days: -days }, tone: "late" };
  if (days === 0) return { key: `attention.${group}.today` as MessageKey, vars: {}, tone: "soon" };
  if (days === 1) return { key: `attention.${group}.tomorrow` as MessageKey, vars: {}, tone: "soon" };
  if (days <= 3) return { key: `attention.${group}.soon` as MessageKey, vars: { days }, tone: days <= 2 ? "soon" : "normal" };
  return { key: `attention.${group}.date` as MessageKey, vars: { date: formatDayMonth(dueOn) }, tone: "normal" };
}

/** Where the row's button goes. Screens that do not exist yet answer with a plain "next" page. */
export function hrefFor(item: AttentionItem): string {
  const memo = item.memo_id;
  switch (item.kind) {
    case "respond_to_dispute": return memo ? `/app/deals/${memo}/dispute` : "/app/deals";
    case "answer_memo": case "deliver_work": case "resubmit_work": case "confirm_payment": case "payment_overdue":
    case "revise_memo": case "review_proof": case "pay_creator":
      return memo ? `/app/deals/${memo}` : "/app/deals";
    case "review_applications": return item.campaign_id ? `/app/campaigns/${item.campaign_id}` : "/app/campaigns";
    case "draft_memo": return item.application_id ? `/app/applications/${item.application_id}/memo` : "/app/deals";
    case "answer_invitation": return item.application_id ? `/app/applications/${item.application_id}` : "/app/discover";
    case "new_sign_in": return "/app/me/sessions";
    case "upi_change_pending": return "/app/me/upi";
    case "phone_change_pending": return "/app/me/phone";
    case "deletion_pending": return "/app/me/delete";
    case "fix_domain_record": case "domain_lapsed": case "domain_claim_expired": return "/app/me/website";
  }
}

export function toRow(item: AttentionItem, role: Role): Row {
  const kind = item.kind;
  let titleKey = `attention.kind.${kind}.title` as MessageKey;
  const titleVars: Row["titleVars"] = {};
  if (kind === "review_applications") {
    const count = item.count ?? 1;
    titleKey = `attention.kind.review_applications.title.${count === 1 ? "one" : "other"}` as MessageKey;
    titleVars.count = count;
  }
  if (item.domain) titleVars.domain = item.domain;
  if (kind === "new_sign_in") titleVars.device = ""; // set by the screen, which looks up the device words
  const counterparty = item.counterparty ? (role === "brand" ? `@${item.counterparty}` : item.counterparty) : null;
  const context = [counterparty, item.campaign_title].filter(Boolean).join(" · ") || null;
  const hasFixedContext = kind === "new_sign_in" || TAKES_EFFECT.includes(kind);
  return {
    id: [kind, item.memo_id, item.application_id, item.campaign_id, item.proof_id, item.session_id].filter(Boolean).join(":"),
    kind,
    tone: toneOf(kind),
    titleKey,
    titleVars,
    context: hasFixedContext ? null : context,
    contextKey: hasFixedContext ? (`attention.kind.${kind}.context` as MessageKey) : null,
    amountPaise: item.amount_paise ?? null,
    ctaKey: `attention.kind.${kind}.cta` as MessageKey,
    href: hrefFor(item),
    due: dueFor(item),
  };
}

/** For a new sign-in: the name the app gave itself, else what it said it is, else "another device". */
export function deviceWords(item: AttentionItem): { label: string | null; fallbackKey: MessageKey } {
  const platform = item.device_platform;
  return { label: item.device_label ?? null, fallbackKey: (platform ? `attention.device.${platform}` : "attention.device.unknown") as MessageKey };
}
