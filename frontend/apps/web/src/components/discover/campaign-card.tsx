import Link from "next/link";
import { FlagNote } from "@/components/ui/flag-note";
import { ShieldIcon } from "@/components/ui/icons";
import { Pill } from "@/components/ui/pill";
import { flagsFor, payLine, type Campaign } from "@/lib/campaigns";
import { formatDayMonth } from "@/lib/format";
import { nicheLabel } from "@/lib/labels";
import { t } from "@/lib/messages";

/** One open campaign: who, what it pays, where, and when it closes, so a creator can tell at a glance whether it is worth a look.
 *  No buttons on the card (screen-plan C2); the whole card opens the campaign. */
export function CampaignCard({ campaign, applied }: { campaign: Campaign; applied: boolean }) {
  const pay = payLine(campaign);
  const cities = campaign.cities.length > 0 ? campaign.cities.join(", ") : t("discover.card.anyCity");
  return (
    // No aria-label: it would replace the card's words, so a screen reader would hear the title but not the pay or the date (WCAG 2.5.3).
    <Link href={`/app/discover/${campaign.id}`} className="t-base group grid h-full content-start gap-3 rounded-3xl bg-sunk p-5 hover:-translate-y-0.5 hover:bg-line">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="min-w-0 truncate text-sm font-semibold text-muted">{campaign.brand_name}</p>
        {applied && <Pill tone="ok">{t("discover.card.applied")}</Pill>}
      </div>
      <h2 className="font-display text-lg font-semibold leading-snug tracking-tight">{campaign.title}</h2>
      <FlagNote flags={flagsFor(campaign.text_flags, "title")} />
      <p className="font-display text-xl font-semibold tabular-nums">{t(pay.key, pay.vars)}</p>
      <div className="flex flex-wrap gap-1.5">
        <Pill tone="neutral">{t(`campaignTypes.${campaign.campaign_type}`)}</Pill>
        {campaign.niches.slice(0, 3).map((n) => <Pill key={n} tone="neutral">{nicheLabel(n)}</Pill>)}
      </div>
      <dl className="grid gap-1 text-sm text-muted">
        <div className="flex gap-1.5"><dt className="sr-only">{t("campaign.cities")}</dt><dd className="min-w-0 truncate">{cities}</dd></div>
        <div className="flex gap-1.5"><dt className="sr-only">{t("campaign.closes")}</dt><dd>{campaign.applications_close_on ? t("discover.card.closes", { date: formatDayMonth(campaign.applications_close_on) }) : t("discover.card.noClose")}</dd></div>
      </dl>
      {campaign.brand_name_flag ? (
        <Pill tone="warn">{t("discover.card.nameFlag")}</Pill>
      ) : campaign.verified_domain ? (
        <p className="inline-flex items-center gap-1.5 text-xs font-semibold"><ShieldIcon width={14} height={14} aria-hidden className="text-ok" />{t("discover.card.verified", { domain: campaign.verified_domain.domain })}</p>
      ) : null}
    </Link>
  );
}
