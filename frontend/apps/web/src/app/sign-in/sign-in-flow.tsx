"use client";

import { useEffect, useRef, useState, useSyncExternalStore, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ChoiceGroup } from "@/components/ui/choice-group";
import { CodeField } from "@/components/ui/code-field";
import { Notice } from "@/components/ui/notice";
import { TextField } from "@/components/ui/text-field";
import { requestCode, verifyCode, type Failure } from "@/lib/auth";
import { t, type MessageKey } from "@/lib/messages";
import { maskIndianMobile, normalizeIndianMobile } from "@/lib/phone";
import { restoreSession, subscribeToSession, getSessionState, getServerSessionState, type Role } from "@/lib/session";

const RESEND_AFTER_SECONDS = 30;

type Shown = { field?: string; notice?: string; reference?: string };

// Maps what went wrong to words. Each message says what happened and how to fix it (docs/standards/ux.md section 6).
function describe(f: Failure, role: Role | null, onCodeStep: boolean): Shown {
  const reference = f.requestId ? t("common.reference", { id: f.requestId }) : undefined;
  const wait = f.retryAfter;
  switch (f.kind) {
    case "invalid_input": return onCodeStep ? { field: t("code.tooShort") } : { field: t("signIn.phoneInvalid") };
    case "invalid_code": return { field: t("code.invalid") };
    case "rate_limited": return { notice: wait ? t("code.rateLimited", { seconds: wait }) : t("code.rateLimitedNoWait"), reference };
    case "busy": return { notice: t("common.busy"), reference };
    case "suspended": return { notice: t("code.suspended"), reference };
    case "role_conflict": return { notice: t("code.roleConflict", { role: role ?? "member" }), reference };
    case "phone_change_waiting": return { notice: t("code.phoneChangeWaiting"), reference };
    case "network": return { notice: t("common.offline") };
    default: return { notice: t("common.somethingWrong"), reference };
  }
}

export function SignInFlow() {
  const router = useRouter();
  const [step, setStep] = useState<"phone" | "code">("phone");
  const [role, setRole] = useState<Role | null>(null);
  const [phoneInput, setPhoneInput] = useState("");
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [roleError, setRoleError] = useState<string>();
  const [shown, setShown] = useState<Shown>({});
  const [busy, setBusy] = useState(false);
  const [cooldown, setCooldown] = useState(0);
  const heading = useRef<HTMLHeadingElement>(null);
  const session = useSyncExternalStore(subscribeToSession, getSessionState, getServerSessionState);

  // Someone who is still signed in (the cookie is valid) goes straight on; the form is visible while that is checked.
  useEffect(() => { void restoreSession(); }, []);
  useEffect(() => { if (session.status === "signedIn") router.replace("/app"); }, [session.status, router]);

  // Move focus to the new screen's heading so a screen reader announces where the person is.
  useEffect(() => { heading.current?.focus(); }, [step]);

  useEffect(() => {
    if (cooldown <= 0) return;
    const timer = setTimeout(() => setCooldown((s) => s - 1), 1000);
    return () => clearTimeout(timer);
  }, [cooldown]);

  async function sendCode(e?: FormEvent) {
    e?.preventDefault();
    if (busy) return;
    const e164 = normalizeIndianMobile(phoneInput || phone);
    setRoleError(undefined);
    setShown({});
    if (!role) { setRoleError(t("signIn.roleMissing")); return; }
    if (!e164) { setShown({ field: t("signIn.phoneInvalid") }); return; }
    setBusy(true);
    const result = await requestCode(e164);
    setBusy(false);
    if (!result.ok) {
      setShown(describe(result, role, false));
      if (result.kind === "rate_limited" && result.retryAfter) setCooldown(result.retryAfter);
      return;
    }
    setPhone(e164);
    setCode("");
    setCooldown(RESEND_AFTER_SECONDS);
    setStep("code");
  }

  async function confirm(digits: string) {
    if (busy || !role) return;
    if (digits.length !== 6) { setShown({ field: t("code.tooShort") }); return; }
    setShown({});
    setBusy(true);
    const result = await verifyCode({ phone, code: digits, role });
    if (result.ok) { router.push("/app"); return; }
    setBusy(false);
    setShown(describe(result, role, true));
    if (result.kind === "invalid_code") setCode("");
  }

  function onCodeChange(digits: string) {
    setCode(digits);
    if (shown.field) setShown({});
    if (digits.length === 6) void confirm(digits);
  }

  function changeNumber() {
    setStep("phone");
    setCode("");
    setShown({});
  }

  return (
    <main className="mx-auto flex w-full max-w-[480px] flex-1 flex-col justify-center gap-8 px-5 py-12">
      <header className="grid gap-3">
        <p className="flex items-center gap-2 font-display text-lg font-semibold tracking-tight"><span aria-hidden className="size-2.5 rounded-full bg-ink" />Colyv</p>
        <h1 ref={heading} tabIndex={-1} className="font-display text-[2rem] font-semibold leading-tight tracking-tight outline-none">
          {step === "phone" ? t("signIn.title") : t("code.title")}
        </h1>
        <p className="text-[15px] leading-6 text-muted">{step === "phone" ? t("signIn.subtitle") : t("code.sentTo", { phone: maskIndianMobile(phone) })}</p>
      </header>

      <Card className="grid gap-6">
        {shown.notice && <Notice tone="error" action={shown.reference && <span className="font-mono text-xs">{shown.reference}</span>}>{shown.notice}</Notice>}

        {step === "phone" ? (
          <form onSubmit={sendCode} noValidate className="grid gap-6">
            <ChoiceGroup<Role>
              legend={t("signIn.roleLabel")}
              value={role as Role}
              onChange={(r) => { setRole(r); setRoleError(undefined); }}
              choices={[
                { value: "creator", title: t("signIn.creator"), hint: t("signIn.creatorHint") },
                { value: "brand", title: t("signIn.brand"), hint: t("signIn.brandHint") },
              ]}
            />
            {roleError ? <p role="alert" className="-mt-3 text-sm text-bad">{roleError}</p> : <p className="-mt-3 text-sm text-muted">{t("signIn.roleNote")}</p>}
            <TextField
              label={t("signIn.phoneLabel")}
              hint={t("signIn.phoneHint")}
              error={shown.field}
              prefix="+91"
              type="tel"
              inputMode="numeric"
              autoComplete="tel-national"
              placeholder="98765 43210"
              value={phoneInput}
              onChange={(e) => { setPhoneInput(e.target.value); if (shown.field) setShown({}); }}
            />
            <Button type="submit" loading={busy} className="w-full">{busy ? t("signIn.sending") : t("signIn.send")}</Button>
            <p className="text-center text-sm text-muted">{t("signIn.safety")}</p>
          </form>
        ) : (
          <form onSubmit={(e) => { e.preventDefault(); void confirm(code); }} noValidate className="grid gap-6">
            <CodeField label={t("code.label")} value={code} onChange={onCodeChange} error={shown.field} autoFocus disabled={busy} />
            <Button type="submit" loading={busy} className="w-full">{busy ? t("code.confirming") : t("code.confirm")}</Button>
            <div className="grid justify-items-center gap-1">
              <Button variant="quiet" onClick={() => void sendCode()} disabled={cooldown > 0 || busy}>
                {cooldown > 0 ? t("code.resendIn", { seconds: cooldown }) : t("code.resend")}
              </Button>
              <Button variant="quiet" onClick={changeNumber}>{t("code.change")}</Button>
            </div>
            <p className="text-center text-sm text-muted">{t("code.safety")}</p>
          </form>
        )}
      </Card>
    </main>
  );
}

// Exported so the keys used here stay checked by the compiler even if a message is renamed.
export type SignInMessageKey = Extract<MessageKey, `signIn.${string}` | `code.${string}`>;
