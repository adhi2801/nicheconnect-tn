"use client";

import { useEffect, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Notice } from "@/components/ui/notice";
import { TextAreaField } from "@/components/ui/text-area-field";
import { TextField } from "@/components/ui/text-field";
import { type Application } from "@/lib/applications";
import { applicationBody, applyRefusal, checkApplication, payLine, PITCH_MAX, quoteAboveBudget, type ApplyProblems, type Campaign } from "@/lib/campaigns";
import { dropDraft, readDraft, saveDraft } from "@/lib/drafts";
import { ApiError, commonWordsKey } from "@/lib/errors";
import { formatPaise } from "@/lib/format";
import { t } from "@/lib/messages";
import { useApply } from "@/lib/mutations";

type Draft = { pitch: string; quote: string };
const numbers = new Intl.NumberFormat("en-IN");

/** The application itself (screen-plan C4): a pitch and an optional quote, with the campaign's budget beside them so nobody quotes blind.
 *  What is typed is kept on this device until it is sent, and survives a failed send. */
export function ApplyForm({ campaign, onSent, onCancel, onBusy }: { campaign: Campaign; onSent: (a: Application) => void; onCancel: () => void; onBusy: (busy: boolean) => void }) {
  const draftName = `apply:${campaign.id}`;
  const apply = useApply(campaign.id);
  // The draft is read as the form is made. Signed-in screens never render on the server (AppShell waits for the session), so this
  // cannot differ between the server's HTML and the browser's.
  const [draft] = useState(() => readDraft<Draft>(draftName));
  const [pitch, setPitch] = useState(typeof draft?.pitch === "string" ? draft.pitch : "");
  const [quote, setQuote] = useState(typeof draft?.quote === "string" ? draft.quote : "");
  const [problems, setProblems] = useState<ApplyProblems>({});
  const [failure, setFailure] = useState<string | null>(null);

  useEffect(() => { saveDraft(draftName, { pitch, quote } satisfies Draft); }, [draftName, pitch, quote]);
  useEffect(() => { onBusy(apply.isPending); }, [apply.isPending, onBusy]);

  function submit(e: FormEvent) {
    e.preventDefault();
    setFailure(null);
    const found = checkApplication(pitch, quote);
    setProblems(found);
    if (Object.keys(found).length > 0) return;
    apply.mutate(applicationBody(pitch, quote), {
      onSuccess: (sent) => { dropDraft(draftName); onSent(sent); },
      onError: (error) => {
        if (error instanceof ApiError && error.kind === "rate_limited") { setFailure(error.retryAfter ? t("common.rateLimitedWait", { seconds: error.retryAfter }) : t("common.rateLimited")); return; }
        if (error instanceof ApiError && (error.kind === "conflict" || error.kind === "invalid" || error.kind === "not_found" || error.kind === "withheld" || error.kind === "forbidden")) {
          const refusal = applyRefusal(error.code, error.fields);
          if (refusal.field) { setProblems({ [refusal.field]: refusal.key }); return; }
          setFailure(t(refusal.key));
          return;
        }
        setFailure(t(commonWordsKey(error)));
      },
    });
  }

  const pay = payLine(campaign);
  const above = quoteAboveBudget(quote, campaign.budget_max_paise);
  const length = pitch.trim().length;

  return (
    <form noValidate onSubmit={submit} className="grid gap-5">
      <TextAreaField
        label={t("apply.pitch.label")}
        hint={t("apply.pitch.hint")}
        error={problems.pitch ? t(problems.pitch) : undefined}
        counter={t("apply.pitch.counter", { count: numbers.format(length) })}
        value={pitch}
        onChange={(e) => { setPitch(e.target.value); setProblems((p) => ({ ...p, pitch: undefined })); }}
        maxLength={PITCH_MAX + 200}
      />
      <div className="grid gap-2">
        <TextField label={t("apply.quote.label")} hint={t("apply.quote.hint")} error={problems.quote ? t(problems.quote) : undefined} prefix="₹" inputMode="decimal" value={quote} onChange={(e) => { setQuote(e.target.value); setProblems((p) => ({ ...p, quote: undefined })); }} maxLength={16} />
        <p className="text-sm text-muted">{t("apply.budget", { pay: t(pay.key, pay.vars) })}</p>
        {above && campaign.budget_max_paise != null && <Notice><p>{t("apply.aboveBudget", { max: formatPaise(campaign.budget_max_paise) })}</p></Notice>}
      </div>
      <p className="rounded-2xl bg-sunk px-4 py-3 text-sm font-medium leading-6">{t("apply.safety")}</p>
      {failure && (
        <Notice tone="error">
          <p className="font-semibold">{t("apply.failedTitle")}</p>
          <p>{failure}</p>
          <p>{t("apply.keptNote")}</p>
        </Notice>
      )}
      <p className="text-sm text-muted">{t("apply.draftKept")}</p>
      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" loading={apply.isPending}>{apply.isPending ? t("apply.sending") : t("apply.send")}</Button>
        <Button variant="quiet" disabled={apply.isPending} onClick={onCancel}>{t("apply.cancel")}</Button>
      </div>
    </form>
  );
}
