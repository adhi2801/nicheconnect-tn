import type { ReactNode } from "react";

/** A filter or a choice among a few: pressed is the black one (the reference's current tab). A button, so it needs no script to be reachable. */
export function Chip({ pressed, onClick, children, count }: { pressed: boolean; onClick: () => void; children: ReactNode; count?: number }) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      onClick={onClick}
      className={`t-base inline-flex min-h-10 items-center gap-2 rounded-full px-4 text-[13px] font-medium active:scale-[0.98] ${pressed ? "bg-accent text-on-accent" : "bg-surface text-ink shadow-[0_0_0_1px_var(--c-line)] hover:bg-sunk"}`}
    >
      {children}
      {count !== undefined && <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold tabular-nums ${pressed ? "bg-on-accent/20" : "bg-sunk"}`}>{count}</span>}
    </button>
  );
}
