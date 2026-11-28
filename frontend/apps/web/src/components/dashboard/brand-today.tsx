"use client";

import type { UseQueryResult } from "@tanstack/react-query";
import { DesignSlot } from "@/design/design-slot";
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
