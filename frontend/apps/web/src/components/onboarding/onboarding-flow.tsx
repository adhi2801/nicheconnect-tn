"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Notice } from "@/components/ui/notice";
import { TextField } from "@/components/ui/text-field";
import { draftName, dropDraft, readDraft, saveDraft } from "@/lib/drafts";
import { useSession } from "@/lib/use-session";
import { ApiError, commonWordsKey } from "@/lib/errors";
import { t } from "@/lib/app-messages";
import { useCreateProfile } from "@/lib/mutations";
import { checkStepOne, checkStepTwo, MAX_NICHES, NICHES, normalizeHandle, problemsFromServer, profileBody, stepOf, todayInIndia, type Niche, type Problems, type StepOne, type StepTwo } from "@/lib/onboarding";
import { useCities } from "@/lib/queries";
import { NichePicker } from "./niche-picker";

const FORM = "onboarding";
type Draft = StepOne & Omit<StepTwo, "dateOfBirth">;
const text = (v: unknown): string => (typeof v === "string" ? v : "");
// A stored draft is untrusted: only niches the app knows are kept, and never more than five.
const nichesFrom = (v: unknown): Niche[] => (Array.isArray(v) ? v.filter((n): n is Niche => (NICHES as readonly string[]).includes(n)).slice(0, MAX_NICHES) : []);

// The creator's two steps (screen-plan C0). "Step n of 2" is always visible: two short steps with a visible end are finished more
// often than one long form (the goal-gradient effect, docs/research/INTERFACE_PSYCHOLOGY_2026.md).
export function OnboardingFlow({ onFinishing }: { onFinishing: () => void }) {
  const router = useRouter();
  const create = useCreateProfile();
  const cities = useCities();
  const heading = useRef<HTMLHeadingElement>(null);
  // The draft is read as the form is made. Signed-in screens never render on the server (AppShell waits for the session), so this
  // cannot differ between the server's HTML and the browser's.
  const session = useSession();
  const DRAFT = draftName(session.status === "signedIn" ? session.session.accountId : "none", FORM);
  const form = useRef<HTMLDivElement>(null);
  const [attempts, setAttempts] = useState(0);
  const [draft] = useState(() => readDraft<Draft>(DRAFT));
  const [step, setStep] = useState<1 | 2>(1);
  const [one, setOne] = useState<StepOne>({ displayName: text(draft?.displayName), handle: text(draft?.handle) });
  const [two, setTwo] = useState<StepTwo>({ city: text(draft?.city), niches: nichesFrom(draft?.niches), dateOfBirth: "" });
  const [problems, setProblems] = useState<Problems>({});
  const [failure, setFailure] = useState<string | null>(null);

  // Never the date of birth (D-086).
  useEffect(() => {
    saveDraft(DRAFT, { displayName: one.displayName, handle: one.handle, city: two.city, niches: two.niches } satisfies Draft);
  }, [DRAFT, one, two.city, two.niches]);

  useEffect(() => { heading.current?.focus(); }, [step]);
  // After a refused step, focus goes to the first field with a problem, so a screen reader reads its error (frontend.md section 6).
  useEffect(() => { if (attempts > 0) form.current?.querySelector<HTMLElement>('[aria-invalid="true"], [data-invalid="true"] button')?.focus(); }, [attempts]);

  const words = (key?: Problems[keyof Problems]) => (key ? t(key) : undefined);
  // A field's error goes as soon as the person edits that field; the rest stay until they are fixed.
  const edited = (field: keyof Problems) => setProblems((p) => ({ ...p, [field]: undefined }));

  function next(e: FormEvent) {
    e.preventDefault();
    const found = checkStepOne(one);
    setProblems(found);
    if (Object.keys(found).length === 0) setStep(2);
    else setAttempts((n) => n + 1);
  }

  function finish(e: FormEvent) {
    e.preventDefault();
    setFailure(null);
    const today = todayInIndia();
    const found = { ...checkStepOne(one), ...checkStepTwo(two, today) };
    setProblems(found);
    if (Object.keys(found).length > 0) { setStep(stepOf(found)); setAttempts((n) => n + 1); return; }
    onFinishing();
    create.mutate(profileBody(one, two), {
      onSuccess: () => { dropDraft(DRAFT); router.push("/app/discover"); },
      onError: (error) => {
        if (error instanceof ApiError && error.code === "profile_exists") { dropDraft(DRAFT); router.replace("/app"); return; }
        const fromServer = error instanceof ApiError ? problemsFromServer(error.code, error.fields) : {};
        if (Object.keys(fromServer).length > 0) { setProblems(fromServer); setStep(stepOf(fromServer)); setAttempts((n) => n + 1); return; }
        if (error instanceof ApiError && error.kind === "rate_limited" && error.retryAfter) { setFailure(t("common.rateLimitedWait", { seconds: error.retryAfter })); return; }
        setFailure(t(commonWordsKey(error)));
      },
    });
  }

  const handle = normalizeHandle(one.handle);

  return (
    <div ref={form} className="mx-auto w-full max-w-xl">
    <Card className="grid gap-6 p-6 sm:p-8">
      <div className="grid gap-3">
        <div aria-hidden className="grid grid-cols-2 gap-1.5">
          <span className="h-1.5 rounded-full bg-accent" />
          <span className={`t-base h-1.5 rounded-full ${step === 2 ? "bg-accent" : "bg-line"}`} />
        </div>
        <p className="text-sm font-semibold text-muted">{t("onboarding.step", { n: step })}</p>
        <h1 ref={heading} tabIndex={-1} className="font-display text-[1.75rem] font-semibold leading-tight tracking-tight outline-none sm:text-[2rem]">
          {t(step === 1 ? "onboarding.one.title" : "onboarding.two.title")}
        </h1>
        <p className="text-[15px] leading-6 text-muted">{t(step === 1 ? "onboarding.one.subtitle" : "onboarding.two.subtitle")}</p>
      </div>

      {step === 1 ? (
        <form noValidate onSubmit={next} className="grid gap-5">
          <TextField label={t("onboarding.name.label")} hint={t("onboarding.name.hint")} error={words(problems.displayName)} value={one.displayName} onChange={(e) => { setOne({ ...one, displayName: e.target.value }); edited("displayName"); }} autoComplete="name" maxLength={120} />
          <div className="grid gap-1.5">
            <TextField label={t("onboarding.handle.label")} hint={t("onboarding.handle.hint")} error={words(problems.handle)} prefix="@" value={one.handle} onChange={(e) => { setOne({ ...one, handle: e.target.value }); edited("handle"); }} autoCapitalize="none" autoCorrect="off" spellCheck={false} maxLength={40} />
            {handle.length >= 3 && !problems.handle && <p className="text-sm text-muted">{t("onboarding.handle.preview", { handle })}</p>}
          </div>
          <p className="text-sm text-muted">{t("onboarding.draftKept")}</p>
          <Button type="submit" className="justify-self-start">{t("onboarding.continue")}</Button>
        </form>
      ) : (
        <form noValidate onSubmit={finish} className="grid gap-5">
          <TextField label={t("onboarding.city.label")} hint={t("onboarding.city.hint")} error={words(problems.city)} value={two.city} onChange={(e) => { setTwo({ ...two, city: e.target.value }); edited("city"); }} list="city-suggestions" autoComplete="address-level2" maxLength={60} />
          <datalist id="city-suggestions">{(cities.data ?? []).map((c) => <option key={c.city} value={c.city} />)}</datalist>
          <NichePicker value={two.niches} onChange={(niches) => { setTwo({ ...two, niches }); edited("niches"); }} error={words(problems.niches)} />
          <TextField type="date" label={t("onboarding.dob.label")} hint={t("onboarding.dob.hint")} error={words(problems.dateOfBirth)} value={two.dateOfBirth} onChange={(e) => { setTwo({ ...two, dateOfBirth: e.target.value }); edited("dateOfBirth"); }} max={todayInIndia()} autoComplete="bday" />
          {failure && (
            <Notice tone="error">
              <p className="font-semibold">{t("onboarding.errorTitle")}</p>
              <p>{failure}</p>
            </Notice>
          )}
          <div className="flex flex-wrap items-center gap-3">
            <Button type="submit" loading={create.isPending}>{create.isPending ? t("onboarding.finishing") : t("onboarding.finish")}</Button>
            <Button variant="quiet" disabled={create.isPending} onClick={() => { setProblems({}); setFailure(null); setStep(1); }}>{t("onboarding.back")}</Button>
          </div>
        </form>
      )}
    </Card>
    </div>
  );
}
