"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { LoadError } from "@/components/ui/load-error";
import { Notice } from "@/components/ui/notice";
import { Reveal } from "@/components/ui/reveal";
import { Skeleton } from "@/components/ui/skeleton";
import { CampaignCard } from "@/components/discover/campaign-card";
import { DiscoverFilters } from "@/components/discover/discover-filters";
import { DiscoverTabs } from "@/components/discover/discover-tabs";
import { Kolam } from "@/components/today/kolam";
import { activeFilterCount, filtersFrom, filtersToSearch, type Filters } from "@/lib/campaigns";
import { t } from "@/lib/app-messages";
import { useCities, useDiscover, useMyApplications } from "@/lib/queries";

const SkeletonCards = () => (
  <div aria-busy="true" aria-label={t("common.loading")} className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
    {[0, 1, 2, 3, 4, 5].map((i) => <Skeleton key={i} className="h-60 rounded-3xl" />)}
  </div>
);

// Discover (screen-plan C2): open campaigns, with pay and terms before anything else. Two calls: the campaigns, and the creator's own
// applications (to mark what was applied to); the second is shared with every other screen of the journey.
function DiscoverBody() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const filters = useMemo(() => filtersFrom(params), [params]);
  const discover = useDiscover(filters);
  const mine = useMyApplications();
  const [wantCities, setWantCities] = useState(false);
  const cities = useCities(wantCities);
  // What the creator already has on each campaign: an application they sent, or an invitation from the brand.
  const yours = useMemo(() => new Map((mine.data ?? []).filter((a) => a.status !== "withdrawn").map((a) => [a.campaign_id, a.origin === "invited" ? ("invited" as const) : ("applied" as const)])), [mine.data]);
  const campaigns = discover.data?.pages.flatMap((p) => p.items) ?? [];
  const filtered = activeFilterCount(filters) > 0;
  // Shown once: the address loses ?blocked=1 at once, so a reload or Back does not show it again.
  const [justBlocked] = useState(() => params.get("blocked") === "1");
  useEffect(() => { if (params.has("blocked")) router.replace(`${pathname}${filtersToSearch(filters)}`, { scroll: false }); }, [params, pathname, filters, router]);

  const apply = (next: Filters) => router.replace(`${pathname}${filtersToSearch(next)}`, { scroll: false });

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-6 lg:gap-7">
      <Reveal>
        <header className="grid gap-4">
          <div className="grid gap-1.5">
            <h1 className="font-display text-[2rem] font-semibold leading-[1.1] tracking-tight sm:text-[2.5rem]">{t("discover.title")}</h1>
            <p className="max-w-[60ch] text-base text-muted">{t("discover.subtitle")}</p>
          </div>
          <DiscoverTabs current="open" />
        </header>
      </Reveal>

      {justBlocked && <div aria-live="polite"><Notice><p>{t("safety.block.done")}</p></Notice></div>}

      <Reveal index={1}>
        {/* Keyed by the filters, so the form resets to the address after back or forward. */}
        <DiscoverFilters key={filtersToSearch(filters)} value={filters} cities={(cities.data ?? []).map((c) => c.city)} onApply={apply} onCityFocus={() => setWantCities(true)} />
      </Reveal>

      <Reveal index={2}>
        <section aria-label={t("discover.tabs.open")} aria-busy={discover.isFetching || undefined} className="grid gap-5">
          {discover.isPending ? (
            <SkeletonCards />
          ) : discover.isError ? (
            <LoadError title={t("discover.errorTitle")} error={discover.error} onRetry={() => void discover.refetch()} />
          ) : campaigns.length === 0 ? (
            <Card className="grid justify-items-start gap-5 p-6 sm:p-8">
              <Kolam />
              <div className="grid gap-2">
                <h2 className="font-display text-2xl font-semibold tracking-tight">{t(filtered ? "discover.empty.filteredTitle" : "discover.empty.noneTitle")}</h2>
                <p className="max-w-[52ch] text-[15px] leading-6 text-muted">{t(filtered ? "discover.empty.filteredBody" : "discover.empty.noneBody")}</p>
              </div>
              {filtered && <Button variant="secondary" onClick={() => apply({})}>{t("discover.filters.clear")}</Button>}
            </Card>
          ) : (
            <>
              <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                {campaigns.map((c) => <li key={c.id}><CampaignCard campaign={c} yours={yours.get(c.id) ?? null} /></li>)}
              </ul>
              {discover.isFetchNextPageError && <Notice tone="error"><p>{t("discover.moreError")}</p></Notice>}
              {discover.hasNextPage ? (
                <Button variant="secondary" className="justify-self-center" loading={discover.isFetchingNextPage} onClick={() => void discover.fetchNextPage()}>
                  {discover.isFetchingNextPage ? t("discover.loadingMore") : t("discover.more")}
                </Button>
              ) : (
                <p className="text-center text-sm text-muted">{t("discover.end")}</p>
              )}
            </>
          )}
        </section>
      </Reveal>
    </div>
  );
}

export default function DiscoverPage() {
  // useSearchParams needs a Suspense boundary (Next.js 16, use-search-params.md, "Prerendering").
  return (
    <Suspense fallback={<SkeletonCards />}>
      <DiscoverBody />
    </Suspense>
  );
}
