"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ButtonLink } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { LoadError } from "@/components/ui/load-error";
import { Skeleton } from "@/components/ui/skeleton";
import { OnboardingFlow } from "@/components/onboarding/onboarding-flow";
import { t } from "@/lib/app-messages";
import { useProfile } from "@/lib/queries";
import { useSession } from "@/lib/use-session";

// Setting up a profile (screen-plan C0). Only a creator without one sees the form: someone who already has a profile goes to Today.
export default function OnboardingPage() {
  const router = useRouter();
  const state = useSession();
  const role = state.status === "signedIn" ? state.session.role : "creator";
  const profile = useProfile(role);
  const exists = profile.data?.found === true;
  // Once the form is sending, the profile appearing is the form's own success: it goes on to Discover, so this does not redirect.
  const [finishing, setFinishing] = useState(false);
  // Only a creator is sent on: brand setup (B0) is not built, so a brand always reads the holding card here, never a redirect after it.
  useEffect(() => { if (role === "creator" && exists && !finishing) router.replace("/app"); }, [role, exists, finishing, router]);

  if (role === "brand") {
    return (
      <Card className="mx-auto grid max-w-lg gap-4 p-8">
        <h1 className="font-display text-2xl font-semibold tracking-tight">{t("onboarding.brandSoon.title")}</h1>
        <p className="text-[15px] leading-6 text-muted">{t("onboarding.brandSoon.body")}</p>
        <ButtonLink href="/app" variant="secondary" className="justify-self-start">{t("next.back")}</ButtonLink>
      </Card>
    );
  }
  if (profile.isError) return <div className="mx-auto max-w-xl"><LoadError title={t("onboarding.errorTitle")} error={profile.error} onRetry={() => void profile.refetch()} /></div>;
  if (profile.isPending || (exists && !finishing)) {
    return (
      <div aria-busy="true" aria-label={t("common.loading")} className="mx-auto grid w-full max-w-xl gap-4 rounded-[1.75rem] bg-surface p-8 shadow-card">
        <Skeleton className="h-2 w-full" /><Skeleton className="h-9 w-1/2" /><Skeleton className="h-12 w-full" /><Skeleton className="h-12 w-full" />
      </div>
    );
  }
  return <OnboardingFlow onFinishing={() => setFinishing(true)} />;
}
