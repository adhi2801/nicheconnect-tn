"use client";

import Link from "next/link";
import { Pill } from "@/components/ui/pill";
import { Skeleton } from "@/components/ui/skeleton";
import { isOpenDeal } from "@/lib/dashboard";
import { moveOf, type Memo } from "@/lib/deals";
import { formatDayMonth } from "@/lib/format";
import { t } from "@/lib/app-messages";
import { useDeals } from "@/lib/queries";
import { Avatar, Panel } from "./panel";

const SHOWN = 6;
const byUrgency = (a: Memo, b: Memo): number => {
  const mine = (moveOf(a, "brand") === "yours" ? 0 : 1) - (moveOf(b, "brand") === "yours" ? 0 : 1);
  if (mine !== 0) return mine;
  const dueA = a.work_due_on ?? a.content_due_on ?? "9999-12-31";
  const dueB = b.work_due_on ?? b.content_due_on ?? "9999-12-31";
  return dueA < dueB ? -1 : dueA > dueB ? 1 : 0;
};

/** Where each collaboration stands: the creator, the campaign, its stage, and whose move it is. A brand's view of "collab status". */
export function CollabsPanel() {
  const deals = useDeals();
  const open = (deals.data ?? []).filter(isOpenDeal).sort(byUrgency);
  return (
    <Panel title={t("dashboard.collabs.title")} action={{ href: "/app/deals", label: t("dashboard.collabs.all") }}>
      {deals.isPending ? (
        <div aria-busy="true" className="grid gap-3"><Skeleton className="h-12" /><Skeleton className="h-12" /><Skeleton className="h-12" /></div>
      ) : deals.isError ? (
        <p className="text-[15px] text-muted">{t("dashboard.coming.error")}</p>
      ) : open.length === 0 ? (
        <p className="text-[15px] leading-6 text-muted">{t("dashboard.collabs.empty")}</p>
      ) : (
        <ul className="grid">
          {open.slice(0, SHOWN).map((m) => {
            const mine = moveOf(m, "brand") === "yours";
            const due = m.work_due_on ?? m.content_due_on;
            return (
              <li key={m.id} className="border-t border-line first:border-t-0">
                <Link href={`/app/deals/${m.id}`} className="t-base grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3.5 py-3.5 hover:opacity-80">
                  <Avatar name={m.counterparty_name ?? m.campaign_title ?? ""} />
                  <span className="grid min-w-0 gap-0.5">
                    <span className="truncate text-[15px] font-semibold">{m.counterparty_name ?? m.campaign_title}</span>
                    <span className="truncate text-sm text-muted">{m.counterparty_name ? `${m.campaign_title} · ` : ""}{due ? t("dashboard.collabs.due", { date: formatDayMonth(due) }) : t(`deals.stage.${m.stage as "agreed"}.hint`)}</span>
                  </span>
                  <span className="grid justify-items-end gap-1.5">
                    <Pill tone="neutral">{t(`deals.stage.${m.stage as "agreed"}.label`)}</Pill>
                    <Pill tone={mine ? "dark" : "neutral"}>{t(mine ? "dashboard.collabs.yours" : "dashboard.collabs.theirs")}</Pill>
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </Panel>
  );
}
