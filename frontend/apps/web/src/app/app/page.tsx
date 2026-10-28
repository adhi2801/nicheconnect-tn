"use client";

import { useEffect, useSyncExternalStore } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { t } from "@/lib/messages";
import { endSession, getSession, subscribeToSession } from "@/lib/session";

// Where sign-in lands for now. The Today screen replaces this (docs/design/screen-plan.md C1 and B1).
export default function SignedInPage() {
  const router = useRouter();
  // The server never has a session, so it renders the skeleton; the browser then reads the in-memory one.
  const session = useSyncExternalStore(subscribeToSession, getSession, () => null);

  useEffect(() => {
    if (!getSession()) router.replace("/sign-in");
  }, [router]);

  async function signOut() {
    const s = getSession();
    endSession();
    if (s) await api.POST("/api/v1/auth/logout", { body: { refresh_token: s.refreshToken } }).catch(() => undefined);
    router.replace("/sign-in");
  }

  return (
    <main className="mx-auto flex w-full max-w-[480px] flex-1 flex-col justify-center gap-6 px-5 py-12">
      {!session ? (
        <Card className="grid gap-3" aria-busy="true" aria-label={t("common.loading")}><Skeleton className="h-6 w-2/3" /><Skeleton className="h-4 w-full" /></Card>
      ) : (
        <Card className="grid gap-4">
          <h1 className="font-display text-2xl font-semibold tracking-tight">{t("home.signedInAs", { role: session.role })}</h1>
          <p className="text-[15px] leading-6 text-muted">{t("home.soon")}</p>
          <Button variant="secondary" onClick={signOut}>{t("home.signOut")}</Button>
        </Card>
      )}
    </main>
  );
}
