"use client";

import Link from "next/link";
import { Notice } from "@/components/ui/notice";
import { Sheet } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { AlertIcon, CheckIcon, InfoIcon } from "@/components/ui/icons";
import { engagementOf, formatCount, formatPercent, type ReportDeal } from "@/lib/dashboard";
import { t } from "@/lib/app-messages";
import { usePostEvidence } from "@/lib/queries";

const SHOWN = ["views", "reach", "impressions", "likes", "comments", "saves", "shares"] as const;

function Check({ label, value }: { label: string; value: boolean | null | undefined }) {
  const ok = value === true, bad = value === false;
  return (
    <li className="flex items-center gap-3 text-[15px] leading-6">
      <span aria-hidden className={`grid size-6 shrink-0 place-items-center rounded-full ${ok ? "bg-lime text-on-lime" : bad ? "bg-bad-soft text-bad" : "bg-sunk text-muted"}`}>
        {ok ? <CheckIcon width={14} height={14} strokeWidth={3} /> : bad ? <AlertIcon width={14} height={14} /> : <InfoIcon width={14} height={14} />}
      </span>
      <span className="grow">{label}</span>
      <span className={`text-[13px] font-semibold ${bad ? "text-bad" : "text-muted"}`}>{t(ok ? "brandCampaigns.view.post.ok" : bad ? "brandCampaigns.view.post.bad" : "brandCampaigns.view.post.unknown")}</span>
    </li>
  );
}

function Body({ deal }: { deal: ReportDeal }) {
  const evidence = usePostEvidence(deal.deal_memo_id);
  const n = deal.results.numbers;
  const engagement = engagementOf(n);
  const files = evidence.data?.files ?? [];
  const readings = files.filter((f) => f.reading && f.reading.status !== "no_numbers");
  return (
    <div className="grid gap-6">
      <section aria-labelledby="post-numbers" className="grid gap-3">
        <h3 id="post-numbers" className="text-[15px] font-medium">{t("brandCampaigns.view.post.numbers")}</h3>
        <p className="-mt-1 text-[13px] text-muted">{t("dashboard.performance.source")}</p>
        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {SHOWN.map((key) => (
            <div key={key} className="grid gap-1 rounded-2xl bg-sunk p-3.5">
              <dt className="text-[12px] text-muted">{key === "impressions" ? t("brandCampaigns.view.post.impressions") : t(`dashboard.performance.${key}`)}</dt>
              <dd className={n[key] === null ? "text-[13px] text-muted" : "type-figure text-[1.5rem]"}>{n[key] === null ? t("dashboard.performance.notShown") : formatCount(n[key])}</dd>
            </div>
          ))}
          <div className="grid gap-1 rounded-2xl bg-lime p-3.5 text-on-lime">
            <dt className="text-[12px]">{t("brandCampaigns.view.insights.engagement")}</dt>
            <dd className={engagement ? "type-figure text-[1.5rem]" : "text-[13px]"}>{engagement ? (engagement.partial ? t("brandCampaigns.view.insights.atLeast", { rate: formatPercent(engagement.rate) }) : formatPercent(engagement.rate)) : t("brandCampaigns.view.insights.notEnough")}</dd>
          </div>
        </dl>
        {deal.results.includes_abbreviated && <p className="text-[13px] text-muted">{t("dashboard.performance.approximate")}</p>}
        {deal.results.readings_marked_wrong > 0 && <p className="text-[13px] text-muted">{t("brandCampaigns.view.post.wrong")}</p>}
      </section>

      <section aria-labelledby="post-evidence" className="grid gap-3" aria-busy={evidence.isPending}>
        <h3 id="post-evidence" className="text-[15px] font-medium">{t("brandCampaigns.view.post.checks")}</h3>
        {evidence.isPending ? (
          <div aria-label={t("brandCampaigns.view.post.loading")} className="grid gap-3"><Skeleton className="h-6" /><Skeleton className="h-6" /><Skeleton className="h-40 rounded-3xl" /></div>
        ) : evidence.isError ? (
          <Notice tone="error"><p>{t("brandCampaigns.view.post.error")}</p></Notice>
        ) : readings.length === 0 ? (
          <p className="text-[15px] text-muted">{t("brandCampaigns.view.post.none")}</p>
        ) : (
          readings.map((f) => (
            <div key={f.id} className="grid gap-4">
              <ul className="grid gap-2.5">
                <Check label={t("brandCampaigns.view.post.handle")} value={f.reading?.checks.handle_matches} />
                <Check label={t("brandCampaigns.view.post.date")} value={f.reading?.checks.date_within_deal} />
                <Check label={t("brandCampaigns.view.post.consistent")} value={f.reading?.checks.numbers_consistent} />
              </ul>
              {typeof f.reading?.views_against_stated === "number" && <p className="text-[14px] text-muted">{t("brandCampaigns.view.post.vsStated", { ratio: f.reading.views_against_stated.toFixed(1) })}</p>}
              {f.url && (
                <figure className="grid gap-2">
                  {/* A short-lived link to the cleaned copy: shown, never stored (the API says so). */}
                  {/* eslint-disable-next-line @next/next/no-img-element -- a signed, expiring image link; there is nothing to optimise */}
                  <img src={f.url} alt={t("brandCampaigns.view.post.alt")} className="max-h-[26rem] w-full rounded-3xl bg-sunk object-contain" />
                  <figcaption className="text-[13px] text-muted">{t("brandCampaigns.view.post.screenshot")}</figcaption>
                </figure>
              )}
            </div>
          ))
        )}
      </section>

      <Link href={`/app/deals/${deal.deal_memo_id}`} className="t-base inline-flex min-h-12 items-center justify-center justify-self-start rounded-full bg-accent px-6 text-[15px] font-semibold text-on-accent hover:bg-accent-hover">{t("brandCampaigns.view.post.openDeal")}</Link>
    </div>
  );
}

/** One post in full: every number its screenshot showed, the engagement calculated from them, what the backend checked, and the
 *  screenshot itself. The evidence is read only once the sheet is opened. */
export function PostSheet({ deal, onClose }: { deal: ReportDeal | null; onClose: () => void }) {
  return (
    <Sheet open={!!deal} onClose={onClose} title={t("brandCampaigns.view.post.title", { name: deal?.creator.display_name ?? "" })}>
      {deal && <Body deal={deal} />}
    </Sheet>
  );
}
