"use client";

import { t } from "@/lib/messages";
import type { Filter } from "@/lib/deals";

const FILTERS: Filter[] = ["all", "mine", "theirs"];

/** Show everything, only what needs the person, or only what waits on others. */
export function FilterBar({ value, onChange }: { value: Filter; onChange: (f: Filter) => void }) {
  return (
    <div role="group" aria-label={t("deals.filter.label")} className="inline-flex gap-1 rounded-full bg-sunk p-1">
      {FILTERS.map((f) => (
        <button key={f} type="button" aria-pressed={value === f} onClick={() => onChange(f)} className={`t-base min-h-10 rounded-full px-4 text-sm font-semibold ${value === f ? "bg-ink text-on-accent" : "text-muted hover:text-ink"}`}>
          {t(`deals.filter.${f}`)}
        </button>
      ))}
    </div>
  );
}
