"use client";

import { useId, type TextareaHTMLAttributes } from "react";

type Props = Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, "id"> & {
  label: string;
  hint?: string;
  error?: string;
  /** A live count, such as "120 of 1,000 characters". Announced politely, so a screen reader hears it without being interrupted. */
  counter?: string;
};

// The multi-line twin of TextField: a visible label, a hint, an error tied to the field and announced (frontend.md section 6).
export function TextAreaField({ label, hint, error, counter, className = "", rows = 6, ...rest }: Props) {
  const id = useId();
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  const counterId = `${id}-counter`;
  const describedBy = [hint ? hintId : null, error ? errorId : null, counter ? counterId : null].filter(Boolean).join(" ") || undefined;
  return (
    <div className={`grid gap-1.5 ${className}`}>
      <label htmlFor={id} className="text-sm font-semibold">{label}</label>
      {hint && <p id={hintId} className="text-sm text-muted">{hint}</p>}
      <textarea
        id={id}
        rows={rows}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        className={`field-control t-base w-full resize-y rounded-2xl border bg-surface px-4 py-3 text-[16px] leading-6 outline-none focus:border-ink focus:shadow-[0_0_0_1px_var(--c-ink)] ${error ? "border-bad" : "border-line-strong"}`}
        {...rest}
      />
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-1">
        {error ? <p id={errorId} className="text-sm text-bad">{error}</p> : <span />}
        {counter && <p id={counterId} aria-live="polite" className="text-sm tabular-nums text-muted">{counter}</p>}
      </div>
    </div>
  );
}
