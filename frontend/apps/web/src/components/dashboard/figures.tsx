"use client";

import { applicantsOf, openDeals } from "@/lib/dashboard";
import { formatPaise } from "@/lib/format";
import { t } from "@/lib/app-messages";
import { useDeals, usePaymentTotals } from "@/lib/queries";
import { Skeleton } from "@/components/ui/skeleton";
import { Figure } from "./panel";
import { useBrandOverview } from "./use-brand-overview";

const Wait = () => <Skeleton className="h-12 w-24" />;
const Row = ({ children }: { children: React.ReactNode }) => <div className="flex flex-wrap gap-x-8 gap-y-5 sm:gap-x-10">{children}</div>;

/** The three figures across the top of a creator's Today. A figure whose call failed says so by being left out, not by being 0. */
export function CreatorFigures() {
  const totals = usePaymentTotals();
  const deals = useDeals();
  return (
    <Row>
      <Figure label={t("dashboard.figures.creator.confirmed")} value={totals.data ? formatPaise(totals.data.finished.amount_paise) : totals.isPending ? <Wait /> : "–"} />
      <Figure label={t("dashboard.figures.creator.onItsWay")} value={totals.data ? formatPaise(totals.data.awaiting_confirmation.amount_paise + totals.data.to_pay.amount_paise) : totals.isPending ? <Wait /> : "–"} />
      <Figure label={t("dashboard.figures.creator.openDeals")} value={deals.data ? openDeals(deals.data) : deals.isPending ? <Wait /> : "–"} />
    </Row>
  );
}

/** The three figures across the top of a brand's Today. */
export function BrandFigures() {
  const totals = usePaymentTotals();
  const deals = useDeals();
  const overview = useBrandOverview();
  return (
    <Row>
      <Figure label={t("dashboard.figures.brand.applicants")} value={overview.loading ? <Wait /> : overview.failedLoad ? "–" : applicantsOf(overview.reports)} />
      <Figure label={t("dashboard.figures.brand.openDeals")} value={deals.data ? openDeals(deals.data) : deals.isPending ? <Wait /> : "–"} />
      <Figure label={t("dashboard.figures.brand.toMark")} value={totals.data ? formatPaise(totals.data.to_pay.amount_paise) : totals.isPending ? <Wait /> : "–"} />
    </Row>
  );
}
