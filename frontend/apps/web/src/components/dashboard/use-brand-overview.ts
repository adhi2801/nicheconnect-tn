"use client";

import { useMemo } from "react";
import { ongoing } from "@/lib/dashboard";
import { useCampaignReports, useMyCampaigns } from "@/lib/queries";

/** The brand's ongoing campaigns and each one's report, read once and shared by every card that needs them (the cache dedupes the reads). */
export function useBrandOverview() {
  const campaigns = useMyCampaigns();
  const list = useMemo(() => (campaigns.data ? ongoing(campaigns.data) : []), [campaigns.data]);
  const { reports, pending, failed } = useCampaignReports(list.map((c) => c.id));
  return {
    list,
    reports,
    byId: useMemo(() => new Map(reports.map((r) => [r.campaign_id, r])), [reports]),
    loading: campaigns.isPending || (list.length > 0 && pending),
    failedLoad: campaigns.isError,
    failedReports: failed,
  };
}
