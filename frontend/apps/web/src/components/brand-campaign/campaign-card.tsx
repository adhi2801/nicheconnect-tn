import Link from "next/link";
import { Pill } from "@/components/ui/pill";
import { payLine, type Campaign } from "@/lib/campaigns";
import { percent, share, type Report } from "@/lib/dashboard";
import { formatDayMonth } from "@/lib/format";
import { t } from "@/lib/app-messages";

const STATUS_TONE = { open: "ok", closed: "neutral", draft: "neutral", cancelled: "bad" } as const;

/** One campaign as a card the whole of which is a link: its status, what it pays, when it closes, how many applied and how its deals are
 *  going (from its report, when it has one). It lifts a little under the pointer, as the reference's cards do. */
export function CampaignCard({ campaign: c, report }: { campaign: Campaign; report: Report | undefined }) {
  const pay = payLine(c);
  const applied = report ? report.totals.applications.submitted + report.totals.applications.shortlisted + report.totals.applications.accepted + report.totals.applications.rejected : c.applicant_count;
  const agreed = report?.totals.deals_agreed ?? 0;
  const finished = percent(share(report?.totals.deals_finished ?? 0, agreed));
  const status = c.status as keyof typeof STATUS_TONE;
  return (
    <Link href={`/app/campaigns/${c.id}`} className="t-base group grid content-between gap-6 rounded-[2rem] bg-surface p-6 shadow-card hover:-translate-y-0.5 hover:shadow-[0_0_0_1px_var(--c-line-strong)]">
      <div className="grid gap-3">
        <div className="flex items-start justify-between gap-3">
          <Pill tone={STATUS_TONE[status] ?? "neutral"}>{t(`brandCampaigns.view.status.${status}` as "brandCampaigns.view.status.open")}</Pill>
          <span className="text-[13px] text-muted">{c.applications_close_on ? t("brandCampaigns.list.card.closes", { date: formatDayMonth(c.applications_close_on) }) : t("brandCampaigns.list.card.noClose")}</span>
        </div>
        <h2 className="type-subtitle line-clamp-2">{c.title}</h2>
        <p className="text-[15px] text-muted">{t(pay.key, pay.vars)}</p>
      </div>
      <div className="grid gap-4">
        <div className="grid grid-cols-2 gap-4 border-t border-line pt-4">
          <p className="grid gap-0.5"><span className="type-figure text-[1.75rem]">{applied ?? "–"}</span><span className="text-[13px] text-muted">{t("brandCampaigns.view.figures.applications")}</span></p>
          <p className="grid gap-0.5"><span className="type-figure text-[1.75rem]">{report ? agreed : "–"}</span><span className="text-[13px] text-muted">{t("brandCampaigns.view.figures.agreed")}</span></p>
        </div>
        {finished !== null && (
          <div className="grid gap-1.5" aria-hidden>
            <div className="h-2 overflow-hidden rounded-full bg-sunk"><div className="h-full rounded-full bg-lime" style={{ width: `${Math.max(finished, 4)}%` }} /></div>
          </div>
        )}
      </div>
    </Link>
  );
}
