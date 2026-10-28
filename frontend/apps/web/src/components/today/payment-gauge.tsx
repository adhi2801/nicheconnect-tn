"use client";

import { useId } from "react";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { formatPaise } from "@/lib/format";
import { t } from "@/lib/messages";
import { usePaymentTotals } from "@/lib/queries";
import type { Role } from "@/lib/session";

const R = 88;
const CX = 110;
const CY = 108;
const ARC = `M ${CX - R} ${CY} A ${R} ${R} 0 0 1 ${CX + R} ${CY}`;
const GAP = 1.4; // between segments, in hundredths of the arc

/** Where all the person's payments stand as one half-circle: confirmed, waiting to be confirmed, and not yet marked as paid
 *  (striped, because it is the part still to come). The words and amounts beside it say the same thing. */
export function PaymentGauge({ role }: { role: Role }) {
  const totals = usePaymentTotals();
  const hatchId = useId();
  if (totals.isPending) return <Skeleton className="h-64 rounded-[1.75rem]" />;
  if (totals.isError) return null; // the figure cards above already say the payments could not be loaded

  const done = totals.data.finished.amount_paise;
  const waiting = totals.data.awaiting_confirmation.amount_paise;
  const notMarked = totals.data.to_pay.amount_paise;
  const sum = done + waiting + notMarked;
  const pct = sum > 0 ? Math.round((done / sum) * 100) : 0;
  const parts = sum > 0 ? [
    { key: "done", share: (done / sum) * 100, stroke: "var(--c-gauge-deep)" },
    { key: "waiting", share: (waiting / sum) * 100, stroke: "var(--c-gauge-mid)" },
    { key: "notMarked", share: (notMarked / sum) * 100, stroke: `url(#${hatchId})` },
  ] : [];
  let start = 0;
  const legend = [
    { label: t("today.gauge.legendConfirmed"), amount: done, swatch: <span aria-hidden className="size-3 rounded-full bg-gauge-deep" /> },
    { label: t("today.gauge.legendWaiting"), amount: waiting, swatch: <span aria-hidden className="size-3 rounded-full bg-gauge-mid" /> },
    { label: t("today.gauge.legendNotMarked"), amount: notMarked, swatch: <span aria-hidden className="hatch size-3 rounded-full ring-1 ring-gauge-mid" /> },
  ];
  return (
    <Card className="grid gap-4 p-5 sm:p-6">
      <h2 className="font-display text-xl font-semibold tracking-tight">{t("today.gauge.title")}</h2>
      <div className="relative mx-auto w-full max-w-[16rem]">
        <svg viewBox="0 0 220 118" className="w-full" aria-hidden fill="none">
          <defs>
            <pattern id={hatchId} width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
              <rect width="7" height="7" fill="var(--c-highlight-soft)" />
              <line x1="0" y1="0" x2="0" y2="7" stroke="var(--c-gauge-mid)" strokeWidth="2.2" />
            </pattern>
          </defs>
          <path d={ARC} stroke="var(--c-surface-sunk)" strokeWidth={26} pathLength={100} />
          {parts.filter((p) => p.share > 0).map((p) => {
            const length = Math.max(p.share - GAP, 0.8);
            const offset = -start;
            start += p.share;
            return <path key={p.key} d={ARC} stroke={p.stroke} strokeWidth={26} pathLength={100} strokeDasharray={`${length} 200`} strokeDashoffset={offset} />;
          })}
        </svg>
        <div className="absolute inset-x-0 bottom-0 grid justify-items-center leading-none">
          {sum > 0 ? (
            <>
              <span className="font-display text-[2.5rem] font-medium tracking-tight tabular-nums">{pct}%</span>
              <span className="mt-1.5 text-sm text-muted">{t("today.gauge.centre")}</span>
            </>
          ) : (
            <span className="text-sm font-medium text-muted">{t("today.gauge.empty")}</span>
          )}
        </div>
      </div>
      {sum === 0 && <p className="text-center text-sm text-muted">{t(`today.gauge.emptyHint.${role}`)}</p>}
      <ul className="grid gap-2.5 text-sm">
        {legend.map((l) => (
          <li key={l.label} className="flex items-center gap-2.5">
            {l.swatch}
            <span className="text-muted">{l.label}</span>
            <span className="ml-auto font-semibold tabular-nums">{formatPaise(l.amount)}</span>
          </li>
        ))}
      </ul>
    </Card>
  );
}
