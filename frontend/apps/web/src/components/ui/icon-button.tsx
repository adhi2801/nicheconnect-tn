import Link from "next/link";
import type { ComponentProps, ReactNode } from "react";

type Props = Omit<ComponentProps<typeof Link>, "children" | "aria-label"> & { label: string; children: ReactNode; badge?: ReactNode; tone?: "light" | "dark" };

// A circular icon link: 44 px, soft, with a name for screen readers. Used for the bell and the arrow on a figure card.
export function IconButton({ label, children, badge, tone = "light", className = "", ...rest }: Props) {
  const look = tone === "dark" ? "bg-white/15 text-on-accent hover:bg-white/25" : "bg-surface text-ink shadow-card hover:bg-sunk";
  return (
    <Link aria-label={label} className={`t-base relative grid size-11 shrink-0 place-items-center rounded-full ${look} ${className}`} {...rest}>
      {children}
      {badge}
    </Link>
  );
}
