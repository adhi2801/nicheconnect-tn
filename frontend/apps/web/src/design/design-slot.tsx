import type { ReactNode } from "react";
import { DESIGNS } from "./registry";
import { SLOTS, type SlotId } from "./slots";

/**
 * A reserved space for a design (HD-002). Its size comes from src/design/slots.ts and is fixed: the box is contained (globals.css
 * ".design-slot"), so whatever is drawn inside can never move, cover or restyle the page around it (proven by e2e/design-slots.spec.ts).
 * An `optional` slot with no design registered is not drawn at all (a dashboard card that would only be an empty panel); development
 * builds still outline it. With no design registered a plain one shows `fallback` if given (the logo slot shows the word Colyv), otherwise a quiet surface. In development
 * builds every slot is outlined with its name and purpose, so it is clear where each design will go.
 * A server component: an empty slot sends no JavaScript.
 */
export function DesignSlot({ id, fallback, className = "", optional = false }: { id: SlotId; fallback?: ReactNode; className?: string; optional?: boolean }) {
  const Design = DESIGNS[id];
  const slot = SLOTS[id];
  const state = Design ? "design" : fallback ? "fallback" : "empty";
  return (
    <div data-slot={id} data-slot-state={state} data-optional={optional || undefined} className={`design-slot ${slot.size} ${className}`}>
      {Design ? <Design /> : fallback}
      <span className="design-slot-label" aria-hidden>
        {id} · {slot.purpose}
      </span>
    </div>
  );
}
