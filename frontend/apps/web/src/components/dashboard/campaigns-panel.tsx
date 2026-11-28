import Link from "next/link";
import { ButtonLink } from "@/components/ui/button";
import { Pill } from "@/components/ui/pill";
import { Skeleton } from "@/components/ui/skeleton";
import type { Report } from "@/lib/dashboard";
import { applicantsOf } from "@/lib/dashboard";
import { t } from "@/lib/app-messages";
import { Panel } from "./panel";

type Item = { id: string; title: string; status: string };

/** The brand's ongoing campaigns, each with how many applied and how many deals have finished, read from its report. */
export function CampaignsPanel({ campaigns, reports, loading, failedLoad, failedReports }: { campaigns: Item[]; reports: Map<string, Report>; loading: boolean; failedLoad: boolean; failedReports: number }) {
  return (
    <Panel title={t("dashboard.campaigns.title")} action={{ href: "/app/campaigns", label: t("dashboard.campaigns.all") }}>
      {loading ? (
        <div aria-busy="true" className="grid gap-3"><Skeleton className="h-14" /><Skeleton className="h-14" /></div>
      ) : failedLoad ? (
        <p className="text-[15px] text-muted">{t("dashboard.campaigns.error")}</p>
      ) : campaigns.length === 0 ? (
        <div className="grid justify-items-start gap-4">
          <p className="text-[15px] leading-6 text-muted">{t("dashboard.campaigns.empty")}</p>
          <ButtonLink href="/app/campaigns/new">{t("dashboard.campaigns.start")}</ButtonLink>
        </div>
      ) : (
        <>
          <ul className="grid">
            {campaigns.map((c) => {
              const report = reports.get(c.id);
              return (
                <li key={c.id} className="border-t border-line first:border-t-0">
                  <Link href={`/app/campaigns/${c.id}`} className="t-base grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 py-3.5 hover:opacity-80">
                    <span className="grid min-w-0 gap-0.5">
                      <span className="truncate text-[15px] font-semibold">{c.title}</span>
                      <span className="truncate text-sm text-muted">
                        {report
                          ? `${t("dashboard.campaigns.applied", { count: applicantsOf([report]) })} · ${report.totals.deals_agreed > 0 ? t("dashboard.campaigns.deals", { done: report.totals.deals_finished, of: report.totals.deals_agreed }) : t("dashboard.campaigns.noDeals")}`
                          : " "}
                      </span>
                    </span>
                    <Pill tone={c.status === "open" ? "ok" : "neutral"}>{t(c.status === "open" ? "dashboard.campaigns.status.open" : "dashboard.campaigns.status.closed")}</Pill>
                  </Link>
                </li>
              );
            })}
          </ul>
          {failedReports > 0 && <p className="text-sm text-muted">{t("dashboard.campaigns.partial", { count: failedReports })}</p>}
        </>
      )}
    </Panel>
  );
}
