"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { toRow, type AttentionItem } from "@/lib/attention";
import { t } from "@/lib/messages";
import type { Role } from "@/lib/session";
import { AttentionRow } from "./attention-row";

const VISIBLE = 5;

/** What needs the person, most urgent first. Five at a time, so the screen stays calm. */
export function NeedsYou({ items, total, truncated, role }: { items: AttentionItem[]; total: number; truncated: boolean; role: Role }) {
  const [all, setAll] = useState(false);
  const shown = all ? items : items.slice(0, VISIBLE);
  return (
    <Card id="needs-you" className="grid gap-5 p-5 sm:p-6">
      <div className="flex items-center justify-between gap-4">
        <h2 className="font-display text-xl font-semibold tracking-tight">{t("today.needsYou")}</h2>
        <span aria-hidden className="rounded-full bg-sunk px-3 py-1 text-sm font-semibold tabular-nums">{total}</span>
      </div>
      <ul className="grid gap-3">
        {shown.map((item, i) => {
          const row = toRow(item, role);
          return <AttentionRow key={row.id} row={row} item={item} primary={i === 0} />;
        })}
      </ul>
      {items.length > VISIBLE && (
        <Button variant="secondary" onClick={() => setAll((v) => !v)} aria-expanded={all} className="w-full sm:w-auto sm:justify-self-start">
          {all ? t("today.showFewer") : t("today.showAll", { count: items.length })}
        </Button>
      )}
      {truncated && <p className="text-sm text-muted">{t("today.truncated", { shown: items.length, total })}</p>}
    </Card>
  );
}
