"use client";

import Link from "next/link";
import { Pill } from "@/components/ui/pill";
import { Skeleton } from "@/components/ui/skeleton";
import { comingUp, type Coming } from "@/lib/dashboard";
import { formatDayMonth } from "@/lib/format";
import { t } from "@/lib/app-messages";
import { todayInIndia } from "@/lib/onboarding";
import { useDeals } from "@/lib/queries";
import type { Role } from "@/lib/session";
import { Panel } from "./panel";

function whenWords(days: number): string {
  if (days < 0) return days === -1 ? t("dashboard.coming.when.lateOne") : t("dashboard.coming.when.late", { days: -days });
  return days === 0 ? t("dashboard.coming.when.today") : days === 1 ? t("dashboard.coming.when.tomorrow") : t("dashboard.coming.when.days", { days });
}

function Row({ c }: { c: Coming }) {
  const [day = "", month = ""] = formatDayMonth(c.on).split(" ");
  return (
    <li>
      <Link href={`/app/deals/${c.memo.id}`} className="t-base grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3.5 rounded-2xl p-2 -m-2 hover:bg-sunk">
        <span aria-hidden className="grid size-12 shrink-0 place-items-center rounded-2xl bg-sunk leading-none">
          <span className="grid justify-items-center gap-0.5"><span className="text-[17px] font-semibold tabular-nums">{day}</span><span className="text-[10px] font-semibold uppercase tracking-wide text-muted">{month}</span></span>
        </span>
        <span className="grid min-w-0 gap-0.5">
          <span className="truncate text-[15px] font-semibold">{c.memo.counterparty_name ?? c.memo.campaign_title}</span>
          <span className={`truncate text-sm ${c.days < 0 ? "font-semibold text-bad" : "text-muted"}`}>{c.memo.counterparty_name ? `${c.memo.campaign_title} · ` : ""}{whenWords(c.days)}</span>
        </span>
        <Pill tone={c.yours ? "dark" : "neutral"}>{t(c.yours ? "dashboard.coming.yours" : "dashboard.coming.waiting")}</Pill>
      </Link>
    </li>
  );
}

/** The next dated things across the person's deals, nearest first. Names come from the deal itself (R1). */
export function ComingUp({ role }: { role: Role }) {
  const deals = useDeals();
  const items = deals.data ? comingUp(deals.data, role, todayInIndia()) : [];
  return (
    <Panel title={t("dashboard.coming.title")} action={{ href: "/app/deals", label: t("dashboard.coming.all") }}>
      {deals.isPending ? (
        <div aria-busy="true" className="grid gap-3"><Skeleton className="h-12" /><Skeleton className="h-12" /></div>
      ) : deals.isError ? (
        <p className="text-[15px] text-muted">{t("dashboard.coming.error")}</p>
      ) : items.length === 0 ? (
        <p className="text-[15px] leading-6 text-muted">{t("dashboard.coming.empty")}</p>
      ) : (
        <ul className="grid gap-4">{items.map((c) => <Row key={c.memo.id} c={c} />)}</ul>
      )}
    </Panel>
  );
}
