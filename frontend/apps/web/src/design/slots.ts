// Every place a planned design goes (HD-002, frontend/design/website-plan.md section 3). A page writes <DesignSlot id="..." /> and
// never sizes a slot itself: the size lives here, so a slot cannot grow by accident and a design always knows the box it gets.
//
// `size` is the box at each width, as Tailwind classes (an aspect ratio, or a width and height). The box is fixed whatever is put in
// it (CSS containment, globals.css ".design-slot"), so a design added later can never move anything around it.
// `purpose` is for the people making the designs; it is shown only with the slot outlines (development builds), never to visitors.

export type Slot = { size: string; purpose: string };

export const SLOTS = {
  "brand.mark": {
    size: "h-7 w-[3.75rem]",
    purpose: "The logo, from the designer's brand book. Until then the word Colyv is shown.",
  },
  "home.hero": {
    size: "w-full aspect-[4/5] sm:aspect-[16/10] lg:aspect-[16/9]",
    purpose: "The hero scene: the temple turned by scroll (D-155, D-164), or whatever replaces it.",
  },
  "home.product": {
    size: "w-full aspect-[4/5] sm:aspect-[16/10]",
    purpose: "The product itself: the redone Deals board, fed example deals, once the Deals page is approved.",
  },
  "home.record": {
    size: "w-full max-w-[30rem] aspect-square",
    purpose: "The sealed record: the bronze seal, or a made image of a record being sealed.",
  },
  "today.feature": {
    size: "w-full aspect-[16/9]",
    purpose: "The dashboard's picture card (the reference's photograph): a made illustration. Shown only once a design is added (data-optional).",
  },
  "footer.ornament": {
    size: "w-full h-12",
    purpose: "A band of ornament above the footer: a kolam line, drawn as a vector.",
  },
} as const satisfies Record<string, Slot>;

export type SlotId = keyof typeof SLOTS;
