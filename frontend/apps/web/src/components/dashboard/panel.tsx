import Link from "next/link";
import type { ReactNode } from "react";
import { ArrowUpRightIcon } from "@/components/ui/icons";

// The dashboard's card (HD-007): a white rounded panel, with a sage and a dark variant, a title, and the reference's round lime arrow
// button as its one link ("see all").
type Tone = "light" | "sage" | "dark";
const TONES: Record<Tone, string> = {
  light: "bg-surface text-ink shadow-card",
  sage: "bg-sage text-ink shadow-[0_0_0_1px_var(--c-line)]",
  dark: "hero on-dark",
};

export function Panel({ title, action, aside, tone = "light", id, className = "", children }: { title: string; action?: { href: string; label: string }; aside?: ReactNode; tone?: Tone; id?: string; className?: string; children: ReactNode }) {
  const heading = `${id ?? title.replace(/\W+/g, "-")}-title`;
  return (
    <section id={id} aria-labelledby={heading} className={`grid content-start gap-5 rounded-[2rem] p-5 sm:p-6 ${TONES[tone]} ${className}`}>
      <div className="flex items-center justify-between gap-4">
        <h2 id={heading} className="text-[15px] font-medium">{title}</h2>
        {aside}
        {action && (
          <Link href={action.href} aria-label={action.label} title={action.label} className="t-base inline-flex size-10 shrink-0 items-center justify-center rounded-full bg-lime text-on-lime hover:brightness-95">
            <ArrowUpRightIcon width={18} height={18} />
          </Link>
        )}
      </div>
      {children}
    </section>
  );
}

/** A big, light figure with its small label under it (the reference's "94 Employer"). */
export function Figure({ value, label, className = "" }: { value: ReactNode; label: string; className?: string }) {
  return (
    <div className={`grid gap-1.5 ${className}`}>
      <p className="type-figure text-[2rem] sm:text-[2.75rem]">{value}</p>
      <p className="text-[13px] text-muted">{label}</p>
    </div>
  );
}

/** A person as their initials in a circle: no photographs (D-142). */
export function Avatar({ name, className = "" }: { name: string; className?: string }) {
  const letters = name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => [...w][0] ?? "").join("").toUpperCase();
  return <span aria-hidden className={`grid size-10 shrink-0 place-items-center rounded-full bg-sage text-[13px] font-semibold text-ink ${className}`}>{letters}</span>;
}
