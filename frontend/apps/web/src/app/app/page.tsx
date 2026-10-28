"use client";

import { Button } from "@/components/ui/button";
import { Notice } from "@/components/ui/notice";
import { Reveal } from "@/components/ui/reveal";
import { Skeleton } from "@/components/ui/skeleton";
import { AllClear } from "@/components/today/all-clear";
import { FirstRun } from "@/components/today/first-run";
import { Money } from "@/components/today/money";
import { NeedsYou } from "@/components/today/needs-you";
import { ApiError } from "@/lib/errors";
import { formatLongDate, partOfDay } from "@/lib/format";
import { t } from "@/lib/messages";
import { useAttention, useProfile } from "@/lib/queries";
import { useSession } from "@/lib/use-session";

// Today (frontend/design/screen-plan.md C1 and B1): what needs the person, before anything else.
function errorWords(error: unknown): string {
  if (error instanceof ApiError) return error.kind === "network" ? t("common.offline") : error.kind === "busy" ? t("common.busy") : t("common.somethingWrong");
  return t("common.somethingWrong");
}

export default function TodayPage() {
  const state = useSession();
  const role = state.status === "signedIn" ? state.session.role : "creator";
  const profile = useProfile(role);
  const attention = useAttention();
  const name = profile.data?.found ? profile.data.name : null;
  const noProfile = profile.data?.found === false;
  const data = attention.data;
  const count = data?.total ?? 0;
  const hasItems = !!data && data.items.length > 0;

  return (
    <div className="grid gap-8">
      <Reveal>
        <header className="grid gap-2">
          <p className="text-sm font-medium text-muted">{data ? formatLongDate(data.as_of) : <Skeleton className="h-5 w-40" />}</p>
          <h1 className="font-display text-[2rem] font-semibold leading-[1.1] tracking-tight sm:text-5xl">
            {name ? t(`today.greeting.${partOfDay()}`, { name }) : noProfile ? t("today.greeting.welcome") : <Skeleton className="h-10 w-3/4 max-w-md" />}
          </h1>
          {!noProfile && <p className="text-[17px] text-muted">{data ? t(count === 0 ? "today.summary.none" : count === 1 ? "today.summary.one" : "today.summary.other", { count }) : ""}</p>}
        </header>
      </Reveal>

      {noProfile && <Reveal index={1}><FirstRun role={role} /></Reveal>}

      {/* Before a profile exists there are no payments and nothing is "all clear", so only a waiting item (a sign-in to check) shows. */}
      {!(noProfile && !hasItems) && (
        <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,22rem)]">
          <Reveal index={2}>
            {attention.isPending ? (
              <div aria-busy="true" className="grid gap-3 rounded-3xl bg-ink p-6"><Skeleton className="h-8 w-1/3 bg-white/10" /><Skeleton className="h-24 bg-white/10" /><Skeleton className="h-24 bg-white/10" /></div>
            ) : attention.isError ? (
              <Notice tone="error" action={<Button variant="secondary" className="min-h-10 px-4 text-sm" onClick={() => void attention.refetch()}>{t("common.retry")}</Button>}>
                <p className="font-semibold">{t("today.errorTitle")}</p>
                <p>{errorWords(attention.error)}</p>
                {attention.error instanceof ApiError && attention.error.requestId && <p className="mt-1 font-mono text-xs">{t("common.reference", { id: attention.error.requestId })}</p>}
              </Notice>
            ) : data && hasItems ? (
              <NeedsYou items={data.items} total={data.total} truncated={data.truncated} role={role} />
            ) : (
              <AllClear role={role} />
            )}
          </Reveal>
          {!noProfile && <Reveal index={3} className="lg:sticky lg:top-6"><Money role={role} /></Reveal>}
        </div>
      )}
    </div>
  );
}
