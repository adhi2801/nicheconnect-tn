"use client";

import { useEffect, useId, useRef, type ReactNode } from "react";
import { t } from "@/lib/messages";

type Props = { open: boolean; onClose: () => void; title: string; children: ReactNode; /** Keep it open while a write is in flight. */ locked?: boolean };

// A native <dialog> shown as a modal: the browser traps focus, Escape closes it, and what is behind is inert to a screen reader.
// It rises from the bottom on a phone (where the thumb is) and sits in the middle on a laptop.
export function Sheet({ open, onClose, title, children, locked = false }: Props) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      // The browser can close a dialog on its own (a second Escape or Android's Back while locked cannot be refused, by the HTML
      // close-watcher rules). Whenever it closes, the screen's state follows, so the sheet can always be opened again.
      onClose={() => { if (open) onClose(); }}
      onCancel={(e) => { e.preventDefault(); if (!locked) onClose(); }}
      onClick={(e) => { if (e.target === ref.current && !locked) onClose(); }}
      className="m-0 mt-auto max-h-[92dvh] w-full max-w-none overflow-y-auto rounded-t-[1.75rem] bg-surface p-0 text-ink shadow-card backdrop:bg-ink/40 sm:m-auto sm:max-w-xl sm:rounded-[1.75rem]"
    >
      <div className="grid gap-5 p-5 sm:p-7">
        <div className="flex items-start justify-between gap-4">
          <h2 id={titleId} className="font-display text-xl font-semibold leading-tight tracking-tight">{title}</h2>
          <button type="button" onClick={onClose} disabled={locked} className="t-base -mr-2 -mt-1 grid min-h-11 min-w-11 place-items-center rounded-full text-sm font-semibold text-muted hover:bg-sunk disabled:opacity-45">
            {t("common.close")}
          </button>
        </div>
        {children}
      </div>
    </dialog>
  );
}
