"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { Notice } from "@/components/ui/notice";
import { Pill } from "@/components/ui/pill";
import { Skeleton } from "@/components/ui/skeleton";
import { ChevronLeftIcon } from "@/components/ui/icons";
import { payLine, type Campaign } from "@/lib/campaigns";
import type { Report, ReportDeal } from "@/lib/dashboard";
import { formatDate } from "@/lib/format";
import { t } from "@/lib/app-messages";
import { CreatorsTab } from "./creators-tab";
import { InsightsTab } from "./insights-tab";
import { OverviewTab } from "./overview-tab";
import { PostSheet } from "./post-sheet";

const SECTIONS = ["overview", "creators", "insights"] as const;
type Section = (typeof SECTIONS)[number];
const TONE = { open: "ok", closed: "neutral", draft: "neutral", cancelled: "bad" } as const;

/** A brand's campaign: its status and terms at the top, three sections under (the address remembers which: ?tab=), and a post opening
 *  in full over either of the last two. */
export function CampaignView({ campaign: c, report, state }: { campaign: Campaign; report: Report | undefined; state: "loading" | "error" | "ready" }) {
  const params = useSearchParams();
  const raw = params.get("tab");
  const section: Section = SECTIONS.includes(raw as Section) ? (raw as Section) : "overview";
  const [opened, setOpened] = useState<ReportDeal | null>(null);
  const pay = payLine(c);
  const status = c.status as keyof typeof TONE;
  return (
    <div className="grid gap-8 lg:gap-10">
      <header className="grid gap-5">
        <Link href="/app/campaigns" className="t-base inline-flex min-h-11 items-center gap-1.5 justify-self-start rounded-full pr-3 text-sm font-semibold text-muted hover:text-ink">
          <ChevronLeftIcon width={18} height={18} aria-hidden />{t("brandCampaigns.view.back")}
        </Link>
        <div className="grid gap-3">
          <div className="flex flex-wrap items-center gap-3">
            <Pill tone={TONE[status] ?? "neutral"}>{t(`brandCampaigns.view.status.${status}` as "brandCampaigns.view.status.open")}</Pill>
            <p className="text-[15px] text-muted">{t(pay.key, pay.vars)}{c.applications_close_on ? ` · ${t("campaign.closesOn", { date: formatDate(c.applications_close_on) })}` : ""}</p>
          </div>
          <h1 className="type-title">{c.title}</h1>
        </div>
        <nav aria-label={t("brandCampaigns.view.nav")} className="flex flex-wrap gap-2">
          {SECTIONS.map((s) => (
            <Link key={s} href={`/app/campaigns/${c.id}?tab=${s}`} replace scroll={false} aria-current={section === s ? "page" : undefined} className={`t-base inline-flex min-h-11 items-center rounded-full px-5 text-[14px] font-medium ${section === s ? "bg-accent text-on-accent" : "bg-surface text-ink shadow-[0_0_0_1px_var(--c-line)] hover:bg-sunk"}`}>
              {t(`brandCampaigns.view.sections.${s}`)}
            </Link>
          ))}
        </nav>
      </header>

      {state === "loading" ? (
        <div aria-busy="true" aria-label={t("common.loading")} className="grid gap-4"><Skeleton className="h-24 rounded-[2rem]" /><Skeleton className="h-72 rounded-[2rem]" /></div>
      ) : state === "error" || !report ? (
        <Notice tone="error"><p>{t("brandCampaigns.view.reportError")}</p></Notice>
      ) : section === "overview" ? (
        <OverviewTab campaign={c} report={report} />
      ) : section === "creators" ? (
        <CreatorsTab report={report} onOpen={setOpened} />
      ) : (
        <InsightsTab report={report} onOpen={setOpened} />
      )}

      <PostSheet deal={opened} onClose={() => setOpened(null)} />
    </div>
  );
}
