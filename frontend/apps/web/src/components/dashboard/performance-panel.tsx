import { Skeleton } from "@/components/ui/skeleton";
import { formatCount, headlineOf, NUMBER_KEYS, performanceOf, postsOf, type Report } from "@/lib/dashboard";
import { t } from "@/lib/app-messages";
import { DotBars } from "./dot-bars";
import { Panel } from "./panel";

const TOP = 5;
const SHOWN_KEYS = NUMBER_KEYS.filter((k) => k !== "impressions"); // impressions are rarely shown on a screenshot: kept out of the grid, never hidden from a post

/**
 * How the posts did, from what the creators' screenshots said (D-070). It says so, always; a number no screenshot showed says "Not
 * shown" and is never 0; a figure shown rounded on screen is marked; readings a creator called wrong are left out and said so.
 * There is no daily graph: the backend has no time series (frontend/design/dashboard-plan.md section 2).
 */
export function PerformancePanel({ reports, loading, failed }: { reports: Report[]; loading: boolean; failed: number }) {
  const total = performanceOf(reports);
  const posts = reports.flatMap(postsOf).map((p) => ({ p, head: headlineOf(p.numbers) })).sort((a, b) => (b.head?.value ?? -1) - (a.head?.value ?? -1)).slice(0, TOP);
  const wrong = reports.flatMap(postsOf).reduce((n, p) => n + p.markedWrong, 0);
  return (
    <Panel title={t("dashboard.performance.title")} tone="sage">
      <p className="-mt-3 text-[13px] text-muted">{t("dashboard.performance.source")}</p>
      {loading ? (
        <div aria-busy="true" className="grid gap-3"><Skeleton className="h-16" /><Skeleton className="h-24" /></div>
      ) : total.posts === 0 ? (
        <p className="text-[15px] leading-6">{failed > 0 ? t("dashboard.performance.error") : t("dashboard.performance.empty")}</p>
      ) : (
        <>
          <p className="text-sm font-medium">{t(total.posts === 1 ? "dashboard.performance.summary.one" : "dashboard.performance.summary.other", { count: total.posts, readings: total.readings })}</p>
          <dl className="grid grid-cols-3 gap-x-4 gap-y-5">
            {SHOWN_KEYS.map((key) => {
              const value = total.numbers[key];
              return (
                <div key={key} className="grid gap-1">
                  <dt className="text-[13px] text-muted">{t(`dashboard.performance.${key}`)}</dt>
                  <dd className={value === null ? "text-[13px] text-muted" : "type-figure text-[1.75rem] sm:text-[2rem]"}>{value === null ? t("dashboard.performance.notShown") : formatCount(value)}</dd>
                </div>
              );
            })}
          </dl>
          <div className="grid grid-cols-[auto_minmax(0,1fr)] items-end gap-5 rounded-3xl bg-surface p-4">
            <DotBars values={posts.map((x) => x.head?.value ?? null)} />
            <ul className="grid gap-2.5" aria-label={t("dashboard.performance.top")}>
              {posts.map(({ p, head }) => (
                <li key={p.dealId} className="grid grid-cols-[minmax(0,1fr)_auto] items-baseline gap-3 text-sm">
                  <span className="truncate font-medium">{p.creator}</span>
                  <span className="tabular-nums text-muted">{head ? t(head.key === "views" ? "dashboard.performance.viewsOf" : "dashboard.performance.reachOf", { value: formatCount(head.value) }) : t("dashboard.performance.noHeadline")}</span>
                </li>
              ))}
            </ul>
          </div>
          {total.approximate && <p className="text-[13px] text-muted">{t("dashboard.performance.approximate")}</p>}
          {wrong > 0 && <p className="text-[13px] text-muted">{t("dashboard.performance.markedWrong")}</p>}
        </>
      )}
    </Panel>
  );
}
