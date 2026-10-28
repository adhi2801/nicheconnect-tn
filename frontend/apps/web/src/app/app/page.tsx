"use client";

import { useEffect, useSyncExternalStore } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { t } from "@/lib/messages";
import { getServerSessionState, getSessionState, restoreSession, signOut, subscribeToSession } from "@/lib/session";

// Where sign-in lands for now. The Today screen replaces this (frontend/design/screen-plan.md C1 and B1).
export default function SignedInPage() {
  const router = useRouter();
  const state = useSyncExternalStore(subscribeToSession, getSessionState, getServerSessionState);

  useEffect(() => { void restoreSession(); }, []);
  useEffect(() => { if (state.status === "signedOut") router.replace("/sign-in"); }, [state.status, router]);

  return (
    <main className="mx-auto flex w-full max-w-[480px] flex-1 flex-col justify-center gap-6 px-5 py-12">
      {state.status !== "signedIn" ? (
        <Card className="grid gap-3" aria-busy="true" aria-label={t("common.loading")}><Skeleton className="h-6 w-2/3" /><Skeleton className="h-4 w-full" /></Card>
      ) : (
        <Card className="grid gap-4">
          <h1 className="font-display text-2xl font-semibold tracking-tight">{t("home.signedInAs", { role: state.session.role })}</h1>
          <p className="text-[15px] leading-6 text-muted">{t("home.soon")}</p>
          <Button variant="secondary" onClick={() => void signOut()}>{t("home.signOut")}</Button>
        </Card>
      )}
    </main>
  );
}
