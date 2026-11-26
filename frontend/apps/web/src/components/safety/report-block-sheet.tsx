"use client";

import { useId, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Notice } from "@/components/ui/notice";
import { Sheet } from "@/components/ui/sheet";
import { TextAreaField } from "@/components/ui/text-area-field";
import { t } from "@/lib/app-messages";
import { ApiError, commonWordsKey } from "@/lib/errors";
import { useBlockBrand, useReport } from "@/lib/mutations";
import { answeredWithin, noteTooLong, REPORT_CATEGORIES, REPORT_NOTE_MAX, reportBody, type ReportCategory, type Subject } from "@/lib/safety";

const failureWords = (error: unknown): string =>
  error instanceof ApiError && error.kind === "rate_limited" && error.retryAfter ? t("common.rateLimitedWait", { seconds: error.retryAfter }) : t(commonWordsKey(error));

/**
 * Report and block, one tap from anything a brand sent (trust-and-safety.md section 5). Report names the campaign or the brand with a
 * reason; block stops the brand reaching this creator, and the brand is never told. The backend decides both.
 */
export function ReportBlockSheet({ open, onClose, subject, brandId, brandName, onBlocked }: { open: boolean; onClose: () => void; subject: Subject; brandId: string; brandName: string; onBlocked: () => void }) {
  const report = useReport();
  const block = useBlockBrand();
  const legend = useId();
  const [category, setCategory] = useState<ReportCategory | null>(null);
  const [note, setNote] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [reported, setReported] = useState<{ again: boolean; category: ReportCategory } | null>(null);
  const [confirmBlock, setConfirmBlock] = useState(false);

  function sendReport(e: FormEvent) {
    e.preventDefault();
    if (!category) { setProblem(t("safety.report.pickReason")); return; }
    if (noteTooLong(note)) { setProblem(t("safety.report.noteLong")); return; }
    setProblem(null);
    report.mutate(reportBody(subject, category, note), {
      onSuccess: ({ alreadyOpen }) => setReported({ again: alreadyOpen, category }),
      onError: (error) => setProblem(error instanceof ApiError && error.kind === "conflict" ? t("safety.report.refused") : failureWords(error)),
    });
  }

  return (
    <Sheet open={open} onClose={onClose} title={t("safety.title", { brand: brandName })} locked={report.isPending || block.isPending}>
      {reported ? (
        <Notice>
          <p className="font-semibold text-ink">{t(reported.again ? "safety.report.already" : "safety.report.sent")}</p>
          <p>{t(answeredWithin(reported.category))}</p>
        </Notice>
      ) : (
        <form noValidate onSubmit={sendReport} className="grid gap-4">
          <fieldset className="grid gap-2" aria-describedby={problem ? `${legend}-problem` : undefined}>
            <legend id={legend} className="mb-1 font-display text-lg font-semibold tracking-tight">{t(subject.kind === "campaign" ? "safety.report.titleCampaign" : "safety.report.titleBrand")}</legend>
            <p className="text-sm text-muted">{t("safety.report.why")}</p>
            {REPORT_CATEGORIES.map((c) => (
              <label key={c} className="t-base flex min-h-11 cursor-pointer items-start gap-3 rounded-2xl border border-line-strong px-4 py-3 has-[:checked]:border-ink has-[:checked]:shadow-[0_0_0_1px_var(--c-ink)]">
                <input type="radio" name={legend} value={c} checked={category === c} onChange={() => { setCategory(c); setProblem(null); }} className="mt-1 size-4 accent-[var(--c-ink)]" />
                <span className="grid gap-0.5"><span className="text-[15px] font-semibold">{t(`safety.categories.${c}.title`)}</span><span className="text-sm text-muted">{t(`safety.categories.${c}.hint`)}</span></span>
              </label>
            ))}
          </fieldset>
          <TextAreaField label={t("safety.report.noteLabel")} hint={t("safety.report.noteHint")} rows={3} value={note} onChange={(e) => setNote(e.target.value)} maxLength={REPORT_NOTE_MAX * 2} counter={t("safety.report.noteCounter", { count: [...note.trim()].length })} />
          {problem && <p id={`${legend}-problem`} role="alert" className="text-sm text-bad">{problem}</p>}
          <Button type="submit" variant="secondary" className="justify-self-start" loading={report.isPending}>{report.isPending ? t("safety.report.sending") : t("safety.report.send")}</Button>
        </form>
      )}

      <section className="grid gap-3 border-t border-line pt-5" aria-labelledby={`${legend}-block`}>
        <h3 id={`${legend}-block`} className="font-display text-lg font-semibold tracking-tight">{t("safety.block.title", { brand: brandName })}</h3>
        <p className="text-sm leading-6 text-muted">{t("safety.block.what")}</p>
        {block.isError && <Notice tone="error"><p>{failureWords(block.error)}</p></Notice>}
        {confirmBlock ? (
          <div className="flex flex-wrap items-center gap-3">
            <Button loading={block.isPending} onClick={() => block.mutate(brandId, { onSuccess: onBlocked })}>{block.isPending ? t("safety.block.working") : t("safety.block.confirm", { brand: brandName })}</Button>
            <Button variant="quiet" disabled={block.isPending} onClick={() => setConfirmBlock(false)}>{t("safety.block.keep")}</Button>
          </div>
        ) : (
          <Button variant="secondary" className="justify-self-start" onClick={() => setConfirmBlock(true)}>{t("safety.block.button", { brand: brandName })}</Button>
        )}
      </section>
    </Sheet>
  );
}
