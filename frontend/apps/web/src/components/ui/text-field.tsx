"use client";

import { useId, type InputHTMLAttributes, type ReactNode } from "react";

type Props = Omit<InputHTMLAttributes<HTMLInputElement>, "id"> & {
  label: string;
  hint?: string;
  error?: string;
  /** Fixed text before the input, such as "+91". Part of the field's look, not its value. */
  prefix?: ReactNode;
};

// A visible label, a hint, and an error that is tied to the field and announced (docs/standards/frontend.md section 6).
export function TextField({ label, hint, error, prefix, className = "", ...rest }: Props) {
  const id = useId();
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  const describedBy = [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(" ") || undefined;
  return (
    <div className={`grid gap-1.5 ${className}`}>
      <label htmlFor={id} className="text-sm font-semibold">{label}</label>
      <div className={`t-base flex min-h-12 items-center gap-2 rounded-2xl border bg-surface px-4 focus-within:border-ink focus-within:shadow-[0_0_0_1px_var(--c-ink)] ${error ? "border-bad" : "border-line-strong"}`}>
        {prefix && <span className="select-none text-[15px] text-muted">{prefix}</span>}
        <input id={id} aria-invalid={error ? true : undefined} aria-describedby={describedBy} className="min-h-11 w-full min-w-0 bg-transparent text-[16px] outline-none placeholder:text-muted/70" {...rest} />
      </div>
      {error ? <p id={errorId} className="text-sm text-bad">{error}</p> : hint ? <p id={hintId} className="text-sm text-muted">{hint}</p> : null}
    </div>
  );
}
