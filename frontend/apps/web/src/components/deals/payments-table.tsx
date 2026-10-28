"use client";

import Link from "next/link";
import { Card } from "@/components/ui/card";
import { Pill } from "@/components/ui/pill";
import { Skeleton } from "@/components/ui/skeleton";
import { paymentPill, type Payment } from "@/lib/deals";
import { formatDayMonth, formatPaise } from "@/lib/format";
import { t, type MessageKey } from "@/lib/messages";
import { usePayments } from "@/lib/queries";
import type { Role } from "@/lib/session";

const SHOWN = 6;

/** The newest payments, with who and what each is for, and where it stands in words. Facts only: who marked what, and when. */
export function PaymentsTable({ role }: { role: Role }) {
  const payments = usePayments();
  if (payments.isPending) return <Skeleton className="h-56 rounded-[1.75rem]" />;
  if (payments.isError) return null; // the board above stands on its own; payments are extra
  const rows = payments.data.slice(0, SHOWN);
  const who = (p: Payment) => (role === "creator" ? p.brand_name : p.creator_display_name);
  const status = (p: Payment) => {
    const pill = paymentPill(p, formatDayMonth);
    return <Pill tone={pill.tone}>{t(pill.key as MessageKey, pill.vars)}</Pill>;
  };
  return (
    <Card className="grid gap-4 p-5 sm:p-6">
      <h2 className="font-display text-xl font-semibold tracking-tight">{t("deals.payments.title")}</h2>
      {rows.length === 0 ? (
        <p className="text-sm text-muted">{t("deals.payments.none")}</p>
      ) : (
        <>
          <table className="hidden w-full text-left text-sm sm:table">
            <caption className="sr-only">{t("deals.payments.title")}</caption>
            <thead>
              <tr className="text-xs text-muted">
                <th scope="col" className="pb-2 font-medium">{t("deals.payments.deal")}</th>
                <th scope="col" className="pb-2 font-medium">{t(`deals.payments.with.${role}`)}</th>
                <th scope="col" className="pb-2 font-medium">{t("deals.payments.amount")}</th>
                <th scope="col" className="pb-2 font-medium">{t("deals.payments.status")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((p) => (
                <tr key={p.id} className="border-t border-line">
                  <td className="py-3 pr-4"><Link href={`/app/deals/${p.deal_memo_id}`} className="font-semibold underline-offset-4 hover:underline">{p.campaign_title}</Link></td>
                  <td className="py-3 pr-4 text-muted">{who(p)}</td>
                  <td className="py-3 pr-4 font-semibold tabular-nums">{formatPaise(p.amount_paise)}</td>
                  <td className="py-3">{status(p)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <ul className="grid gap-3 sm:hidden">
            {rows.map((p) => (
              <li key={p.id} className="grid gap-1.5 rounded-2xl bg-sunk p-3.5">
                <Link href={`/app/deals/${p.deal_memo_id}`} className="font-semibold">{p.campaign_title}</Link>
                <p className="text-sm text-muted">{who(p)}</p>
                <div className="flex flex-wrap items-center justify-between gap-2"><span className="font-display font-semibold tabular-nums">{formatPaise(p.amount_paise)}</span>{status(p)}</div>
              </li>
            ))}
          </ul>
        </>
      )}
    </Card>
  );
}
