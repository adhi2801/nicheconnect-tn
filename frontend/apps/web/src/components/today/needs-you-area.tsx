"use client";

import type { UseQueryResult } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Notice } from "@/components/ui/notice";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/errors";
import { t } from "@/lib/messages";
import type { Role } from "@/lib/session";
import type { AttentionItem } from "@/lib/attention";
import { AllClear } from "./all-clear";
import { NeedsYou } from "./needs-you";

export type Attention = { items: AttentionItem[]; total: number; truncated: boolean };

function errorWords(error: unknown): string {
  if (error instanceof ApiError) return error.kind === "network" ? t("common.offline") : error.kind === "busy" ? t("common.busy") : t("common.somethingWrong");
  return t("common.somethingWrong");
}

/** The dark "Needs you" card, or its loading, failed or all-clear state. */
export function NeedsYouArea({ attention, role }: { attention: UseQueryResult<Attention>; role: Role }) {
  const data = attention.data;
  if (attention.isPending) return <div aria-busy="true" className="grid gap-3 rounded-[2rem] bg-sunk p-6"><Skeleton className="h-8 w-1/3 bg-line" /><Skeleton className="h-24 bg-line" /><Skeleton className="h-24 bg-line" /></div>;
  if (attention.isError) {
    return (
      <Notice tone="error" action={<Button variant="secondary" className="min-h-10 px-4 text-sm" onClick={() => void attention.refetch()}>{t("common.retry")}</Button>}>
        <p className="font-semibold">{t("today.errorTitle")}</p>
        <p>{errorWords(attention.error)}</p>
        {attention.error instanceof ApiError && attention.error.requestId && <p className="mt-1 font-mono text-xs">{t("common.reference", { id: attention.error.requestId })}</p>}
      </Notice>
    );
  }
  return data && data.items.length > 0 ? <NeedsYou items={data.items} total={data.total} truncated={data.truncated} role={role} /> : <AllClear role={role} />;
}
