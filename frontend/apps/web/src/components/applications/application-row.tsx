import Link from "next/link";
import type { UseQueryResult } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { FlagNote } from "@/components/ui/flag-note";
import { Pill } from "@/components/ui/pill";
import { Skeleton } from "@/components/ui/skeleton";
import { canWithdraw, reasonWords, statusTone, statusWords, type Application } from "@/lib/applications";
import { flagsFor, type Campaign } from "@/lib/campaigns";
import { ApiError } from "@/lib/errors";
import { formatDate, formatPaise, indiaDay } from "@/lib/format";
import { t } from "@/lib/app-messages";

/** One application: which campaign, where it stands and since when, and why, when a brand said no. */
export function ApplicationRow({ application: a, campaign, onWithdraw, onReport }: { application: Application; campaign: UseQueryResult<Campaign> | undefined; onWithdraw: (a: Application) => void; onReport: (c: Campaign) => void }) {
  const gone = campaign?.error instanceof ApiError && (campaign.error.kind === "not_found" || campaign.error.kind === "withheld");
  return (
    <article className="grid gap-3 rounded-3xl bg-sunk p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="grid min-w-0 gap-0.5">
          {campaign?.data ? (
            <>
              <p className="truncate text-sm font-semibold text-muted">{campaign.data.brand_name}</p>
              <h3 className="font-display text-lg font-semibold leading-snug tracking-tight">{campaign.data.title}</h3>
              <FlagNote flags={flagsFor(campaign.data.text_flags, "title")} />
              {campaign.data.brand_name_flag && <p className="mt-1 text-sm font-semibold text-warn">{t("discover.card.nameFlag")}</p>}
            </>
          ) : campaign?.isPending ? (
            <div aria-busy="true" className="grid gap-1.5"><Skeleton className="h-4 w-28 bg-line" /><Skeleton className="h-6 w-56 bg-line" /></div>
          ) : (
            <h3 className="font-display text-lg font-semibold leading-snug tracking-tight text-muted">{t(gone ? "applications.campaignGone" : "applications.campaignUnknown")}</h3>
          )}
        </div>
        <Pill tone={statusTone(a.status)}>{t(statusWords(a.status))}</Pill>
      </div>

      <p className="text-sm text-muted">
        {t("applications.changed", { date: formatDate(indiaDay(a.status_changed_at)) })}
        {" · "}
        {a.quoted_amount_paise != null ? t("applications.quoted", { amount: formatPaise(a.quoted_amount_paise) }) : t("applications.noQuote")}
      </p>

      {a.status === "rejected" && a.rejection_reason && (
        <div className="grid gap-1 rounded-2xl bg-surface px-4 py-3 text-[15px] leading-6">
          <p><span className="font-semibold">{t("applications.reasonLabel")}: </span>{t(reasonWords(a.rejection_reason))}</p>
          {/* The brand's own words: text only, never links, with any warning beside them. */}
          {a.rejection_note && <p className="whitespace-pre-line text-muted"><span className="font-semibold text-ink">{t("applications.noteLabel")}: </span>{a.rejection_note}</p>}
          <FlagNote flags={flagsFor(a.text_flags, "rejection_note")} />
        </div>
      )}

      {a.status === "invited" && (
        <div className="grid gap-1 text-[15px] leading-6">
          {a.invitation_note && <p className="whitespace-pre-line">{a.invitation_note}</p>}
          <FlagNote flags={flagsFor(a.text_flags, "invitation_note")} />
          <p className="text-sm text-muted">{t("applications.invitedNote")}</p>
        </div>
      )}

      {(campaign?.data || canWithdraw(a)) && (
        <div className="flex flex-wrap items-center gap-2">
          {campaign?.data && <Link href={`/app/discover/${a.campaign_id}`} className="t-base inline-flex min-h-11 items-center rounded-full px-4 text-sm font-semibold underline-offset-4 hover:bg-surface hover:underline">{t("applications.open")}</Link>}
          {canWithdraw(a) && <Button variant="quiet" className="min-h-11 px-4 text-sm" onClick={() => onWithdraw(a)}>{t("applications.withdraw.button")}</Button>}
          {/* One tap from what the brand sent. Only where the brand is known: a closed campaign does not say which brand it was (R7). */}
          {campaign?.data && <Button variant="quiet" className="min-h-11 px-4 text-sm" onClick={() => campaign.data && onReport(campaign.data)}>{t("safety.open")}</Button>}
        </div>
      )}
    </article>
  );
}
