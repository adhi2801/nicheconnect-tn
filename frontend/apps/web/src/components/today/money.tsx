"use client";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Notice } from "@/components/ui/notice";
import { Pill } from "@/components/ui/pill";
import { Skeleton } from "@/components/ui/skeleton";
import { formatPaise } from "@/lib/format";
import { t } from "@/lib/messages";
import { usePaymentTotals } from "@/lib/queries";
import type { Role } from "@/lib/session";

const gold = { background: "linear-gradient(150deg, var(--c-glance-gold-from), var(--c-glance-gold-to))" };

function Bucket({ amount, count }: { amount: number; count: number }) {
  return (
    <>
      <p className="font-display text-4xl font-medium tracking-tight tabular-nums">{formatPaise(amount)}</p>
      <p className="text-sm">{count === 0 ? t("today.money.none") : t(count === 1 ? "today.money.count.one" : "today.money.count.other", { count })}</p>
    </>
  );
}

/** Where the person's payments stand, from the payments totals. Two figures that matter, and what is confirmed so far. */
export function Money({ role }: { role: Role }) {
  const totals = usePaymentTotals();
  if (totals.isPending) return <div aria-busy="true" className="grid gap-3"><Skeleton className="h-36 rounded-3xl" /><Skeleton className="h-28 rounded-3xl" /></div>;
  if (totals.isError) return <Notice tone="error" action={<Button variant="secondary" className="min-h-10 px-4 text-sm" onClick={() => void totals.refetch()}>{t("common.retry")}</Button>}>{t("today.moneyError")}</Notice>;
  const { awaiting_confirmation: awaiting, to_pay: toPay, overdue, finished } = totals.data;
  const words = role === "creator" ? { awaiting: t("today.money.creator.awaiting"), toPay: t("today.money.creator.toPay") } : { awaiting: t("today.money.brand.awaiting"), toPay: t("today.money.brand.toPay") };
  // The figure each person acts on or waits on comes first: a creator confirms, a brand pays.
  const first = role === "creator" ? { label: words.awaiting, bucket: awaiting } : { label: words.toPay, bucket: toPay };
  const second = role === "creator" ? { label: words.toPay, bucket: toPay } : { label: words.awaiting, bucket: awaiting };
  return (
    <div className="grid gap-3">
      <div className="grid gap-1 rounded-3xl p-6 text-on-highlight shadow-card" style={gold}>
        <p className="text-sm font-semibold">{first.label}</p>
        <Bucket amount={first.bucket.amount_paise} count={first.bucket.count} />
        {role === "brand" && overdue.amount_paise > 0 && <div className="mt-2"><Pill tone="bad">{t("today.money.late", { amount: formatPaise(overdue.amount_paise) })}</Pill></div>}
      </div>
      <Card className="grid gap-1 p-6">
        <p className="text-sm font-semibold text-muted">{second.label}</p>
        <Bucket amount={second.bucket.amount_paise} count={second.bucket.count} />
        {role === "creator" && overdue.amount_paise > 0 && <div className="mt-2"><Pill tone="bad">{t("today.money.late", { amount: formatPaise(overdue.amount_paise) })}</Pill></div>}
      </Card>
      <p className="px-2 text-sm text-muted">{t("today.money.finished")}: <span className="font-semibold text-ink tabular-nums">{formatPaise(finished.amount_paise)}</span></p>
    </div>
  );
}
