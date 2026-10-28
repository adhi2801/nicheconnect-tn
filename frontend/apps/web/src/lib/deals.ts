import type { components } from "@colyv/api";
import type { Role } from "./session.ts";

// The facts behind the Deals board (frontend/design/screen-plan.md C6 and B9). The API says each deal's `stage` and whose move it is;
// everything here is arranging and wording, never deciding.
type Api = components["schemas"]["MemoWithStageRead"];
/** A campaign title and the other side's name are not in the memo list yet (frontend request R1), so they are optional here:
 *  shown when the API sends them, filled from the payments list where one exists, and otherwise left out. */
export type Memo = Api & { campaign_title?: string | null; counterparty_name?: string | null };
export type Payment = components["schemas"]["PaymentListItem"];
export type Stage = Api["stage"];
export type BoardStage = Exclude<Stage, "declined" | "cancelled">;

const CREATOR_STAGES: BoardStage[] = ["memo_sent", "agreed", "in_progress", "payment", "finished"];
/** A brand also sees its drafts, which a creator never does. */
export const boardStages = (role: Role): BoardStage[] => (role === "brand" ? ["draft", ...CREATOR_STAGES] : CREATOR_STAGES);

export type Move = "yours" | "theirs" | "ended";
export const moveOf = (memo: Memo, role: Role): Move => (memo.waiting_on === null || memo.waiting_on === undefined ? "ended" : memo.waiting_on === role ? "yours" : "theirs");

export type Filter = "all" | "mine" | "theirs";
export const applyFilter = (memos: Memo[], role: Role, filter: Filter): Memo[] =>
  filter === "all" ? memos : memos.filter((m) => moveOf(m, role) === (filter === "mine" ? "yours" : "theirs"));

/** Inside a column: the ones that need the person first, then the nearest content date, then the most recently touched. */
function compare(role: Role) {
  return (a: Memo, b: Memo): number => {
    const mineA = moveOf(a, role) === "yours" ? 0 : 1;
    const mineB = moveOf(b, role) === "yours" ? 0 : 1;
    if (mineA !== mineB) return mineA - mineB;
    const dueA = a.content_due_on ?? "9999-12-31";
    const dueB = b.content_due_on ?? "9999-12-31";
    if (dueA !== dueB) return dueA < dueB ? -1 : 1;
    return a.updated_at < b.updated_at ? 1 : a.updated_at > b.updated_at ? -1 : 0;
  };
}

export type Column = { stage: BoardStage; memos: Memo[] };
export function groupByStage(memos: Memo[], role: Role): Column[] {
  const sort = compare(role);
  return boardStages(role).map((stage) => ({ stage, memos: memos.filter((m) => m.stage === stage).sort(sort) }));
}

/** Declined and cancelled deals are not stages of a journey, so they sit apart as a count. */
export const closedCounts = (memos: Memo[]): { declined: number; cancelled: number } => ({
  declined: memos.filter((m) => m.stage === "declined").length,
  cancelled: memos.filter((m) => m.stage === "cancelled").length,
});

export type Who = { title: string | null; name: string | null };

/** The campaign and the other side, for a deal card. A name the memo carries wins; otherwise the payments list knows it for any deal
 *  that has a payment: a creator sees the brand, a brand sees the creator. */
export function whoFor(memo: Memo, role: Role, byMemo: Map<string, Payment>): Who {
  const payment = byMemo.get(memo.id);
  const fromPayment = payment ? (role === "creator" ? payment.brand_name : payment.creator_display_name) : null;
  return { title: memo.campaign_title ?? payment?.campaign_title ?? null, name: memo.counterparty_name ?? fromPayment ?? null };
}

export const paymentsByMemo = (payments: Payment[]): Map<string, Payment> => new Map(payments.map((p) => [p.deal_memo_id, p]));

/** The figure a card shows: what was agreed once there is an agreement, else the fee in the memo. A draft may have neither yet. */
export const amountOf = (memo: Memo): number | null => memo.agreed_amount_paise ?? memo.fee_amount_paise ?? null;

export type PaymentPill = { tone: "ok" | "warn" | "bad" | "neutral"; key: string; vars: Record<string, string | number> };

/** The words and colour for a payment's state. Facts only: who did what, never a bare "Paid" (docs/standards/ux.md section 6). */
export function paymentPill(p: Pick<Payment, "state" | "due_on" | "days_overdue">, formatDayMonth: (isoDate: string) => string): PaymentPill {
  switch (p.state) {
    case "due": return { tone: "neutral", key: "deals.payments.state.due", vars: { date: formatDayMonth(p.due_on) } };
    case "late": return { tone: "bad", key: p.days_overdue === 1 ? "deals.payments.state.late.one" : "deals.payments.state.late.other", vars: { days: p.days_overdue } };
    case "unpaid": return { tone: "bad", key: "deals.payments.state.unpaid", vars: { days: p.days_overdue } };
    case "paid": return { tone: "warn", key: "deals.payments.state.paid", vars: {} };
    case "unconfirmed": return { tone: "warn", key: "deals.payments.state.unconfirmed", vars: {} };
    case "confirmed": return { tone: "ok", key: "deals.payments.state.confirmed", vars: {} };
  }
}
