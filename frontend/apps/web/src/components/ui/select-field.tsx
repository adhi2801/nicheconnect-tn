"use client";

import { useId, type SelectHTMLAttributes } from "react";

type Props = Omit<SelectHTMLAttributes<HTMLSelectElement>, "id"> & { label: string; options: { value: string; label: string }[] };

// A native select: the phone's own picker, keyboard and screen reader support for free. The first option is "any".
export function SelectField({ label, options, className = "", ...rest }: Props) {
  const id = useId();
  return (
    <div className={`grid gap-1.5 ${className}`}>
      <label htmlFor={id} className="text-sm font-semibold">{label}</label>
      <select id={id} className="field-control t-base min-h-12 w-full rounded-2xl border border-line-strong bg-surface px-4 text-[16px] outline-none focus:border-ink focus:shadow-[0_0_0_1px_var(--c-ink)]" {...rest}>
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </div>
  );
}
