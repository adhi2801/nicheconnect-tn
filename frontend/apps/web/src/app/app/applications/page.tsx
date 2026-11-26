"use client";

import { useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ApplicationRow } from "@/components/applications/application-row";
import { FeedbackCard } from "@/components/applications/feedback-card";
import { DiscoverTabs } from "@/components/discover/discover-tabs";
import { Kolam } from "@/components/today/kolam";
import { Button, ButtonLink } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { LoadError } from "@/components/ui/load-error";
import { Notice } from "@/components/ui/notice";
import { Reveal } from "@/components/ui/reveal";
import { Sheet } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { campaignIdsOf, groupApplications, type Application } from "@/lib/applications";
import type { Campaign } from "@/lib/campaigns";
import { ReportBlockSheet } from "@/components/safety/report-block-sheet";
import { ApiError, commonWordsKey } from "@/lib/errors";
import { t, type MessageKey } from "@/lib/app-messages";
import { useWithdraw } from "@/lib/mutations";
import { useCampaignsFor, useMyApplications } from "@/lib/queries";

const GROUP_TITLES: Record<ReturnType<typeof groupApplications>[number]["id"], MessageKey> = {
  moving: "applications.groups.moving",
  invited: "applications.groups.invited",
  ended: "applications.groups.ended",
  other: "applications.groups.other",
};

// My applications (screen-plan C5): a dated status and a reason turn a brand's silence into information.
export default function ApplicationsPage() {
  const mine = useMyApplications();
  const items = useMemo(() => mine.data ?? [], [mine.data]);
  const campaigns = useCampaignsFor(useMemo(() => campaignIdsOf(items), [items]));
  const groups = groupApplications(items);
  const withdraw = useWithdraw();
  const client = useQueryClient();
  const [confirming, setConfirming] = useState<Application | null>(null);
  const [reporting, setReporting] = useState<Campaign | null>(null);
  const [message, setMessage] = useState<{ tone: "info" | "error"; text: string } | null>(null);

  function confirmWithdraw() {
    if (!confirming) return;
    withdraw.mutate(confirming.id, {
      onSuccess: () => { setConfirming(null); setMessage({ tone: "info", text: t("applications.withdraw.done") }); },
      onError: (error) => {
        // A conflict means its status changed since the list loaded (a brand answered it): say so, and show where it stands now.
        const why = error instanceof ApiError && error.kind === "rate_limited" && error.retryAfter ? t("common.rateLimitedWait", { seconds: error.retryAfter })
          : error instanceof ApiError && error.kind === "conflict" && error.code !== "idempotency_key_in_flight" ? t("applications.withdraw.changed")
          : t(commonWordsKey(error));
        setMessage({ tone: "error", text: `${t("applications.withdraw.failed")} ${why}` });
        setConfirming(null);
        void mine.refetch();
      },
    });
  }

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-6 lg:gap-7">
      <Reveal>
        <header className="grid gap-4">
          <div className="grid gap-1.5">
            <h1 className="font-display text-[2rem] font-semibold leading-[1.1] tracking-tight sm:text-[2.5rem]">{t("applications.title")}</h1>
            <p className="max-w-[60ch] text-base text-muted">{t("applications.subtitle")}</p>
          </div>
          <DiscoverTabs current="mine" />
        </header>
      </Reveal>

      <div aria-live="polite">{message && <Notice tone={message.tone}><p>{message.text}</p></Notice>}</div>

      <Reveal index={1}>
        {mine.isPending ? (
          <div aria-busy="true" aria-label={t("common.loading")} className="grid gap-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-36 rounded-3xl" />)}</div>
        ) : mine.isError && mine.error instanceof ApiError && mine.error.code === "creator_profile_required" ? (
          // No profile yet: a state with a next step, not an error.
          <Card className="grid justify-items-start gap-4 p-6 sm:p-8">
            <h2 className="font-display text-2xl font-semibold tracking-tight">{t("applications.noProfile.title")}</h2>
            <p className="max-w-[52ch] text-[15px] leading-6 text-muted">{t("applications.noProfile.body")}</p>
            <ButtonLink href="/app/onboarding">{t("applications.noProfile.cta")}</ButtonLink>
          </Card>
        ) : mine.isError ? (
          <LoadError title={t("applications.errorTitle")} error={mine.error} onRetry={() => void mine.refetch()} />
        ) : items.length === 0 ? (
          <Card className="grid justify-items-start gap-5 p-6 sm:p-8">
            <Kolam />
            <div className="grid gap-2">
              <h2 className="font-display text-2xl font-semibold tracking-tight">{t("applications.empty.title")}</h2>
              <p className="max-w-[52ch] text-[15px] leading-6 text-muted">{t("applications.empty.body")}</p>
            </div>
            <ButtonLink href="/app/discover">{t("applications.empty.cta")}</ButtonLink>
          </Card>
        ) : (
          <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,21rem)]">
            <div className="grid gap-7">
              {groups.map((group) => (
                <section key={group.id} aria-labelledby={`group-${group.id}`} className="grid gap-3">
                  <h2 id={`group-${group.id}`} className="text-sm font-semibold uppercase tracking-[0.12em] text-muted">
                    {t(GROUP_TITLES[group.id])} <span className="tabular-nums">({group.items.length})</span>
                  </h2>
                  <ul className="grid gap-3">
                    {group.items.map((a) => <li key={a.id}><ApplicationRow application={a} campaign={campaigns.get(a.campaign_id)} onWithdraw={(x) => { setMessage(null); setConfirming(x); }} onReport={(c) => { setMessage(null); setReporting(c); }} /></li>)}
                  </ul>
                </section>
              ))}
            </div>
            <div className="lg:sticky lg:top-6"><FeedbackCard /></div>
          </div>
        )}
      </Reveal>

      {reporting && (
        <ReportBlockSheet open onClose={() => setReporting(null)} subject={{ kind: "brand", id: reporting.brand_id }} brandId={reporting.brand_id} brandName={reporting.brand_name}
          onBlocked={() => { setReporting(null); setMessage({ tone: "info", text: t("safety.block.done") }); void client.invalidateQueries({ queryKey: ["campaign"] }); }} />
      )}

      <Sheet open={confirming !== null} onClose={() => setConfirming(null)} title={t("applications.withdraw.title")} locked={withdraw.isPending}>
        <p className="text-[15px] leading-6 text-muted">{t("applications.withdraw.body")}</p>
        <div className="flex flex-wrap items-center gap-3">
          <Button loading={withdraw.isPending} onClick={confirmWithdraw}>{withdraw.isPending ? t("applications.withdraw.working") : t("applications.withdraw.confirm")}</Button>
          <Button variant="quiet" disabled={withdraw.isPending} onClick={() => setConfirming(null)}>{t("applications.withdraw.keep")}</Button>
        </div>
      </Sheet>
    </div>
  );
}
