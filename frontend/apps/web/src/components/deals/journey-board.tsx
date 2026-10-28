"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ChevronLeftIcon, ChevronRightIcon } from "@/components/ui/icons";
import type { Column, Payment } from "@/lib/deals";
import { t } from "@/lib/messages";
import type { Role } from "@/lib/session";
import { StageColumn } from "./stage-column";

const arrow = "t-base grid size-10 place-items-center rounded-full bg-surface text-ink shadow-card hover:bg-highlight-soft disabled:opacity-35 disabled:hover:bg-surface";

/** The deals as a journey, left to right. When the stages do not all fit, they scroll sideways and each snaps into place; buttons
 *  and a soft fade at the edge say there is more, so a mouse works as well as a thumb or a trackpad. */
export function JourneyBoard({ columns, role, byMemo }: { columns: Column[]; role: Role; byMemo: Map<string, Payment> }) {
  const scroller = useRef<HTMLDivElement>(null);
  const [reach, setReach] = useState({ overflow: false, canPrev: false, canNext: false });

  const measure = useCallback(() => {
    const el = scroller.current;
    if (!el) return;
    setReach({ overflow: el.scrollWidth > el.clientWidth + 1, canPrev: el.scrollLeft > 4, canNext: el.scrollLeft + el.clientWidth < el.scrollWidth - 4 });
  }, []);

  useEffect(() => {
    const el = scroller.current;
    if (!el) return;
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, [measure, columns.length]);

  function move(direction: 1 | -1) {
    const el = scroller.current;
    const first = el?.querySelector("section");
    if (!el || !first) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    el.scrollBy({ left: direction * (first.getBoundingClientRect().width + 24), behavior: reduce ? "auto" : "smooth" });
  }

  return (
    <div className="relative min-w-0 rounded-[1.75rem] bg-sunk p-3 sm:p-4">
      {reach.overflow && (
        <div className="mb-3 hidden justify-end gap-2 lg:flex">
          <button type="button" className={arrow} onClick={() => move(-1)} disabled={!reach.canPrev} aria-label={t("deals.scroll.previous")}><ChevronLeftIcon /></button>
          <button type="button" className={arrow} onClick={() => move(1)} disabled={!reach.canNext} aria-label={t("deals.scroll.next")}><ChevronRightIcon /></button>
        </div>
      )}
      <div ref={scroller} onScroll={measure} className="flex snap-x snap-mandatory gap-3 overflow-x-auto pb-2 lg:gap-6">
        {columns.map((c, i) => <StageColumn key={c.stage} stage={c.stage} memos={c.memos} role={role} byMemo={byMemo} connect={i > 0} />)}
      </div>
      {reach.canNext && <span aria-hidden className="pointer-events-none absolute inset-y-4 right-3 hidden w-8 rounded-r-3xl bg-gradient-to-l from-sunk/90 to-transparent lg:block sm:right-4" />}
    </div>
  );
}
