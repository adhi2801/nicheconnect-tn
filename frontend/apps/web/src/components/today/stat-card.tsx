import Link from "next/link";
import type { ReactNode } from "react";
import { ArrowUpRightIcon } from "@/components/ui/icons";
import { t } from "@/lib/messages";

type Props = { tone?: "light" | "hero"; label: string; value: ReactNode; foot?: ReactNode; href: string; wide?: boolean };

/** One figure, large, with a short line beneath and an arrow to where it lives. The hero card is the deep-green one. */
export function StatCard({ tone = "light", label, value, foot, href, wide = false }: Props) {
  const hero = tone === "hero";
  return (
    // The wrapper is a size container: the figure scales with the card it is in, so a lakh never spills past the edge.
    <div className={`@container min-w-0 ${wide ? "col-span-2 sm:col-span-1" : ""}`}>
      <div className={`grid h-full content-between gap-5 rounded-3xl p-4 sm:gap-6 sm:p-5 ${hero ? "hero on-dark" : "bg-surface shadow-card"}`}>
        <div className="flex items-start justify-between gap-3">
          <p className="text-[15px] font-medium leading-snug">{label}</p>
          <Link href={href} aria-label={t("today.stats.open", { label })} className={`t-base grid size-9 shrink-0 place-items-center rounded-full ${hero ? "bg-surface text-ink hover:bg-highlight" : "border border-line-strong hover:bg-sunk"}`}>
            <ArrowUpRightIcon width={16} height={16} />
          </Link>
        </div>
        <div className="grid gap-2.5">
          <p className="font-display text-2xl font-medium leading-none tracking-tight tabular-nums @[10rem]:text-[1.75rem] @[13rem]:text-[2.25rem] @[16rem]:text-[2.5rem]">{value}</p>
          {/* A fixed height, so the figures line up across the row whether or not a card has a pill. */}
          <div className={`min-h-[2.75rem] text-sm ${hero ? "text-on-accent/80" : "text-muted"}`}>{foot}</div>
        </div>
      </div>
    </div>
  );
}
