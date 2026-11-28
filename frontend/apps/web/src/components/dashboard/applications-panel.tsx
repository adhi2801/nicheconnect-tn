"use client";

import Link from "next/link";
import { ButtonLink } from "@/components/ui/button";
import { Pill } from "@/components/ui/pill";
import { Skeleton } from "@/components/ui/skeleton";
import { statusTone, statusWords, type Application } from "@/lib/applications";
import { formatDate, indiaDay } from "@/lib/format";
import { t } from "@/lib/app-messages";
import { useCampaignsFor, useMyApplications } from "@/lib/queries";
import { Panel } from "./panel";

const SHOWN = 4;
const newest = (a: Application, b: Application) => (a.status_changed_at < b.status_changed_at ? 1 : a.status_changed_at > b.status_changed_at ? -1 : 0);

/** The creator's four latest applications and where each stands. Campaign names come from the campaign reads My applications shares
 *  (a stopgap until request R7, so at most four reads here). */
export function ApplicationsPanel() {
  const applications = useMyApplications();
  const latest = [...(applications.data ?? [])].sort(newest).slice(0, SHOWN);
  const campaigns = useCampaignsFor(latest.map((a) => a.campaign_id));
  return (
    <Panel title={t("dashboard.applications.title")} action={{ href: "/app/applications", label: t("dashboard.applications.see") }}>
      {applications.isPending ? (
        <div aria-busy="true" className="grid gap-3"><Skeleton className="h-14" /><Skeleton className="h-14" /></div>
      ) : applications.isError ? (
        <p className="text-[15px] text-muted">{t("dashboard.applications.error")}</p>
      ) : latest.length === 0 ? (
        <div className="grid justify-items-start gap-4">
          <p className="text-[15px] leading-6 text-muted">{t("dashboard.applications.empty")}</p>
          <ButtonLink href="/app/discover" variant="secondary">{t("dashboard.applications.browse")}</ButtonLink>
        </div>
      ) : (
        <ul className="grid gap-1">
          {latest.map((a) => {
            const campaign = campaigns.get(a.campaign_id)?.data;
            return (
              <li key={a.id} className="border-t border-line first:border-t-0">
                <Link href="/app/applications" className="t-base grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 py-3.5 hover:opacity-80">
                  <span className="grid min-w-0 gap-0.5">
                    <span className="truncate text-[15px] font-semibold">{campaign ? campaign.title : <Skeleton className="h-5 w-40" />}</span>
                    <span className="truncate text-sm text-muted">{campaign ? `${campaign.brand_name} · ` : ""}{t("dashboard.applications.status", { date: formatDate(indiaDay(a.status_changed_at)) })}</span>
                  </span>
                  <Pill tone={statusTone(a.status)}>{t(statusWords(a.status))}</Pill>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </Panel>
  );
}
