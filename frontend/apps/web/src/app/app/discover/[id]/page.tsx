"use client";

import { useParams } from "next/navigation";
import { ButtonLink } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { LoadError } from "@/components/ui/load-error";
import { Skeleton } from "@/components/ui/skeleton";
import { CampaignDetail } from "@/components/campaign/campaign-detail";
import { ApiError } from "@/lib/errors";
import { t } from "@/lib/messages";
import { useCampaign, useMyApplications } from "@/lib/queries";

// One campaign (screen-plan C3), opened from Discover. Its calls: the campaign, the brand's record (after the campaign names the brand),
// and the creator's applications, shared with Discover and usually already cached. Request R9 asks the backend to put "your
// application" on the campaign itself, so this needs two calls on a cold start too.
export default function CampaignPage() {
  const { id } = useParams<{ id: string }>();
  const campaign = useCampaign(id);
  const mine = useMyApplications();

  if (campaign.isPending) {
    return (
      <div aria-busy="true" aria-label={t("common.loading")} className="grid gap-5">
        <Skeleton className="h-6 w-40" /><Skeleton className="h-12 w-3/4" />
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_22rem]"><Skeleton className="h-96 rounded-[1.75rem]" /><Skeleton className="h-56 rounded-[1.75rem]" /></div>
      </div>
    );
  }
  if (campaign.isError) {
    const kind = campaign.error instanceof ApiError ? campaign.error.kind : "unknown";
    if (kind === "not_found" || kind === "withheld") {
      const which = kind === "withheld" ? "withheld" : "notFound";
      return (
        <Card className="mx-auto grid max-w-lg gap-4 p-8">
          <h1 className="font-display text-2xl font-semibold tracking-tight">{t(`campaign.${which}.title`)}</h1>
          <p className="text-[15px] leading-6 text-muted">{t(`campaign.${which}.body`)}</p>
          <ButtonLink href="/app/discover" variant="secondary" className="justify-self-start">{t("campaign.notFound.cta")}</ButtonLink>
        </Card>
      );
    }
    return <LoadError title={t("campaign.errorTitle")} error={campaign.error} onRetry={() => void campaign.refetch()} />;
  }
  // The newest application to this campaign, if any. While the list loads, the action waits rather than offer Apply to someone who
  // already applied; if the list fails, Apply shows and the backend's already_applied answer covers it.
  const yours = (mine.data ?? []).filter((a) => a.campaign_id === id).sort((a, b) => b.created_at.localeCompare(a.created_at))[0];
  return <CampaignDetail campaign={campaign.data} mine={yours} checking={mine.isPending} />;
}
