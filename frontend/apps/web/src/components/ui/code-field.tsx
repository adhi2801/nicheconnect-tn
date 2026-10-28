"use client";

import { useId, useRef, useState } from "react";

type Props = { label: string; value: string; onChange: (digits: string) => void; length?: number; error?: string; autoFocus?: boolean; disabled?: boolean };

// Six boxes drawn over ONE real input. Autofill from the phone's messages, paste, the numeric keyboard and screen readers
// all keep working because the input is real; the boxes only show it (docs/standards/frontend.md sections 6 and 7).
export function CodeField({ label, value, onChange, length = 6, error, autoFocus, disabled }: Props) {
  const id = useId();
  const errorId = `${id}-error`;
  const ref = useRef<HTMLInputElement>(null);
  const [focused, setFocused] = useState(false);
  return (
    <div className="grid gap-2">
      <label htmlFor={id} className="text-sm font-semibold">{label}</label>
      <div className="relative" onClick={() => ref.current?.focus()}>
        <div aria-hidden className="grid grid-cols-6 gap-2 sm:gap-3">
          {Array.from({ length }, (_, i) => {
            const active = focused && i === Math.min(value.length, length - 1);
            return (
              <div key={i} className={`t-base flex h-14 items-center justify-center rounded-2xl border bg-surface font-mono text-2xl font-medium sm:h-16 ${error ? "border-bad" : active ? "border-ink shadow-[0_0_0_1px_var(--c-ink)]" : "border-line-strong"}`}>
                {value[i] ?? ""}
              </div>
            );
          })}
        </div>
        <input
          ref={ref}
          id={id}
          value={value}
          onChange={(e) => onChange(e.target.value.replace(/\D/g, "").slice(0, length))}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          inputMode="numeric"
          autoComplete="one-time-code"
          pattern="[0-9]*"
          maxLength={length}
          autoFocus={autoFocus}
          disabled={disabled}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? errorId : undefined}
          className="absolute inset-0 size-full cursor-text opacity-0"
        />
      </div>
      {error && <p id={errorId} className="text-sm text-bad">{error}</p>}
    </div>
  );
}
