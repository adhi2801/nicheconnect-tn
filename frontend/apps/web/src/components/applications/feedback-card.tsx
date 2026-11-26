"use client";

import Link from "next/link";
import { Card } from "@/components/ui/card";
import { feedbackLines, reasonWords } from "@/lib/applications";
import { formatDate } from "@/lib/format";
import { t } from "@/lib/app-messages";
import { useApplicationFeedback } from "@/lib/queries";

/** What a creator's applications show, as dated facts, only where there is enough to say something (screen-plan C5). Silent otherwise:
 *  a failed or thin summary leaves the list alone rather than adding a warning nobody can act on. */
export function FeedbackCard() {
  const feedback = useApplicationFeedback();
  if (!feedback.data) return null;
  const lines = feedbackLines(feedback.data);
  if (lines.length === 0) return null;
  return (
    <Card className="grid gap-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-display text-lg font-semibold tracking-tight">{t("applications.feedback.title")}</h2>
        <p className="text-xs text-muted">{t("applications.feedback.asOf", { date: formatDate(feedback.data.as_of) })}</p>
      </div>
      <ul className="grid gap-2">
        {lines.map((line) => (
          <li key={line.key} className="flex items-start gap-2 text-[15px] leading-6">
            <span aria-hidden className="mt-2.5 size-1.5 shrink-0 rounded-full bg-accent" />
            <span>
              {t(line.key, line.reason ? { ...line.vars, reason: t(reasonWords(line.reason)).toLowerCase() } : line.vars)}
              {(line.key === "applications.feedback.open" || line.key === "applications.feedback.openOne") && (
                <> <Link href="/app/discover" className="font-semibold underline underline-offset-4">{t("applications.feedback.browse")}</Link></>
              )}
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
}
