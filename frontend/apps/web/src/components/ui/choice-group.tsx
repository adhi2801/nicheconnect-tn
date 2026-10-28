"use client";

import { useId, type ReactNode } from "react";

export type Choice<T extends string> = { value: T; title: string; hint: string; icon?: ReactNode };

type Props<T extends string> = { legend: string; name?: string; value: T; onChange: (v: T) => void; choices: Choice<T>[] };

// Radio buttons that look like two large cards. Real radios underneath: arrow keys and screen readers work.
export function ChoiceGroup<T extends string>({ legend, name, value, onChange, choices }: Props<T>) {
  const group = useId();
  return (
    <fieldset className="grid gap-2">
      <legend className="mb-1 text-sm font-semibold">{legend}</legend>
      <div className="grid gap-3 sm:grid-cols-2">
        {choices.map((c) => {
          const checked = c.value === value;
          return (
            <label key={c.value} className={`t-base relative grid cursor-pointer gap-1 rounded-2xl border p-4 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-ink ${checked ? "border-ink bg-surface shadow-[0_0_0_1px_var(--c-ink)]" : "border-line-strong bg-surface/60 hover:bg-surface"}`}>
              <input type="radio" name={name ?? group} value={c.value} checked={checked} onChange={() => onChange(c.value)} className="sr-only" />
              <span className="flex items-center justify-between gap-2 text-[15px] font-semibold">
                {c.title}
                <span aria-hidden className={`t-base grid size-5 place-items-center rounded-full border ${checked ? "border-ink bg-ink" : "border-line-strong"}`}>
                  {checked && <span className="size-2 rounded-full bg-highlight" />}
                </span>
              </span>
              <span className="text-sm leading-5 text-muted">{c.hint}</span>
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}
