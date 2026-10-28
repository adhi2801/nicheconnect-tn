import Link from "next/link";
import { ArrowUpRightIcon, UserIcon } from "@/components/ui/icons";
import { Pill } from "@/components/ui/pill";
import { amountOf, moveOf, type Memo, type Who } from "@/lib/deals";
import { formatDayMonth, formatPaise, initials } from "@/lib/format";
import { t } from "@/lib/messages";
import type { Role } from "@/lib/session";

/** One deal. Where it is the person's move the card is dark, so what needs them stands out across the whole board. */
export function DealCard({ memo, who, role }: { memo: Memo; who: Who; role: Role }) {
  const move = moveOf(memo, role);
  const yours = move === "yours";
  const amount = amountOf(memo);
  const name = who.name;
  return (
    <Link href={`/app/deals/${memo.id}`} aria-label={`${t("deals.card.open")}: ${who.title ?? t("deals.card.untitled")}${name ? `, ${name}` : ""}`} className={`t-base group grid gap-3 rounded-2xl p-3.5 hover:-translate-y-0.5 ${yours ? "on-dark bg-ink text-on-accent" : "bg-sunk hover:bg-line"}`}>
      <div className="flex items-start gap-3">
        <span aria-hidden className={`grid size-9 shrink-0 place-items-center rounded-full text-[12px] font-semibold ${yours ? "bg-highlight text-on-highlight" : "bg-accent text-on-accent"}`}>{name ? initials(name) : <UserIcon width={16} height={16} />}</span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold">{name ?? t("deals.card.someone")}</p>
          <p className={`truncate text-xs ${yours ? "text-on-accent/75" : "text-muted"}`}>{who.title ?? t("deals.card.untitled")}</p>
        </div>
        {yours && <span aria-hidden className="grid size-7 shrink-0 place-items-center rounded-full bg-white/15"><ArrowUpRightIcon width={14} height={14} /></span>}
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-display text-lg font-semibold tabular-nums">{amount === null ? "" : formatPaise(amount)}</span>
        {memo.content_due_on && <Pill tone="neutral">{t("deals.card.due", { date: formatDayMonth(memo.content_due_on) })}</Pill>}
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
        <span className={`inline-flex items-center gap-1.5 font-semibold ${yours ? "text-highlight-deep" : "text-muted"}`}>
          {yours && <span aria-hidden className="size-1.5 rounded-full bg-highlight-deep" />}
          {move === "yours" ? t("deals.yourMove") : move === "theirs" ? t(memo.waiting_on === "brand" ? "deals.waitingOn.brand" : "deals.waitingOn.creator") : t("deals.ended")}
        </span>
        {memo.has_open_dispute && <Pill tone="bad">{t("deals.dispute")}</Pill>}
      </div>
    </Link>
  );
}
