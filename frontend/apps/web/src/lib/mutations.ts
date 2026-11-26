import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import type { components } from "@colyv/api";
import { api } from "./api";
import { ApiError } from "./errors";
import { IntentKeys, sendWrite, sendWriteWithStatus } from "./writes";

// The journey's three writes. Each sends an Idempotency-Key tied to its intent (lib/writes.ts): a double tap, a retry after a dropped
// connection or a busy backend all reuse the key, so the backend applies the write once. Retries of a busy backend happen inside
// sendWrite; the query library itself never retries a write.

/** One IntentKeys per form, made once and kept for as long as the form is on screen. A caller may hold it longer (the campaign page
 *  holds Apply's, so closing and reopening the sheet keeps the key). It lives in memory: a reload starts a new intent, and the
 *  backend's already_applied answer covers that case. */
export const useIntentKeys = () => useState(() => new IntentKeys())[0];

export function useCreateProfile() {
  const client = useQueryClient();
  const keys = useIntentKeys();
  return useMutation({
    retry: false,
    mutationFn: (body: components["schemas"]["CreatorProfileCreate"]) =>
      sendWrite((signal) => api.POST("/api/v1/creators/me", { params: { header: { "Idempotency-Key": keys.keyFor(body) } }, body, signal })),
    onSuccess: async () => {
      keys.done();
      await Promise.all([client.invalidateQueries({ queryKey: ["profile"] }), client.invalidateQueries({ queryKey: ["attention"] })]);
    },
  });
}

export function useApply(campaignId: string, keys: IntentKeys) {
  const client = useQueryClient();
  return useMutation({
    retry: false,
    mutationFn: (body: components["schemas"]["ApplicationCreate"]) =>
      sendWrite((signal) => api.POST("/api/v1/campaigns/{campaign_id}/applications", { params: { path: { campaign_id: campaignId }, header: { "Idempotency-Key": keys.keyFor({ campaignId, body }) } }, body, signal })),
    onSuccess: async () => {
      keys.done();
      await Promise.all(["my-applications", "application-feedback", "discover", "campaign"].map((k) => client.invalidateQueries({ queryKey: [k] })));
    },
    // Already applied (say, from another tab, or a send whose answer was lost before a reload): fetch the list again, so the page
    // shows that application instead of offering Apply.
    onError: async (error) => {
      if (error instanceof ApiError && error.code === "already_applied") await client.invalidateQueries({ queryKey: ["my-applications"] });
    },
  });
}

export function useWithdraw() {
  const client = useQueryClient();
  const keys = useIntentKeys();
  return useMutation({
    retry: false,
    mutationFn: (applicationId: string) =>
      sendWrite((signal) => api.POST("/api/v1/applications/{application_id}/withdraw", { params: { path: { application_id: applicationId }, header: { "Idempotency-Key": keys.keyFor({ withdraw: applicationId }) } }, signal })),
    onSuccess: async () => {
      keys.done();
      await Promise.all(["my-applications", "application-feedback", "attention"].map((k) => client.invalidateQueries({ queryKey: [k] })));
    },
  });
}

/** A report: answered 201 when new, 200 with the open one when the same thing was already reported (the screen says which). */
export function useReport() {
  const keys = useIntentKeys();
  return useMutation({
    retry: false,
    mutationFn: async (body: components["schemas"]["ReportCreate"]) => {
      const { status } = await sendWriteWithStatus((signal) => api.POST("/api/v1/reports", { params: { header: { "Idempotency-Key": keys.keyFor(body) } }, body, signal }));
      return { alreadyOpen: status === 200 };
    },
    onSuccess: () => keys.done(),
  });
}

/** A creator blocks a brand. The brand is never told. Everything the brand had shown this creator is read again, and now refused. */
export function useBlockBrand() {
  const client = useQueryClient();
  const keys = useIntentKeys();
  return useMutation({
    retry: false,
    mutationFn: (brandId: string) => {
      const body = { brand_id: brandId };
      return sendWrite((signal) => api.POST("/api/v1/me/blocks", { params: { header: { "Idempotency-Key": keys.keyFor(body) } }, body, signal }));
    },
    onSuccess: () => {
      keys.done();
      // Read again in the background, not awaited: the screen that blocked moves on at once. The open campaign is only marked stale,
      // not re-read here, or its "not found" would replace the page before the screen could move on.
      void Promise.all(["discover", "reliability", "my-applications"].map((k) => client.invalidateQueries({ queryKey: [k] })));
      void client.invalidateQueries({ queryKey: ["campaign"], refetchType: "none" });
    },
  });
}
