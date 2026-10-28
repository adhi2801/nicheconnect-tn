import type { SVGProps } from "react";

// A small set of inline icons. Decorative: the words beside them carry the meaning.
const base: SVGProps<SVGSVGElement> = { width: 16, height: 16, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 2, strokeLinecap: "round", strokeLinejoin: "round", "aria-hidden": true };

export const CheckIcon = (p: SVGProps<SVGSVGElement>) => (<svg {...base} {...p}><path d="m5 12.5 4.5 4.5L19 7.5" /></svg>);
export const ClockIcon = (p: SVGProps<SVGSVGElement>) => (<svg {...base} {...p}><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></svg>);
export const AlertIcon = (p: SVGProps<SVGSVGElement>) => (<svg {...base} {...p}><path d="M12 4 3 20h18L12 4Z" /><path d="M12 10v4M12 17.5v.01" /></svg>);
export const InfoIcon = (p: SVGProps<SVGSVGElement>) => (<svg {...base} {...p}><circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 8v.01" /></svg>);
export const DotIcon = (p: SVGProps<SVGSVGElement>) => (<svg {...base} {...p}><circle cx="12" cy="12" r="4" fill="currentColor" stroke="none" /></svg>);
export const ArrowRightIcon = (p: SVGProps<SVGSVGElement>) => (<svg {...base} {...p}><path d="M5 12h14M13 6l6 6-6 6" /></svg>);
