import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import type { components } from "@colyv/api";
import { api } from "./api";
import { IntentKeys, sendWrite } from "./writes";

// The journey's three writes. Each sends an Idempotency-Key tied to its intent (lib/writes.ts): a double tap, a retry after a dropped
// connection or a busy backend all reuse the key, so the backend applies the write once. Retries of a busy backend happen inside
// sendWrite; the query library itself never retries a write.

/** One IntentKeys per form, made once and kept for as long as the form is on screen. */
const useIntent = () => useState(() => new IntentKeys())[0];

export function useCreateProfile() {
  const client = useQueryClient();
  const keys = useIntent();
  return useMutation({
    retry: false,
    mutationFn: (body: components["schemas"]["CreatorProfileCreate"]) =>
      sendWrite(() => api.POST("/api/v1/creators/me", { params: { header: { "Idempotency-Key": keys.keyFor(body) } }, body })),
    onSuccess: async () => {
      keys.done();
      await Promise.all([client.invalidateQueries({ queryKey: ["profile"] }), client.invalidateQueries({ queryKey: ["attention"] })]);
    },
  });
}

export function useApply(campaignId: string) {
  const client = useQueryClient();
  const keys = useIntent();
  return useMutation({
    retry: false,
    mutationFn: (body: components["schemas"]["ApplicationCreate"]) =>
      sendWrite(() => api.POST("/api/v1/campaigns/{campaign_id}/applications", { params: { path: { campaign_id: campaignId }, header: { "Idempotency-Key": keys.keyFor({ campaignId, body }) } }, body })),
    onSuccess: async () => {
      keys.done();
      await Promise.all(["my-applications", "application-feedback", "discover", "campaign"].map((k) => client.invalidateQueries({ queryKey: [k] })));
    },
  });
}

export function useWithdraw() {
  const client = useQueryClient();
  const keys = useIntent();
  return useMutation({
    retry: false,
    mutationFn: (applicationId: string) =>
      sendWrite(() => api.POST("/api/v1/applications/{application_id}/withdraw", { params: { path: { application_id: applicationId }, header: { "Idempotency-Key": keys.keyFor({ withdraw: applicationId }) } } })),
    onSuccess: async () => {
      keys.done();
      await Promise.all(["my-applications", "application-feedback", "attention"].map((k) => client.invalidateQueries({ queryKey: [k] })));
    },
  });
}
