import { ButtonLink } from "@/components/ui/button";
import { toRow, type AttentionItem } from "@/lib/attention";
import { t } from "@/lib/messages";
import type { Role } from "@/lib/session";
import { titleFor } from "./row-title";

/** The nearest deadline that has not passed, as the one thing to look at next. Nothing dated, nothing shown. */
export function NextDeadline({ items, role }: { items: AttentionItem[]; role: Role }) {
  const dated = items.filter((i) => i.days_left !== null && i.days_left !== undefined && i.days_left >= 0 && i.kind !== "new_sign_in");
  if (dated.length === 0) return null;
  const next = dated.reduce((a, b) => ((b.days_left ?? 0) < (a.days_left ?? 0) ? b : a));
  const row = toRow(next, role);
  const days = next.days_left ?? 0;
  const big = days === 0 ? t("today.next.today") : days === 1 ? t("today.next.tomorrow") : t("today.next.days", { days });
  return (
    <div className="hero on-dark grid gap-5 rounded-[1.75rem] p-5 sm:p-6">
      <h2 className="text-[15px] font-medium">{t("today.next.title")}</h2>
      <p className="font-display text-[2.5rem] font-medium leading-none tracking-tight">{big}</p>
      <div className="grid gap-1">
        <p className="font-semibold leading-snug">{titleFor(row, next)}</p>
        {row.context && <p className="truncate text-sm text-on-accent/80">{row.context}</p>}
      </div>
      <ButtonLink href={row.href} variant="highlight" className="w-full">{t("today.next.open")}</ButtonLink>
    </div>
  );
}
