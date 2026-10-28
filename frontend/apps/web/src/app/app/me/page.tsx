"use client";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { initials } from "@/lib/format";
import { t } from "@/lib/messages";
import { useProfile } from "@/lib/queries";
import { signOut } from "@/lib/session";
import { useSession } from "@/lib/use-session";

// The start of the account screen (frontend/design/screen-plan.md C14). Only signing out exists so far.
export default function MePage() {
  const state = useSession();
  const role = state.status === "signedIn" ? state.session.role : "creator";
  const profile = useProfile(role);
  const name = profile.data?.found ? profile.data.name : null;
  return (
    <Card className="mx-auto grid max-w-lg gap-6 p-8">
      <div className="flex items-center gap-4">
        <span aria-hidden className="grid size-14 place-items-center rounded-full bg-ink font-display text-lg font-semibold text-on-accent">{name ? initials(name) : ""}</span>
        <div className="min-w-0">
          <h1 className="truncate font-display text-2xl font-semibold tracking-tight">{name ?? t("me.title")}</h1>
          <p className="text-sm text-muted">{t("me.signedInAs", { role })}</p>
        </div>
      </div>
      <Button variant="secondary" onClick={() => void signOut()}>{t("me.signOut")}</Button>
    </Card>
  );
}
