"use client";

import { useId } from "react";
import { CheckIcon } from "@/components/ui/icons";
import { t } from "@/lib/app-messages";
import { MAX_NICHES, NICHES, toggleNiche, type Niche } from "@/lib/onboarding";

/** Up to five niches as toggle chips. Each chip is a real button with aria-pressed, so a screen reader says chosen or not. */
export function NichePicker({ value, onChange, error }: { value: Niche[]; onChange: (next: Niche[]) => void; error?: string }) {
  const id = useId();
  const full = value.length >= MAX_NICHES;
  return (
    <div role="group" data-invalid={error ? "true" : undefined} aria-labelledby={`${id}-legend`} aria-describedby={`${id}-status${error ? ` ${id}-error` : ""}`} className="grid gap-2">
      <p id={`${id}-legend`} className="text-sm font-semibold">{t("onboarding.niches.legend")}</p>
      <p className="text-sm text-muted">{t("onboarding.niches.hint")}</p>
      <ul className="flex flex-wrap gap-2">
        {NICHES.map((niche) => {
          const on = value.includes(niche);
          return (
            <li key={niche}>
              <button
                type="button"
                aria-pressed={on}
                disabled={!on && full}
                onClick={() => onChange(toggleNiche(value, niche))}
                className={`t-base inline-flex min-h-11 items-center gap-1.5 rounded-full border px-4 text-[15px] font-semibold disabled:cursor-not-allowed disabled:opacity-45 ${on ? "border-ink bg-ink text-on-accent" : "border-line-strong bg-surface hover:bg-sunk"}`}
              >
                {on && <CheckIcon width={16} height={16} aria-hidden />}
                {t(`niches.${niche}`)}
              </button>
            </li>
          );
        })}
      </ul>
      <p id={`${id}-status`} aria-live="polite" className="text-sm text-muted">{full ? t("onboarding.niches.full") : t("onboarding.niches.count", { count: value.length })}</p>
      {error && <p id={`${id}-error`} className="text-sm text-bad">{error}</p>}
    </div>
  );
}
