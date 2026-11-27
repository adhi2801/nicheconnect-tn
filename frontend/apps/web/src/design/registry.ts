import type { ComponentType } from "react";
import type { SlotId } from "./slots";

// The one place a design is plugged in (HD-002). Adding a design is one line here, its code in its own folder under
// src/design/art/, and nothing else: no page changes. A slot with nothing here shows its quiet placeholder.
//
// Rules for a design, checked by src/lib/design-rules.test.ts and e2e/design-slots.spec.ts:
// - it fills the box it is given (width and height 100%) and draws nothing outside it;
// - its styles are its own (a CSS module or Tailwind classes), never a global stylesheet;
// - anything it says is also said in the page's text, so a reader, a search engine or reduced motion loses nothing.
//
// Empty on 27 November 2026: the website's structure comes first, the designs after (frontend/design/website-plan.md).
export const DESIGNS: Partial<Record<SlotId, ComponentType>> = {};
