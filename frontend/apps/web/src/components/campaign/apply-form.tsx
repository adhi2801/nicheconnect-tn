"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import Link from "next/link";
import type { UseMutationResult } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Notice } from "@/components/ui/notice";
import { TextAreaField } from "@/components/ui/text-area-field";
import { TextField } from "@/components/ui/text-field";
import { t, type MessageKey } from "@/lib/app-messages";
import { type Application } from "@/lib/applications";
import { applicationBody, applyRefusal, checkApplication, payLine, PITCH_MAX, pitchLength, quoteAboveBudget, type ApplyProblems, type Campaign } from "@/lib/campaigns";
import { dropDraft, readDraft, saveDraft } from "@/lib/drafts";
import { ApiError, commonWordsKey } from "@/lib/errors";
import { formatPaise } from "@/lib/format";

type Draft = { pitch: string; quote: string };
type Body = ReturnType<typeof applicationBody>;
const numbers = new Intl.NumberFormat("en-IN");

/** What the backend's refusal means here: a field to fix, or words for the whole form. Read from the write itself, which lives on the
 *  campaign page; opening the sheet clears an old refusal, so a wait or "offline" from minutes ago is never shown as current. */
function refusalOf(error: unknown): { field?: keyof ApplyProblems; key: MessageKey; vars?: Record<string, number>; profileLink?: boolean } | null {
  if (!error) return null;
  if (error instanceof ApiError && error.kind === "rate_limited") return error.retryAfter ? { key: "common.rateLimitedWait", vars: { seconds: error.retryAfter } } : { key: "common.rateLimited" };
  if (error instanceof ApiError && ["conflict", "invalid", "not_found", "withheld", "forbidden"].includes(error.kind)) {
    const refusal = applyRefusal(error.code, error.fields);
    return { ...refusal, profileLink: error.code === "creator_profile_required" };
  }
  return { key: commonWordsKey(error) };
}

/** The application itself (screen-plan C4): a pitch and an optional quote, with the campaign's budget beside them so nobody quotes blind.
 *  What is typed is kept on this device until it is sent, and survives a failed send. */
export function ApplyForm({ campaign, apply, draft, onCancel }: { campaign: Campaign; apply: UseMutationResult<Application, Error, Body>; draft: string; onCancel: () => void }) {
  const form = useRef<HTMLFormElement>(null);
  // The draft is read as the form is made. Signed-in screens never render on the server (AppShell waits for the session), so this
  // cannot differ between the server's HTML and the browser's.
  const [saved] = useState(() => readDraft<Draft>(draft));
  const [pitch, setPitch] = useState(typeof saved?.pitch === "string" ? saved.pitch : "");
  const [quote, setQuote] = useState(typeof saved?.quote === "string" ? saved.quote : "");
  const [problems, setProblems] = useState<ApplyProblems>({});
  const [attempts, setAttempts] = useState(0);
  const refusal = refusalOf(apply.error);
  const shown: ApplyProblems = { ...problems, ...(refusal?.field ? { [refusal.field]: refusal.key } : {}) };

  // Only words worth keeping: an empty form leaves nothing behind.
  useEffect(() => { if (pitch.trim() || quote.trim()) saveDraft(draft, { pitch, quote } satisfies Draft); else dropDraft(draft); }, [draft, pitch, quote]);
  // After a refused send, focus goes to the first field with a problem, so a screen reader reads its error (frontend.md section 6).
  useEffect(() => { if (attempts > 0 || refusal?.field) form.current?.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus(); }, [attempts, refusal?.field]);

  const edited = (field: keyof ApplyProblems) => { setProblems((p) => ({ ...p, [field]: undefined })); if (apply.isError) apply.reset(); };

  function submit(e: FormEvent) {
    e.preventDefault();
    apply.reset();
    const found = checkApplication(pitch, quote);
    setProblems(found);
    setAttempts((n) => n + 1);
    if (Object.keys(found).length === 0) apply.mutate(applicationBody(pitch, quote));
  }

  const pay = payLine(campaign);
  const above = quoteAboveBudget(quote, campaign.budget_max_paise);
  const failure = refusal && !refusal.field ? refusal : null;

  return (
    <form ref={form} noValidate onSubmit={submit} className="grid gap-5">
      <TextAreaField
        label={t("apply.pitch.label")}
        hint={t("apply.pitch.hint")}
        error={shown.pitch ? t(shown.pitch) : undefined}
        counter={t("apply.pitch.counter", { count: numbers.format(pitchLength(pitch)) })}
        value={pitch}
        onChange={(e) => { setPitch(e.target.value); edited("pitch"); }}
        maxLength={PITCH_MAX * 2 + 200}
      />
      <div className="grid gap-2">
        <TextField label={t("apply.quote.label")} hint={t("apply.quote.hint")} error={shown.quote ? t(shown.quote) : undefined} prefix="₹" inputMode="decimal" value={quote} onChange={(e) => { setQuote(e.target.value); edited("quote"); }} maxLength={16} />
        <p className="text-sm text-muted">{t("apply.budget", { pay: t(pay.key, pay.vars) })}</p>
        {above && campaign.budget_max_paise != null && <Notice><p>{t("apply.aboveBudget", { max: formatPaise(campaign.budget_max_paise) })}</p></Notice>}
      </div>
      <p className="rounded-2xl bg-sunk px-4 py-3 text-sm font-medium leading-6">{t("apply.safety")}</p>
      {failure && (
        <Notice tone="error">
          <p className="font-semibold">{t("apply.failedTitle")}</p>
          <p>{t(failure.key, failure.vars)}</p>
          {failure.profileLink ? <Link href="/app/onboarding" className="font-semibold underline underline-offset-4">{t("apply.setUpProfile")}</Link> : <p>{t("apply.keptNote")}</p>}
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
