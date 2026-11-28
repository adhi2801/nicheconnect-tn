"use client";

import { useState } from "react";
import { Panel } from "@/components/dashboard/panel";
import { addNumbers, averageEngagement, engagementOf, formatCount, formatPercent, METRICS, postsOf, rankPosts, type Metric, type Report, type ReportDeal } from "@/lib/dashboard";
import { t } from "@/lib/app-messages";

/**
 * The reels' performance as a brand can explore it: pick a figure and the posts rank by it, as bars that grow into place; the figure's
 * total is on its button; the average engagement is calculated and says so; selecting a post opens it in full. Everything here is what
 * the creators' screenshots said (D-070), and the page says that first.
 */
export function InsightsTab({ report, onOpen }: { report: Report; onOpen: (deal: ReportDeal) => void }) {
  const [metric, setMetric] = useState<Metric>("views");
  const posts = postsOf(report);
  const totals = addNumbers(posts.map((p) => p.numbers));
  const ranked = rankPosts(posts, metric);
  const max = Math.max(1, ...ranked.map((r) => r.value ?? 0));
  const average = averageEngagement(posts);
  const best = posts.map((p) => ({ p, e: engagementOf(p.numbers) })).filter((x) => x.e !== null).sort((a, b) => (b.e?.rate ?? 0) - (a.e?.rate ?? 0))[0];
  const open = (dealId: string) => { const deal = report.deals.find((d) => d.deal_memo_id === dealId); if (deal) onOpen(deal); };

  if (posts.length === 0) {
    return <Panel title={t("brandCampaigns.view.insights.title")}><p className="text-[15px] leading-6 text-muted">{t("dashboard.performance.empty")}</p></Panel>;
  }
  return (
    <div className="grid gap-4">
      <p className="text-[13px] text-muted">{t("dashboard.performance.source")} {t(posts.length === 1 ? "dashboard.performance.summary.one" : "dashboard.performance.summary.other", { count: posts.length, readings: posts.reduce((n, p) => n + p.readings, 0) })}.</p>

      <div role="group" aria-label={t("brandCampaigns.view.insights.metric")} className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {METRICS.map((m) => {
          const on = metric === m;
          const total = totals[m];
          return (
            <button key={m} type="button" aria-pressed={on} onClick={() => setMetric(m)} className={`t-base grid gap-1.5 rounded-3xl p-4 text-left active:scale-[0.98] ${on ? "bg-accent text-on-accent" : "bg-surface shadow-card hover:shadow-[0_0_0_1px_var(--c-line-strong)]"}`}>
              <span className={`text-[13px] ${on ? "text-on-accent/75" : "text-muted"}`}>{t(`dashboard.performance.${m}`)}</span>
              <span className={total === null ? "text-[13px]" : "type-figure text-[2rem]"}>{total === null ? t("dashboard.performance.notShown") : formatCount(total)}</span>
            </button>
          );
        })}
      </div>

      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,8fr)_minmax(0,4fr)]">
        <Panel title={t("brandCampaigns.view.insights.ranked", { metric: t(`dashboard.performance.${metric}`) })}>
          <ul className="grid gap-2">
            {ranked.map(({ post, value }, i) => {
              const e = engagementOf(post.numbers);
              return (
                <li key={post.dealId}>
                  <button type="button" onClick={() => open(post.dealId)} aria-label={`${post.creator}, ${value === null ? t("brandCampaigns.view.insights.noValue") : formatCount(value)} ${t(`dashboard.performance.${metric}`)}`} className="t-base group grid w-full grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-4 rounded-3xl p-3 text-left hover:bg-sunk">
                    <span aria-hidden className="grid size-9 place-items-center rounded-full bg-sunk text-[13px] font-semibold tabular-nums group-hover:bg-surface">{i + 1}</span>
                    <span className="grid min-w-0 gap-2">
                      <span className="flex items-baseline justify-between gap-3">
                        <span className="truncate text-[15px] font-semibold">{post.creator}</span>
                        <span className={value === null ? "text-[13px] text-muted" : "text-[15px] font-semibold tabular-nums"}>{value === null ? t("brandCampaigns.view.insights.noValue") : formatCount(value)}</span>
                      </span>
                      <span aria-hidden className="h-3 overflow-hidden rounded-full bg-sunk group-hover:bg-surface">
                        {value !== null && <span key={metric} className="bar-grow block h-full rounded-full bg-accent" style={{ width: `${Math.max((value / max) * 100, value > 0 ? 2 : 0)}%` }} />}
                      </span>
                    </span>
                    <span className="hidden min-w-[4.5rem] justify-items-end gap-0.5 text-right sm:grid">
                      <span className="text-[15px] font-semibold tabular-nums">{e ? (e.partial ? `≥ ${formatPercent(e.rate)}` : formatPercent(e.rate)) : "–"}</span>
                      <span className="text-[11px] text-muted">{t("brandCampaigns.view.insights.engagement")}</span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
          <p className="text-[13px] text-muted">{t("brandCampaigns.view.insights.hint")}</p>
        </Panel>

        <Panel title={t("brandCampaigns.view.insights.average")} tone="sage">
          {average ? (
            <>
              <p className="type-figure text-[3.5rem]">{average.partial ? t("brandCampaigns.view.insights.atLeast", { rate: formatPercent(average.rate) }) : formatPercent(average.rate)}</p>
              <p className="text-[15px] text-muted">{t("brandCampaigns.view.insights.averageOf", { count: average.count })}</p>
              {best?.e && <p className="rounded-2xl bg-surface p-4 text-[15px]">{t("brandCampaigns.view.insights.top", { name: best.p.creator })} <span className="font-semibold tabular-nums">{formatPercent(best.e.rate)}</span></p>}
            </>
          ) : (
            <p className="text-[15px] leading-6">{t("brandCampaigns.view.insights.notEnough")}</p>
          )}
          <p className="text-[13px] leading-5 text-muted">{t("brandCampaigns.view.insights.engagementNote")}</p>
        </Panel>
      </div>
    </div>
  );
}
