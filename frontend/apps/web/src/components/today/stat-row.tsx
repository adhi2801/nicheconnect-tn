"use client";

import { Button } from "@/components/ui/button";
import { Notice } from "@/components/ui/notice";
import { Pill } from "@/components/ui/pill";
import { Skeleton } from "@/components/ui/skeleton";
import { toRow, type AttentionItem } from "@/lib/attention";
import { formatPaise } from "@/lib/format";
import { t } from "@/lib/messages";
import { usePaymentTotals } from "@/lib/queries";
import type { Role } from "@/lib/session";
import { titleFor } from "./row-title";
import { StatCard } from "./stat-card";

type Bucket = { amount_paise: number; count: number };
const countWords = (b: Bucket): string => (b.count === 0 ? t("today.money.none") : t(b.count === 1 ? "today.money.count.one" : "today.money.count.other", { count: b.count }));

/** The four figures across the top: what needs the person, and where their payments stand, worded for their role. */
export function StatRow({ role, items, total }: { role: Role; items: AttentionItem[]; total: number }) {
  const totals = usePaymentTotals();
  const top = items[0];
  const heroFoot = top ? titleFor(toRow(top, role), top) : t("today.stats.allClearFoot");
  const hero = <StatCard tone="hero" label={t("today.stats.needsYou")} value={total} foot={<span className="line-clamp-2">{heroFoot}</span>} href="#needs-you" wide />;

  if (totals.isPending) return <div aria-busy="true" className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-[repeat(4,minmax(0,1fr))]">{hero}{[0, 1, 2].map((i) => <Skeleton key={i} className="h-40 rounded-3xl" />)}</div>;
  if (totals.isError) {
    return (
      <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-[repeat(4,minmax(0,1fr))]">
        {hero}
        <div className="col-span-2 xl:col-span-3">
          <Notice tone="error" action={<Button variant="secondary" className="min-h-10 px-4 text-sm" onClick={() => void totals.refetch()}>{t("common.retry")}</Button>}>{t("today.moneyError")}</Notice>
        </div>
      </div>
    );
  }
  const { awaiting_confirmation: awaiting, to_pay: toPay, overdue, finished } = totals.data;
  const late = overdue.amount_paise > 0 ? <Pill tone="bad">{t("today.money.late", { amount: formatPaise(overdue.amount_paise) })}</Pill> : null;
  // What each person acts on comes first: a creator confirms what a brand sent, a brand pays.
  const cards = role === "creator"
    ? [
        { label: t("today.money.creator.awaiting"), bucket: awaiting, extra: null },
        { label: t("today.money.creator.toPay"), bucket: toPay, extra: late },
      ]
    : [
        { label: t("today.money.brand.toPay"), bucket: toPay, extra: late },
        { label: t("today.money.brand.awaiting"), bucket: awaiting, extra: null },
      ];
  return (
    <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-[repeat(4,minmax(0,1fr))]">
      {hero}
      {cards.map((c) => <StatCard key={c.label} label={c.label} value={formatPaise(c.bucket.amount_paise)} foot={<span className="flex flex-wrap items-center gap-2"><span>{countWords(c.bucket)}</span>{c.extra}</span>} href="/app/deals" />)}
      <StatCard label={t("today.stats.confirmed")} value={formatPaise(finished.amount_paise)} foot={countWords(finished)} href="/app/deals" wide />
    </div>
  );
}
