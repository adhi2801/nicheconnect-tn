"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Notice } from "@/components/ui/notice";
import { TextAreaField } from "@/components/ui/text-area-field";
import { TextField } from "@/components/ui/text-field";
import { type Application } from "@/lib/applications";
import { applicationBody, applyRefusal, checkApplication, payLine, PITCH_MAX, pitchLength, quoteAboveBudget, type ApplyProblems, type Campaign } from "@/lib/campaigns";
import { draftName, dropDraft, readDraft, saveDraft } from "@/lib/drafts";
import { ApiError, commonWordsKey } from "@/lib/errors";
import { formatPaise } from "@/lib/format";
import { t, type MessageKey } from "@/lib/app-messages";
import { useApply } from "@/lib/mutations";
import { useSession } from "@/lib/use-session";
import type { IntentKeys } from "@/lib/writes";

type Draft = { pitch: string; quote: string };
const numbers = new Intl.NumberFormat("en-IN");

/** The application itself (screen-plan C4): a pitch and an optional quote, with the campaign's budget beside them so nobody quotes blind.
 *  What is typed is kept on this device until it is sent, and survives a failed send. */
export function ApplyForm({ campaign, intentKeys, onSent, onCancel, onBusy }: { campaign: Campaign; intentKeys: IntentKeys; onSent: (a: Application) => void; onCancel: () => void; onBusy: (busy: boolean) => void }) {
  const session = useSession();
  const name = draftName(session.status === "signedIn" ? session.session.accountId : "none", `apply:${campaign.id}`);
  const apply = useApply(campaign.id, intentKeys);
  const form = useRef<HTMLFormElement>(null);
  // The draft is read as the form is made. Signed-in screens never render on the server (AppShell waits for the session), so this
  // cannot differ between the server's HTML and the browser's.
  const [draft] = useState(() => readDraft<Draft>(name));
  const [pitch, setPitch] = useState(typeof draft?.pitch === "string" ? draft.pitch : "");
  const [quote, setQuote] = useState(typeof draft?.quote === "string" ? draft.quote : "");
  const [problems, setProblems] = useState<ApplyProblems>({});
  const [failure, setFailure] = useState<{ key: MessageKey; vars?: Record<string, number>; profileLink?: boolean } | null>(null);
  const [attempts, setAttempts] = useState(0);

  // Only words worth keeping: an empty form leaves nothing behind.
  useEffect(() => { if (pitch.trim() || quote.trim()) saveDraft(name, { pitch, quote } satisfies Draft); else dropDraft(name); }, [name, pitch, quote]);
  useEffect(() => { onBusy(apply.isPending); }, [apply.isPending, onBusy]);
  // After a refused send, focus goes to the first field with a problem, so a screen reader reads its error (frontend.md section 6).
  useEffect(() => { if (attempts > 0) form.current?.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus(); }, [attempts]);

  function submit(e: FormEvent) {
    e.preventDefault();
    setFailure(null);
    const found = checkApplication(pitch, quote);
    setProblems(found);
    setAttempts((n) => n + 1);
    if (Object.keys(found).length > 0) return;
    apply.mutate(applicationBody(pitch, quote), {
      onSuccess: (sent) => { dropDraft(name); onSent(sent); },
      onError: (error) => {
        if (error instanceof ApiError && error.kind === "rate_limited") { setFailure(error.retryAfter ? { key: "common.rateLimitedWait", vars: { seconds: error.retryAfter } } : { key: "common.rateLimited" }); return; }
        if (error instanceof ApiError && (error.kind === "conflict" || error.kind === "invalid" || error.kind === "not_found" || error.kind === "withheld" || error.kind === "forbidden")) {
          const refusal = applyRefusal(error.code, error.fields);
          if (refusal.field) { setProblems({ [refusal.field]: refusal.key }); setAttempts((n) => n + 1); return; }
          setFailure({ key: refusal.key, profileLink: error.code === "creator_profile_required" });
          return;
        }
        setFailure({ key: commonWordsKey(error) });
      },
    });
  }

  const pay = payLine(campaign);
  const above = quoteAboveBudget(quote, campaign.budget_max_paise);

  return (
    <form ref={form} noValidate onSubmit={submit} className="grid gap-5">
      <TextAreaField
        label={t("apply.pitch.label")}
        hint={t("apply.pitch.hint")}
        error={problems.pitch ? t(problems.pitch) : undefined}
        counter={t("apply.pitch.counter", { count: numbers.format(pitchLength(pitch)) })}
        value={pitch}
        onChange={(e) => { setPitch(e.target.value); setProblems((p) => ({ ...p, pitch: undefined })); }}
        maxLength={PITCH_MAX * 2 + 200}
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
