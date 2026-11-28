import { Panel } from "@/components/dashboard/panel";
import { SplitBar } from "@/components/dashboard/split-bar";
import { Figure } from "@/components/dashboard/panel";
import { nicheLabel } from "@/lib/labels";
import { payLine, type Campaign } from "@/lib/campaigns";
import { applicantsOf, funnelOf, progressOf, STAGE_ORDER, stageCountsOf, type Report } from "@/lib/dashboard";
import { formatDate, formatPaise } from "@/lib/format";
import { t } from "@/lib/app-messages";

const FUNNEL_FILL = { submitted: "bg-line-strong", shortlisted: "bg-lime", accepted: "bg-accent", rejected: "bg-sunk" } as const;

function Funnel({ report }: { report: Report }) {
  const parts = funnelOf(report);
  const total = parts.reduce((n, p) => n + p.count, 0);
  return (
    <Panel title={t("brandCampaigns.view.funnel.title")}>
      {total === 0 ? (
        <p className="text-[15px] text-muted">{t("brandCampaigns.view.funnel.none")}</p>
      ) : (
        <>
          <div aria-hidden className="flex h-4 overflow-hidden rounded-full bg-sunk">
            {parts.filter((p) => p.count > 0).map((p) => <div key={p.status} className={`bar-grow h-full ${FUNNEL_FILL[p.status]}`} style={{ width: `${(p.count / total) * 100}%` }} />)}
          </div>
          <ul className="grid gap-2.5">
            {parts.map((p) => (
              <li key={p.status} className="flex items-center gap-3 text-[15px]">
                <span aria-hidden className={`size-3 rounded-full ${FUNNEL_FILL[p.status]} ${p.status === "rejected" ? "ring-1 ring-line-strong" : ""}`} />
                <span className="text-muted">{t(`brandCampaigns.view.funnel.${p.status}`)}</span>
                <span className="ml-auto font-semibold tabular-nums">{p.count}</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </Panel>
  );
}

function Stages({ report }: { report: Report }) {
  const counts = stageCountsOf(report);
  const any = counts.some((c) => c.count > 0);
  return (
    <Panel title={t("brandCampaigns.view.stages.title")}>
      {!any ? (
        <p className="text-[15px] text-muted">{t("brandCampaigns.view.stages.none")}</p>
      ) : (
        <ol className="grid grid-cols-5 gap-2">
          {STAGE_ORDER.map((stage, i) => {
            const count = counts[i]?.count ?? 0;
            return (
              <li key={stage} className="grid content-start justify-items-center gap-2 text-center">
                <span className={`grid size-12 place-items-center rounded-full text-[17px] font-semibold tabular-nums ${count > 0 ? "bg-accent text-on-accent" : "bg-sunk text-muted"}`}>{count}</span>
                <span className="text-[12px] leading-4 text-muted">{t(`deals.stage.${stage}.label`)}</span>
              </li>
            );
          })}
        </ol>
      )}
    </Panel>
  );
}

/** A campaign at a glance: the figures, where the applications and deals stand, the money, and the campaign's own terms. */
export function OverviewTab({ campaign: c, report }: { campaign: Campaign; report: Report }) {
  const progress = progressOf([report]);
  const pay = payLine(c);
  const totals = report.totals;
  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap gap-x-10 gap-y-5">
        <Figure label={t("brandCampaigns.view.figures.applications")} value={applicantsOf([report])} />
        <Figure label={t("brandCampaigns.view.figures.agreed")} value={totals.deals_agreed} />
        <Figure label={t("brandCampaigns.view.figures.finished")} value={totals.deals_finished} />
        <Figure label={t("brandCampaigns.view.figures.paid")} value={formatPaise(totals.confirmed_paise)} />
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <SplitBar label={t("dashboard.progress.applications")} share={progress.applications} fill="ink" />
        <SplitBar label={t("dashboard.progress.memos")} share={progress.memos} fill="lime" />
        <SplitBar label={t("dashboard.progress.work")} share={progress.work} fill="hatch" />
        <SplitBar label={t("dashboard.progress.paid")} share={progress.paid} fill="lime" />
      </div>
      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
        <div className="grid gap-4">
          <Funnel report={report} />
          <Stages report={report} />
        </div>
        <div className="grid gap-4">
          <Panel title={t("brandCampaigns.view.details.title")}>
            <dl className="grid gap-5 text-[15px] leading-6">
              <div className="grid gap-1"><dt className="text-[13px] text-muted">{t("campaign.pay")}</dt><dd className="font-semibold">{t(pay.key, pay.vars)}</dd></div>
              <div className="grid gap-1"><dt className="text-[13px] text-muted">{t("campaign.deliver")}</dt><dd className="whitespace-pre-line">{c.deliverables}</dd></div>
              <div className="grid gap-1"><dt className="text-[13px] text-muted">{t("campaign.about")}</dt><dd className="whitespace-pre-line">{c.description}</dd></div>
              <div className="grid grid-cols-2 gap-4">
                <div className="grid gap-1"><dt className="text-[13px] text-muted">{t("campaign.cities")}</dt><dd>{c.cities.length > 0 ? c.cities.join(", ") : t("campaign.anyCity")}</dd></div>
                <div className="grid gap-1"><dt className="text-[13px] text-muted">{t("campaign.niches")}</dt><dd>{c.niches.map(nicheLabel).join(", ")}</dd></div>
              </div>
              <div className="grid gap-1"><dt className="text-[13px] text-muted">{t("campaign.closes")}</dt><dd>{c.applications_close_on ? t("campaign.closesOn", { date: formatDate(c.applications_close_on) }) : t("campaign.noClose")}</dd></div>
            </dl>
          </Panel>
          <Panel title={t("brandCampaigns.view.money.title")} tone="sage">
            <dl className="grid gap-3 text-[15px]">
              {([["agreed", totals.agreed_value_paise], ["marked", totals.marked_paid_paise], ["confirmed", totals.confirmed_paise]] as const).map(([key, paise]) => (
                <div key={key} className="flex items-baseline justify-between gap-4"><dt className="text-muted">{t(`brandCampaigns.view.money.${key}`)}</dt><dd className="font-semibold tabular-nums">{formatPaise(paise)}</dd></div>
              ))}
            </dl>
            <p className="text-[13px] text-muted">{t("brandCampaigns.view.money.note")}</p>
          </Panel>
        </div>
      </div>
    </div>
  );
}
