"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { CampaignCard } from "@/components/brand-campaign/campaign-card";
import { Button, ButtonLink } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { Notice } from "@/components/ui/notice";
import { Reveal } from "@/components/ui/reveal";
import { Skeleton } from "@/components/ui/skeleton";
import { ongoing } from "@/lib/dashboard";
import { t } from "@/lib/app-messages";
import { useCampaignReports, useMyCampaigns } from "@/lib/queries";
import { useSession } from "@/lib/use-session";

// The brand's Campaigns (screen-plan B2, D-205): every campaign, grouped, each a card with how it is doing. Creators have Discover instead.
type Group = "all" | "ongoing" | "draft" | "cancelled";
const GROUPS: Group[] = ["all", "ongoing", "draft", "cancelled"];
const inGroup = (status: string, group: Group): boolean => group === "all" || (group === "ongoing" ? status === "open" || status === "closed" : status === group);

export default function CampaignsPage() {
  const router = useRouter();
  const session = useSession();
  const role = session.status === "signedIn" ? session.session.role : null;
  useEffect(() => { if (role === "creator") router.replace("/app/discover"); }, [role, router]);

  const campaigns = useMyCampaigns(role === "brand");
  const [group, setGroup] = useState<Group>("all");
  const all = useMemo(() => campaigns.data ?? [], [campaigns.data]);
  const withStats = useMemo(() => ongoing(all).map((c) => c.id), [all]);
  const { reports } = useCampaignReports(withStats);
  const byId = useMemo(() => new Map(reports.map((r) => [r.campaign_id, r])), [reports]);
  const shown = all.filter((c) => inGroup(c.status, group));

  return (
    <div className="grid gap-8 lg:gap-10">
      <Reveal>
        <header className="grid gap-5 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end">
          <div className="grid gap-2">
            <h1 className="type-title">{t("brandCampaigns.list.title")}</h1>
            <p className="type-lede">{t("brandCampaigns.list.subtitle")}</p>
          </div>
          <ButtonLink href="/app/campaigns/new">{t("brandCampaigns.list.new")}</ButtonLink>
        </header>
      </Reveal>

      {campaigns.isPending ? (
        <div aria-busy="true" aria-label={t("common.loading")} className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3"><Skeleton className="h-64 rounded-[2rem]" /><Skeleton className="h-64 rounded-[2rem]" /><Skeleton className="h-64 rounded-[2rem]" /></div>
      ) : campaigns.isError ? (
        <Notice tone="error" action={<Button variant="secondary" className="min-h-10 px-4 text-sm" onClick={() => void campaigns.refetch()}>{t("common.retry")}</Button>}><p>{t("brandCampaigns.list.error")}</p></Notice>
      ) : all.length === 0 ? (
        <Reveal index={1}>
          <section aria-labelledby="first-title" className="grid gap-8 rounded-[2rem] bg-surface p-7 shadow-card sm:p-12 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)] lg:items-center">
            <div className="grid content-start gap-4">
              <h2 id="first-title" className="type-title">{t("brandCampaigns.list.empty.title")}</h2>
              <p className="type-lede">{t("brandCampaigns.list.empty.body")}</p>
              <ButtonLink href="/app/campaigns/new" className="mt-2 justify-self-start">{t("brandCampaigns.list.new")}</ButtonLink>
            </div>
            <ol className="grid gap-3">
              {(["1", "2", "3", "4"] as const).map((n) => (
                <li key={n} className="flex items-center gap-4 rounded-3xl bg-sunk p-4 text-[16px] leading-6">
                  <span aria-hidden className="grid size-9 shrink-0 place-items-center rounded-full bg-lime text-[13px] font-semibold text-on-lime">{n}</span>
                  {t(`brandCampaigns.list.empty.steps.${n}`)}
                </li>
              ))}
            </ol>
          </section>
        </Reveal>
      ) : (
        <>
          <Reveal index={1}>
            <div role="group" aria-label={t("brandCampaigns.list.filters.label")} className="flex flex-wrap gap-2">
              {GROUPS.map((g) => <Chip key={g} pressed={group === g} onClick={() => setGroup(g)} count={all.filter((c) => inGroup(c.status, g)).length}>{t(`brandCampaigns.list.filters.${g}`)}</Chip>)}
            </div>
          </Reveal>
          {shown.length === 0 ? (
            <p className="text-[15px] text-muted">{t("brandCampaigns.list.none")}</p>
          ) : (
            <Reveal index={2}>
              <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                {shown.map((c) => <li key={c.id} className="grid"><CampaignCard campaign={c} report={byId.get(c.id)} /></li>)}
              </ul>
            </Reveal>
          )}
        </>
      )}
    </div>
  );
}
