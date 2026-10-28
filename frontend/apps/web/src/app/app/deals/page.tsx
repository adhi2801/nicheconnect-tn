"use client";

import { useState } from "react";
import { Button, ButtonLink } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Notice } from "@/components/ui/notice";
import { Reveal } from "@/components/ui/reveal";
import { Skeleton } from "@/components/ui/skeleton";
import { FilterBar } from "@/components/deals/filter-bar";
import { JourneyBoard } from "@/components/deals/journey-board";
import { PaymentsTable } from "@/components/deals/payments-table";
import { Kolam } from "@/components/today/kolam";
import { applyFilter, closedCounts, groupByStage, moveOf, paymentsByMemo, type Filter } from "@/lib/deals";
import { ApiError } from "@/lib/errors";
import { t } from "@/lib/messages";
import { useDeals, usePayments } from "@/lib/queries";
import { useSession } from "@/lib/use-session";

// Deals (frontend/design/screen-plan.md C6 and B9): every deal as a journey, so a creator and a brand can both see where each one is.
export default function DealsPage() {
  const state = useSession();
  const role = state.status === "signedIn" ? state.session.role : "creator";
  const deals = useDeals();
  const payments = usePayments();
  const [filter, setFilter] = useState<Filter>("all");

  const memos = deals.data ?? [];
  const needYou = memos.filter((m) => moveOf(m, role) === "yours").length;
  const closed = closedCounts(memos);
  const byMemo = paymentsByMemo(payments.data ?? []);
  const columns = groupByStage(applyFilter(memos, role, filter), role);
  const count = memos.filter((m) => m.stage !== "declined" && m.stage !== "cancelled").length;

  // minmax(0, 1fr): without it the board's own width would widen the page instead of scrolling inside the board.
  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-6 lg:gap-7">
      <Reveal>
        <header className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end">
          <div className="grid gap-1.5">
            <h1 className="font-display text-[2rem] font-semibold leading-[1.1] tracking-tight sm:text-[2.5rem]">{t("deals.title")}</h1>
            <p className="max-w-[60ch] text-base text-muted">{t("deals.subtitle")}</p>
            {deals.data && memos.length > 0 && <p className="text-sm font-medium text-muted">{t(count === 1 ? "deals.count.one" : "deals.count.other", { count })} · {needYou === 0 ? t("deals.summary.none") : t("deals.summary.needYou", { count: needYou })}</p>}
          </div>
          {memos.length > 0 && <FilterBar value={filter} onChange={setFilter} />}
        </header>
      </Reveal>

      <Reveal index={1}>
        {deals.isPending ? (
          <div aria-busy="true" className="flex gap-3 overflow-hidden rounded-[1.75rem] bg-sunk p-4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-72 min-w-[15rem] flex-1 rounded-3xl bg-line" />)}</div>
        ) : deals.isError ? (
          <Notice tone="error" action={<Button variant="secondary" className="min-h-10 px-4 text-sm" onClick={() => void deals.refetch()}>{t("common.retry")}</Button>}>
            <p className="font-semibold">{t("deals.errorTitle")}</p>
            <p>{deals.error instanceof ApiError && deals.error.kind === "busy" ? t("common.busy") : deals.error instanceof ApiError && deals.error.kind === "network" ? t("common.offline") : t("common.somethingWrong")}</p>
          </Notice>
        ) : memos.length === 0 ? (
          <Card className="grid justify-items-start gap-5 p-6 sm:p-8">
            <Kolam />
            <div className="grid gap-2">
              <h2 className="font-display text-2xl font-semibold tracking-tight">{t("deals.empty.title")}</h2>
              <p className="max-w-[52ch] text-[15px] leading-6 text-muted">{t(`deals.empty.body.${role}`)}</p>
            </div>
            <ButtonLink href={role === "creator" ? "/app/discover" : "/app/campaigns"}>{t(role === "creator" ? "deals.empty.ctaCreator" : "deals.empty.ctaBrand")}</ButtonLink>
          </Card>
        ) : (
          <div className="grid grid-cols-[minmax(0,1fr)] gap-3">
            <JourneyBoard columns={columns} role={role} byMemo={byMemo} />
            {(closed.declined > 0 || closed.cancelled > 0) && (
              <p className="px-2 text-sm text-muted"><span className="font-semibold text-ink">{t("deals.closed.label")}:</span> {[closed.declined > 0 ? t("deals.closed.declined", { count: closed.declined }) : null, closed.cancelled > 0 ? t("deals.closed.cancelled", { count: closed.cancelled }) : null].filter(Boolean).join(", ")}</p>
            )}
          </div>
        )}
      </Reveal>

      {!deals.isPending && !deals.isError && <Reveal index={2}><PaymentsTable role={role} /></Reveal>}
    </div>
  );
}
