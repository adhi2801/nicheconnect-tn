"use client";

import { Card } from "@/components/ui/card";
import { AlertIcon, ShieldIcon } from "@/components/ui/icons";
import { Skeleton } from "@/components/ui/skeleton";
import { recordLines, type Campaign } from "@/lib/campaigns";
import { t } from "@/lib/messages";
import { useReliability } from "@/lib/queries";

/** The brand's payment record, as facts with what they rest on (D-027): the only trust signal, and absent rather than faked. */
export function BrandRecord({ campaign }: { campaign: Campaign }) {
  const record = useReliability(campaign.brand_id);
  return (
    <Card className="grid gap-4">
      <div className="grid gap-1">
        <h2 className="font-display text-lg font-semibold tracking-tight">{t("campaign.record.title")}</h2>
        <p className="text-sm leading-5 text-muted">{t("campaign.record.source")}</p>
      </div>
      {campaign.brand_name_flag && (
        <p className="flex items-start gap-2 rounded-xl bg-warn-soft px-3 py-2 text-sm leading-5 text-warn"><AlertIcon width={16} height={16} className="mt-0.5 shrink-0" aria-hidden />{t("campaign.record.nameFlag")}</p>
      )}
      {/* Ink words, green only on the shield: small green text on these surfaces falls below the 7:1 body-text bar. */}
      {campaign.verified_domain && (
        <p className="inline-flex items-center gap-2 text-sm font-semibold"><ShieldIcon width={16} height={16} aria-hidden className="text-ok" />{t("campaign.record.domain", { domain: campaign.verified_domain.domain })}</p>
      )}
      {record.isPending ? (
        <div aria-busy="true" className="grid gap-2"><Skeleton className="h-5 w-full" /><Skeleton className="h-5 w-4/5" /></div>
      ) : record.isError ? (
        <p className="text-sm text-muted">{t("campaign.record.error")}</p>
      ) : (
        <ul className="grid gap-2.5">
          {recordLines(record.data).map((line) => (
            <li key={line.key} className={`flex items-start gap-2 text-[15px] leading-6 ${line.tone === "bad" ? "font-semibold text-bad" : ""}`}>
              <span aria-hidden className={`mt-2.5 size-1.5 shrink-0 rounded-full ${line.tone === "bad" ? "bg-bad" : "bg-accent"}`} />
              {t(line.key, line.vars)}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
