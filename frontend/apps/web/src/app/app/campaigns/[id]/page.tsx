"use client";

import { Suspense, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { CampaignView } from "@/components/brand-campaign/campaign-view";
import { ButtonLink } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { LoadError } from "@/components/ui/load-error";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/errors";
import { t } from "@/lib/app-messages";
import { useCampaign, useCampaignReports } from "@/lib/queries";
import { useSession } from "@/lib/use-session";

// A brand's campaign (D-205): the campaign itself and its report, two calls in parallel. A creator is sent to the campaign as Discover shows it.
function BrandCampaign({ id }: { id: string }) {
  const campaign = useCampaign(id);
  const { reports, pending, failed } = useCampaignReports([id]);
  if (campaign.isPending) {
    return <div aria-busy="true" aria-label={t("common.loading")} className="grid gap-5"><Skeleton className="h-6 w-40" /><Skeleton className="h-14 w-3/4" /><Skeleton className="h-80 rounded-[2rem]" /></div>;
  }
  if (campaign.isError) {
    const kind = campaign.error instanceof ApiError ? campaign.error.kind : "unknown";
    if (kind === "not_found" || kind === "withheld") {
      return (
        <Card className="mx-auto grid max-w-lg gap-4 p-8">
          <h1 className="font-display text-2xl font-semibold tracking-tight">{t("brandCampaigns.view.notFound.title")}</h1>
          <p className="text-[15px] leading-6 text-muted">{t("brandCampaigns.view.notFound.body")}</p>
          <ButtonLink href="/app/campaigns" variant="secondary" className="justify-self-start">{t("brandCampaigns.view.back")}</ButtonLink>
        </Card>
      );
    }
    return <LoadError title={t("campaign.errorTitle")} error={campaign.error} onRetry={() => void campaign.refetch()} />;
  }
  return <CampaignView campaign={campaign.data} report={reports[0]} state={pending ? "loading" : failed > 0 ? "error" : "ready"} />;
}

export default function CampaignPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const session = useSession();
  const role = session.status === "signedIn" ? session.session.role : null;
  useEffect(() => { if (role === "creator") router.replace(`/app/discover/${id}`); }, [role, id, router]);
  if (role !== "brand") return <Skeleton className="h-80 rounded-[2rem]" />;
  return <Suspense fallback={<Skeleton className="h-80 rounded-[2rem]" />}><BrandCampaign id={id} /></Suspense>;
}
