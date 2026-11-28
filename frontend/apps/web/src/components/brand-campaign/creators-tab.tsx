"use client";

import Link from "next/link";
import { useState } from "react";
import { Avatar, Panel } from "@/components/dashboard/panel";
import { Chip } from "@/components/ui/chip";
import { Pill, type Tone } from "@/components/ui/pill";
import { formatCount, headlineOf, STAGE_ORDER, type Report, type ReportDeal } from "@/lib/dashboard";
import { formatDayMonth, formatPaise } from "@/lib/format";
import { t } from "@/lib/app-messages";

const PAY_TONE: Record<string, Tone> = { due: "neutral", late: "bad", unpaid: "bad", paid: "warn", unconfirmed: "warn", confirmed: "ok" };

/** Every collaboration on the campaign: who, where it stands, the fee, the dates, the payment, and the post's headline number, which
 *  opens the post. Filtered by stage with the chips. */
export function CreatorsTab({ report, onOpen }: { report: Report; onOpen: (deal: ReportDeal) => void }) {
  const [stage, setStage] = useState<string>("all");
  const deals = report.deals;
  const shown = stage === "all" ? deals : deals.filter((d) => d.stage === stage);
  return (
    <Panel title={t("brandCampaigns.view.creators.title")}>
      {deals.length === 0 ? (
        <p className="text-[15px] leading-6 text-muted">{t("brandCampaigns.view.creators.empty")}</p>
      ) : (
        <>
          <div role="group" aria-label={t("brandCampaigns.view.creators.title")} className="flex flex-wrap gap-2">
            <Chip pressed={stage === "all"} onClick={() => setStage("all")} count={deals.length}>{t("brandCampaigns.view.creators.all")}</Chip>
            {STAGE_ORDER.filter((s) => deals.some((d) => d.stage === s)).map((s) => (
              <Chip key={s} pressed={stage === s} onClick={() => setStage(s)} count={deals.filter((d) => d.stage === s).length}>{t(`deals.stage.${s}.label`)}</Chip>
            ))}
          </div>
          {shown.length === 0 ? (
            <p className="text-[15px] text-muted">{t("brandCampaigns.view.creators.none")}</p>
          ) : (
            <ul className="grid">
              {shown.map((d) => {
                const head = headlineOf(d.results.numbers);
                const due = d.work_due_on ?? d.content_due_on;
                return (
                  <li key={d.deal_memo_id} className="grid gap-3 border-t border-line py-4 first:border-t-0 md:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_minmax(0,1fr)_auto] md:items-center md:gap-5">
                    <div className="flex min-w-0 items-center gap-3.5">
                      <Avatar name={d.creator.display_name} />
                      <div className="grid min-w-0 gap-0.5">
                        <p className="truncate text-[15px] font-semibold">{d.creator.display_name}</p>
                        <p className="truncate text-sm text-muted">@{d.creator.handle}</p>
                      </div>
                    </div>
                    <div className="grid gap-1.5">
                      <div className="flex flex-wrap items-center gap-2">
                        <Pill tone="neutral">{t(`deals.stage.${d.stage as "agreed"}.label`)}</Pill>
                        {d.payment_state && <Pill tone={PAY_TONE[d.payment_state] ?? "neutral"}>{t(`brandCampaigns.view.pay.${d.payment_state as "due"}`)}</Pill>}
                      </div>
                      <p className="text-sm text-muted">{d.fee_amount_paise != null ? formatPaise(d.fee_amount_paise) : t("brandCampaigns.view.creators.barter")}{due ? ` · ${t("brandCampaigns.view.creators.due")} ${formatDayMonth(due)}` : ""}</p>
                    </div>
                    <div>
                      {head ? (
                        <button type="button" onClick={() => onOpen(d)} className="t-base group inline-flex min-h-11 items-center gap-2 rounded-full bg-sunk px-4 text-[14px] font-semibold hover:bg-lime hover:text-on-lime">
                          <span className="tabular-nums">{formatCount(head.value)}</span><span className="font-medium text-muted group-hover:text-on-lime">{t(head.key === "views" ? "dashboard.performance.views" : "dashboard.performance.reach")}</span>
                        </button>
                      ) : (
                        <span className="text-sm text-muted">{t("brandCampaigns.view.creators.noPost")}</span>
                      )}
                    </div>
                    <Link href={`/app/deals/${d.deal_memo_id}`} className="t-base inline-flex min-h-11 items-center justify-self-start rounded-full px-4 text-[14px] font-semibold text-ink underline-offset-4 hover:underline md:justify-self-end">{t("brandCampaigns.view.creators.open")}</Link>
                  </li>
                );
              })}
            </ul>
          )}
        </>
      )}
    </Panel>
  );
}
