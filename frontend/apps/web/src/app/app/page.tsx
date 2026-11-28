"use client";

import { BrandFigures, CreatorFigures } from "@/components/dashboard/figures";
import { BrandToday } from "@/components/dashboard/brand-today";
import { CreatorToday } from "@/components/dashboard/creator-today";
import { FirstRun } from "@/components/today/first-run";
import { Reveal } from "@/components/ui/reveal";
import { Skeleton } from "@/components/ui/skeleton";
import { formatLongDate, partOfDay } from "@/lib/format";
import { t } from "@/lib/app-messages";
import { useAttention, useProfile } from "@/lib/queries";
import { useSession } from "@/lib/use-session";

// Today (frontend/design/screen-plan.md C1 and B1, in the look of HD-007 and D-203; the cards are frontend/design/dashboard-plan.md):
// what needs the person, before anything else, then how their collaborations are going. One page for both roles.
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
    <div className="grid gap-8 lg:gap-10">
      <Reveal>
        <header className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end">
          <div className="grid gap-2">
            <p className="text-sm font-medium text-muted">{data ? formatLongDate(data.as_of) : <Skeleton className="h-5 w-40" />}</p>
            <h1 className="type-title">
              {name ? t(`today.greeting.${partOfDay()}`, { name }) : noProfile ? t("today.greeting.welcome") : <Skeleton className="h-12 w-3/4 max-w-md" />}
            </h1>
            {!noProfile && <p className="text-base text-muted">{data ? t(count === 0 ? "today.summary.none" : count === 1 ? "today.summary.one" : "today.summary.other", { count }) : ""}</p>}
          </div>
          {!noProfile && (role === "creator" ? <CreatorFigures /> : <BrandFigures />)}
        </header>
      </Reveal>

      {noProfile && <Reveal index={1}><FirstRun role={role} /></Reveal>}

      {/* Before a profile exists there are no payments and nothing to show beyond a waiting item (a sign-in to check). */}
      {!(noProfile && !hasItems) && <Reveal index={2}>{role === "creator" ? <CreatorToday attention={attention} /> : <BrandToday attention={attention} />}</Reveal>}
    </div>
  );
}
