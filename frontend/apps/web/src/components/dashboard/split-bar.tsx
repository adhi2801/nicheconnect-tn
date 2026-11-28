import { percent, type Share } from "@/lib/dashboard";
import { t } from "@/lib/app-messages";

type Fill = "ink" | "lime" | "hatch";
const FILLS: Record<Fill, string> = { ink: "bg-accent text-on-accent", lime: "bg-lime text-on-lime", hatch: "hatch text-ink" };

/** One step's progress as a capsule bar with its percent (the reference's "60%" row). A step with nothing to divide says so in words
 *  and draws no bar: "not enough yet" is not 0%. */
export function SplitBar({ label, share, fill }: { label: string; share: Share; fill: Fill }) {
  const p = percent(share);
  const inside = p !== null && p >= 18;
  return (
    <div className="grid gap-2">
      <p className="text-[13px] text-muted">{label}</p>
      {p === null || share === null ? (
        <div className="flex h-11 items-center rounded-full bg-surface/70 px-4 text-[13px] text-muted shadow-[0_0_0_1px_var(--c-line)]">{t("dashboard.progress.notYet")}</div>
      ) : (
        <div
          role="progressbar"
          aria-label={label}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={p}
          aria-valuetext={`${p}% (${t("dashboard.progress.of", { done: share.done, of: share.of })})`}
          className="flex h-11 items-center overflow-hidden rounded-full bg-surface/70 shadow-[0_0_0_1px_var(--c-line)]"
        >
          {p > 0 && (
            <div className={`flex h-full items-center rounded-full px-4 text-[13px] font-semibold tabular-nums ${FILLS[fill]}`} style={{ width: `${p}%` }}>
              {inside ? `${p}%` : null}
            </div>
          )}
          {!inside && <span className="px-3 text-[13px] font-semibold tabular-nums">{p}%</span>}
        </div>
      )}
    </div>
  );
}
