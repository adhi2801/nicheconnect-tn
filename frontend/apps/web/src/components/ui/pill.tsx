import type { ReactNode } from "react";
import { AlertIcon, CheckIcon, ClockIcon, DotIcon } from "./icons";

export type Tone = "ok" | "warn" | "bad" | "neutral" | "dark";

const tones: Record<Tone, { cls: string; icon: ReactNode }> = {
  ok: { cls: "bg-ok-soft text-ok", icon: <CheckIcon width={14} height={14} /> },
  warn: { cls: "bg-warn-soft text-warn", icon: <ClockIcon width={14} height={14} /> },
  bad: { cls: "bg-bad-soft text-bad", icon: <AlertIcon width={14} height={14} /> },
  neutral: { cls: "bg-surface text-muted ring-1 ring-line", icon: <DotIcon width={14} height={14} /> },
  dark: { cls: "bg-ink text-on-accent", icon: <DotIcon width={14} height={14} className="text-highlight" /> },
};

// A status always carries a word and an icon, never colour alone (docs/standards/frontend.md section 6).
export function Pill({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  const { cls, icon } = tones[tone];
  return (
    <span className={`inline-flex min-h-6 items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 text-xs font-semibold ${cls}`}>
      {icon}
      {children}
    </span>
  );
}
