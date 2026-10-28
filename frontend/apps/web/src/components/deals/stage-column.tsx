import { t, type MessageKey } from "@/lib/messages";
import { whoFor, type BoardStage, type Memo, type Payment } from "@/lib/deals";
import type { Role } from "@/lib/session";
import { DealCard } from "./deal-card";

type Props = { stage: BoardStage; memos: Memo[]; role: Role; byMemo: Map<string, Payment>; connect: boolean };

/** One stage of the journey: a soft white panel with its deals. A dashed line joins it to the stage before. */
export function StageColumn({ stage, memos, role, byMemo, connect }: Props) {
  const label = t(`deals.stage.${stage}.label` as MessageKey);
  return (
    <section aria-label={`${label}, ${t(memos.length === 1 ? "deals.count.one" : "deals.count.other", { count: memos.length })}`} className="relative min-w-[15rem] flex-1 snap-start">
      {connect && (
        <span aria-hidden className="absolute -left-6 top-9 hidden w-6 items-center lg:flex">
          <span className="size-1.5 rounded-full bg-line-strong" />
          <span className="h-0 flex-1 border-t-2 border-dashed border-line-strong/60" />
          <span className="size-1.5 rounded-full bg-line-strong" />
        </span>
      )}
      <div className="grid h-full content-start gap-3 rounded-3xl bg-surface p-3 shadow-card">
        <header className="flex items-start justify-between gap-2 px-1.5 pt-1.5">
          <div className="min-w-0">
            <h3 className="font-display text-[15px] font-semibold tracking-tight">{label}</h3>
            <p className="text-xs text-muted">{t(`deals.stage.${stage}.hint` as MessageKey)}</p>
          </div>
          <span aria-hidden className="rounded-full bg-sunk px-2.5 py-0.5 text-xs font-semibold tabular-nums">{memos.length}</span>
        </header>
        {memos.length === 0 ? (
          <p className="rounded-2xl border border-dashed border-line-strong/50 px-3 py-6 text-center text-xs text-muted">{t("deals.columnEmpty")}</p>
        ) : (
          <ul className="grid gap-2.5">
            {memos.map((m) => <li key={m.id}><DealCard memo={m} who={whoFor(m, role, byMemo)} role={role} /></li>)}
          </ul>
        )}
      </div>
    </section>
  );
}
