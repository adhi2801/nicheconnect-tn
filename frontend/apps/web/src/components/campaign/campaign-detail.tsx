"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ReportBlockSheet } from "@/components/safety/report-block-sheet";
import { Button, ButtonLink } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { FlagNote } from "@/components/ui/flag-note";
import { ChevronLeftIcon } from "@/components/ui/icons";
import { Notice } from "@/components/ui/notice";
import { Pill } from "@/components/ui/pill";
import { Reveal } from "@/components/ui/reveal";
import { Sheet } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { statusTone, statusWords, type Application } from "@/lib/applications";
import { flagsFor, payLine, type Campaign } from "@/lib/campaigns";
import { formatDate, indiaDay } from "@/lib/format";
import { campaignTypeLabel, formatLabel, nicheLabel, platformLabel } from "@/lib/labels";
import { t } from "@/lib/app-messages";
import { useApply, useIntentKeys } from "@/lib/mutations";
import { draftName, dropDraft } from "@/lib/drafts";
import { useSession } from "@/lib/use-session";
import { ApplyForm } from "./apply-form";
import { BrandRecord } from "./brand-record";

/** Everything needed to decide, on one page, above the one action (screen-plan C3: terms before commitment). */
export function CampaignDetail({ campaign, mine, checking }: { campaign: Campaign; mine: Application | undefined; checking: boolean }) {
  const router = useRouter();
  const [applying, setApplying] = useState(false);
  const [reporting, setReporting] = useState(false);
  const [sent, setSent] = useState<Application | null>(null);
  // The write and its key live here, not in the sheet: closing and reopening the sheet after a lost answer resends with the same key,
  // and a success is shown (and the draft dropped) even if the browser closed the sheet while it was sending.
  const keys = useIntentKeys();
  const session = useSession();
  const draft = draftName(session.status === "signedIn" ? session.session.accountId : "none", `apply:${campaign.id}`);
  const apply = useApply(campaign.id, keys, (a) => { dropDraft(draft); setSent(a); setApplying(false); });
  const pay = payLine(campaign);
  const yours = sent ?? mine;

  const facts: { term: string; detail: string }[] = [
    { term: t("campaign.cities"), detail: campaign.cities.length > 0 ? campaign.cities.join(", ") : t("campaign.anyCity") },
    { term: t("campaign.niches"), detail: campaign.niches.map(nicheLabel).join(", ") },
    { term: t("campaign.closes"), detail: campaign.applications_close_on ? t("campaign.closesOn", { date: formatDate(campaign.applications_close_on) }) : t("campaign.noClose") },
  ];

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-6 lg:gap-7">
      <Reveal>
        <div className="grid gap-4">
          <Link href="/app/discover" className="t-base inline-flex min-h-11 items-center gap-1.5 justify-self-start rounded-full pr-3 text-sm font-semibold text-muted hover:text-ink">
            <ChevronLeftIcon width={18} height={18} aria-hidden />{t("campaign.back")}
          </Link>
          <header className="grid gap-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm font-semibold text-muted">{t("campaign.by", { brand: campaign.brand_name })}</p>
              <Button variant="quiet" className="min-h-11 px-4 text-sm" onClick={() => setReporting(true)}>{t("safety.open")}</Button>
            </div>
            <h1 className="font-display text-[2rem] font-semibold leading-[1.1] tracking-tight sm:text-[2.5rem]">{campaign.title}</h1>
            <FlagNote flags={flagsFor(campaign.text_flags, "title")} />
            <div className="flex flex-wrap gap-1.5"><Pill tone="neutral">{campaignTypeLabel(campaign.campaign_type)}</Pill></div>
          </header>
        </div>
      </Reveal>

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,22rem)]">
        <Reveal index={1} className="grid gap-5">
          <Card className="grid gap-6">
            <section className="grid gap-1">
              <h2 className="text-sm font-semibold text-muted">{t("campaign.pay")}</h2>
              <p className="font-display text-2xl font-semibold tabular-nums">{t(pay.key, pay.vars)}</p>
            </section>
            <section className="grid gap-2">
              <h2 className="text-sm font-semibold text-muted">{t("campaign.deliver")}</h2>
              {/* The summary both sides read is always shown, so a warning beside it is never about text nobody can see. */}
              <p className="whitespace-pre-line text-[15px] leading-6">{campaign.deliverables}</p>
              <FlagNote flags={flagsFor(campaign.text_flags, "deliverables")} />
              {campaign.deliverable_items.length > 0 && (
                <ul className="grid gap-2">
                  {campaign.deliverable_items.map((d, i) => (
                    <li key={i} className="rounded-2xl bg-sunk px-4 py-3 text-[15px] leading-6">
                      <span className="font-semibold">{t("campaign.deliverable", { quantity: d.quantity, format: formatLabel(d.format), platform: platformLabel(d.platform) })}</span>
                      {/* The backend does not check these notes for contact details or money requests yet (request R11). */}
                      {d.note && <span className="block text-muted">{d.note}</span>}
                    </li>
                  ))}
                </ul>
              )}
            </section>
            <section className="grid gap-2">
              <h2 className="text-sm font-semibold text-muted">{t("campaign.about")}</h2>
              {/* Another person's text: shown as text, never turned into links (frontend.md section 10). */}
              <p className="max-w-[68ch] whitespace-pre-line text-[15px] leading-7">{campaign.description}</p>
              <FlagNote flags={flagsFor(campaign.text_flags, "description")} />
            </section>
            <dl className="grid gap-3 sm:grid-cols-3">
              {facts.map((f) => (
                <div key={f.term} className="grid gap-0.5"><dt className="text-sm font-semibold text-muted">{f.term}</dt><dd className="text-[15px]">{f.detail}</dd></div>
              ))}
            </dl>
          </Card>
        </Reveal>

        <Reveal index={2} className="grid gap-5 lg:sticky lg:top-6">
          <Card className="grid gap-4" tone={yours || checking ? "light" : "dark"}>
            {sent && (
              <Notice>
                <p className="font-semibold text-ink">{t("apply.sent.title")}</p>
                <p>{t("apply.sent.body", { brand: campaign.brand_name })}</p>
              </Notice>
            )}
            {sent && <FlagNote flags={flagsFor(sent.text_flags, "pitch")} />}
            {checking && !sent ? (
              <div aria-busy="true" aria-label={t("common.loading")} className="grid gap-3"><Skeleton className="h-8 w-2/3" /><Skeleton className="h-12 w-full" /></div>
            ) : yours ? (
              <div className="grid gap-3">
                <h2 className="font-display text-lg font-semibold tracking-tight">{t(yours.origin === "invited" ? "campaign.yours.invitedTitle" : "campaign.yours.title")}</h2>
                <div className="flex flex-wrap items-center gap-2">
                  <Pill tone={statusTone(yours.status)}>{t(statusWords(yours.status))}</Pill>
                  <span className="text-sm text-muted">{t(yours.origin === "invited" ? "campaign.yours.invited" : "campaign.yours.sent", { date: formatDate(indiaDay(yours.created_at)) })}</span>
                </div>
                <ButtonLink href="/app/applications" variant="secondary" className="justify-self-start">{t("campaign.yours.see")}</ButtonLink>
              </div>
            ) : campaign.applications_open ? (
              <div className="grid gap-3">
                <p className="font-display text-2xl font-semibold tabular-nums">{t(pay.key, pay.vars)}</p>
                <p className="text-sm text-on-accent/80">{campaign.applications_close_on ? t("campaign.closesOn", { date: formatDate(campaign.applications_close_on) }) : t("campaign.noClose")}</p>
                <Button variant="highlight" onClick={() => { if (!apply.isPending) apply.reset(); setApplying(true); }}>{t("campaign.apply")}</Button>
              </div>
            ) : (
              <p className="text-[15px] font-semibold">{t("campaign.closed")}</p>
            )}
          </Card>
          <BrandRecord campaign={campaign} />
        </Reveal>
      </div>

      <ReportBlockSheet open={reporting} onClose={() => setReporting(false)} subject={{ kind: "campaign", id: campaign.id }} brandId={campaign.brand_id} brandName={campaign.brand_name} onBlocked={() => router.replace("/app/discover?blocked=1")} />

      <Sheet open={applying} onClose={() => setApplying(false)} title={t("apply.title", { title: campaign.title })} locked={apply.isPending}>
        {applying && <ApplyForm campaign={campaign} apply={apply} draft={draft} onCancel={() => setApplying(false)} />}
      </Sheet>
    </div>
  );
}
