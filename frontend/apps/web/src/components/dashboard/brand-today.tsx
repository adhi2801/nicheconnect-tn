"use client";

import type { UseQueryResult } from "@tanstack/react-query";
import { DesignSlot } from "@/design/design-slot";
import { ButtonLink } from "@/components/ui/button";
import { NeedsYouArea, type Attention } from "@/components/today/needs-you-area";
import { PaymentGauge } from "@/components/today/payment-gauge";
import { progressOf } from "@/lib/dashboard";
import { t } from "@/lib/app-messages";
import { CampaignsPanel } from "./campaigns-panel";
import { CollabsPanel } from "./collabs-panel";
import { NextDue } from "./next-due";
import { PerformancePanel } from "./performance-panel";
import { SplitBar } from "./split-bar";
import { useBrandOverview } from "./use-brand-overview";

/** A brand's Today: how the collaborations are going, what needs them, their campaigns and each collaboration's status, and how the
 *  posts performed (read from the creators' screenshots). */
export function BrandToday({ attention }: { attention: UseQueryResult<Attention> }) {
  const overview = useBrandOverview();
  const items = attention.data?.items ?? [];
  const progress = progressOf(overview.reports);
  return (
    <div className="grid gap-4">
      {overview.total === 0 && (
        <section aria-labelledby="first-steps" className="grid gap-6 rounded-[2rem] bg-sage p-6 shadow-[0_0_0_1px_var(--c-line)] sm:p-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)] lg:items-center">
          <div className="grid content-start gap-3">
            <h2 id="first-steps" className="type-subtitle">{t("brandCampaigns.first.title")}</h2>
            <p className="text-[15px] leading-6 text-muted">{t("brandCampaigns.first.body")}</p>
            <ButtonLink href="/app/campaigns/new" className="mt-2 justify-self-start">{t("brandCampaigns.list.new")}</ButtonLink>
          </div>
          <ol className="grid gap-2.5 sm:grid-cols-2">
            {(["1", "2", "3", "4"] as const).map((n) => (
              <li key={n} className="flex items-center gap-3 rounded-3xl bg-surface p-4 text-[15px] leading-5">
                <span aria-hidden className="grid size-8 shrink-0 place-items-center rounded-full bg-lime text-[13px] font-semibold text-on-lime">{n}</span>
                {t(`brandCampaigns.list.empty.steps.${n}`)}
              </li>
            ))}
          </ol>
        </section>
      )}
      <section aria-labelledby="progress-title" className="grid gap-4">
        <h2 id="progress-title" className="sr-only">{t("dashboard.progress.title")}</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <SplitBar label={t("dashboard.progress.applications")} share={progress.applications} fill="ink" />
          <SplitBar label={t("dashboard.progress.memos")} share={progress.memos} fill="lime" />
          <SplitBar label={t("dashboard.progress.work")} share={progress.work} fill="hatch" />
          <SplitBar label={t("dashboard.progress.paid")} share={progress.paid} fill="lime" />
        </div>
      </section>
      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
        <div className="grid gap-4">
          <NeedsYouArea attention={attention} role="brand" />
          <CollabsPanel />
          <PerformancePanel reports={overview.reports} loading={overview.loading} failed={overview.failedReports} />
        </div>
        <div className="grid gap-4">
          <DesignSlot id="today.feature" optional className="rounded-[2rem]" />
          <CampaignsPanel campaigns={overview.list} reports={overview.byId} loading={overview.loading} failedLoad={overview.failedLoad} failedReports={overview.failedReports} />
          <NextDue items={items} role="brand" />
          <PaymentGauge role="brand" />
        </div>
      </div>
    </div>
  );
}
