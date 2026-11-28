"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Panel } from "@/components/dashboard/panel";
import { toRow, type AttentionItem } from "@/lib/attention";
import { t } from "@/lib/messages";
import type { Role } from "@/lib/session";
import { AttentionRow } from "./attention-row";

const VISIBLE = 5;

/** What needs the person, most urgent first, on the dashboard's one dark card. Five at a time, so the screen stays calm. */
export function NeedsYou({ items, total, truncated, role }: { items: AttentionItem[]; total: number; truncated: boolean; role: Role }) {
  const [all, setAll] = useState(false);
  const shown = all ? items : items.slice(0, VISIBLE);
  return (
    <Panel id="needs-you" title={t("today.needsYou")} tone="dark" aside={<span aria-hidden className="type-figure text-[2rem]">{total}</span>}>
      <ul className="grid gap-3">
        {shown.map((item, i) => {
          const row = toRow(item, role);
          return <AttentionRow key={row.id} row={row} item={item} primary={i === 0} />;
        })}
      </ul>
      {items.length > VISIBLE && (
        <Button variant="onDark" onClick={() => setAll((v) => !v)} aria-expanded={all} className="w-full sm:w-auto sm:justify-self-start">
          {all ? t("today.showFewer") : t("today.showAll", { count: items.length })}
        </Button>
      )}
      {truncated && <p className="text-sm text-on-accent/75">{t("today.truncated", { shown: items.length, total })}</p>}
    </Panel>
  );
}
