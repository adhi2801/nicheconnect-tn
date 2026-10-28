import { ButtonLink } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { t } from "@/lib/messages";
import type { Role } from "@/lib/session";

/** A new account has no profile yet. This comes before anything else, because nothing else works until it exists. */
export function FirstRun({ role }: { role: Role }) {
  return (
    <Card className="grid gap-4 border border-line p-6 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center sm:p-7">
      <div className="grid gap-1.5">
        <h2 className="font-display text-xl font-semibold tracking-tight">{t("today.firstRun.title")}</h2>
        <p className="max-w-[52ch] text-[15px] leading-6 text-muted">{t(`today.firstRun.body.${role}`)}</p>
      </div>
      <ButtonLink href="/app/onboarding">{t("today.firstRun.cta")}</ButtonLink>
    </Card>
  );
}
