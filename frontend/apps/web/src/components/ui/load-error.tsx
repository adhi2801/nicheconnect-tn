"use client";

import { ApiError, commonWordsKey } from "@/lib/errors";
import { t } from "@/lib/messages";
import { Button } from "./button";
import { Notice } from "./notice";

/** A read that failed: what happened, a way out, and the reference to quote if it keeps happening (frontend.md section 5). */
export function LoadError({ title, error, onRetry }: { title: string; error: unknown; onRetry: () => void }) {
  return (
    <Notice tone="error" action={<Button variant="secondary" className="min-h-10 px-4 text-sm" onClick={onRetry}>{t("common.retry")}</Button>}>
      <p className="font-semibold">{title}</p>
      <p>{t(commonWordsKey(error))}</p>
      {error instanceof ApiError && error.requestId && <p className="mt-1 font-mono text-xs">{t("common.reference", { id: error.requestId })}</p>}
    </Notice>
  );
}
