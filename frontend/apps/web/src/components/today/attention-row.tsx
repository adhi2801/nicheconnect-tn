import type { ReactNode } from "react";
import { ButtonLink } from "@/components/ui/button";
import { FileIcon, RupeeIcon, ShieldIcon, UserIcon } from "@/components/ui/icons";
import { Pill, type Tone } from "@/components/ui/pill";
import { deviceWords, type AttentionItem, type Row } from "@/lib/attention";
import { formatPaise } from "@/lib/format";
import { t } from "@/lib/messages";

const icons: Record<Row["tone"], ReactNode> = { money: <RupeeIcon />, work: <FileIcon />, account: <UserIcon />, security: <ShieldIcon /> };
const dueTone: Record<NonNullable<Row["due"]>["tone"], Tone> = { late: "bad", soon: "warn", normal: "neutral" };

/** One thing waiting on the person: what to do, with whom, by when, and the one button that does it. */
export function AttentionRow({ row, item, primary }: { row: Row; item: AttentionItem; primary: boolean }) {
  const device = row.kind === "new_sign_in" ? (() => { const d = deviceWords(item); return d.label ?? t(d.fallbackKey); })() : null;
  const title = t(row.titleKey, device ? { ...row.titleVars, device } : row.titleVars);
  return (
    <li className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3.5 gap-y-3 rounded-2xl bg-white/[0.07] p-4 sm:grid-cols-[auto_minmax(0,1fr)_auto] sm:items-center sm:gap-x-4">
      <span aria-hidden className={`grid size-10 place-items-center rounded-xl sm:size-11 ${row.tone === "security" ? "bg-bad-soft text-bad" : "bg-white/10 text-highlight"}`}>{icons[row.tone]}</span>
      <div className="grid min-w-0 gap-1.5">
        <p className="text-[15px] font-semibold leading-snug">{title}</p>
        {(row.context || row.contextKey) && <p className="truncate text-sm text-on-accent/70">{row.context ?? (row.contextKey ? t(row.contextKey) : "")}</p>}
        {(row.due || row.amountPaise !== null || row.tone === "security") && (
          <div className="mt-0.5 flex flex-wrap items-center gap-2">
            {row.tone === "security" && <Pill tone="bad">{t("attention.security")}</Pill>}
            {row.due && <Pill tone={dueTone[row.due.tone]}>{t(row.due.key, row.due.vars)}</Pill>}
            {row.amountPaise !== null && <span className="font-display text-[15px] font-semibold tabular-nums">{formatPaise(row.amountPaise)}</span>}
          </div>
        )}
      </div>
      <ButtonLink href={row.href} variant={primary ? "highlight" : "onDark"} className="col-span-2 w-full sm:col-span-1 sm:w-auto">{t(row.ctaKey)}</ButtonLink>
    </li>
  );
}
