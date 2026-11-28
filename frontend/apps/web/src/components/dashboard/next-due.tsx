import { Panel } from "./panel";
import { Ring } from "./ring";
import { toRow, type AttentionItem } from "@/lib/attention";
import { t } from "@/lib/app-messages";
import type { Role } from "@/lib/session";
import { titleFor } from "@/components/today/row-title";

const WINDOW_DAYS = 14;

/** The nearest deadline that has not passed, on a ring that fills as it comes close. Nothing dated: it says so. */
export function NextDue({ items, role }: { items: AttentionItem[]; role: Role }) {
  const dated = items.filter((i) => i.days_left !== null && i.days_left !== undefined && i.days_left >= 0 && i.kind !== "new_sign_in");
  if (dated.length === 0) {
    return <Panel title={t("dashboard.next.title")}><p className="text-[15px] text-muted">{t("dashboard.next.none")}</p></Panel>;
  }
  const next = dated.reduce((a, b) => ((b.days_left ?? 0) < (a.days_left ?? 0) ? b : a));
  const row = toRow(next, role);
  const days = next.days_left ?? 0;
  return (
    <Panel title={t("dashboard.next.title")} action={{ href: row.href, label: t("dashboard.next.open") }}>
      <Ring fraction={1 - Math.min(days, WINDOW_DAYS) / WINDOW_DAYS}>
        {days <= 1 ? (
          <span className="type-figure text-[2.25rem]">{days === 0 ? t("dashboard.next.today") : t("dashboard.next.tomorrow")}</span>
        ) : (
          <>
            <span className="type-figure text-[3rem]">{days}</span>
            <span className="text-[13px] text-muted">{t("dashboard.next.days")}</span>
          </>
        )}
      </Ring>
      <div className="grid gap-0.5 text-center">
        <p className="text-[15px] font-semibold leading-snug">{titleFor(row, next)}</p>
        {row.context && <p className="truncate text-sm text-muted">{row.context}</p>}
      </div>
    </Panel>
  );
}
