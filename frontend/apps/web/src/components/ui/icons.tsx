import type { SVGProps } from "react";

// A small set of inline icons. Decorative: the words beside them carry the meaning.
const base: SVGProps<SVGSVGElement> = { width: 16, height: 16, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 2, strokeLinecap: "round", strokeLinejoin: "round", "aria-hidden": true };

export const CheckIcon = (p: SVGProps<SVGSVGElement>) => (<svg {...base} {...p}><path d="m5 12.5 4.5 4.5L19 7.5" /></svg>);
export const ClockIcon = (p: SVGProps<SVGSVGElement>) => (<svg {...base} {...p}><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></svg>);
export const AlertIcon = (p: SVGProps<SVGSVGElement>) => (<svg {...base} {...p}><path d="M12 4 3 20h18L12 4Z" /><path d="M12 10v4M12 17.5v.01" /></svg>);
export const InfoIcon = (p: SVGProps<SVGSVGElement>) => (<svg {...base} {...p}><circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 8v.01" /></svg>);
export const DotIcon = (p: SVGProps<SVGSVGElement>) => (<svg {...base} {...p}><circle cx="12" cy="12" r="4" fill="currentColor" stroke="none" /></svg>);
export const ArrowRightIcon = (p: SVGProps<SVGSVGElement>) => (<svg {...base} {...p}><path d="M5 12h14M13 6l6 6-6 6" /></svg>);
export const HomeIcon = (p: SVGProps<SVGSVGElement>) => (<svg {...base} {...p}><path d="M4 11 12 4l8 7v8a1 1 0 0 1-1 1h-4v-6H9v6H5a1 1 0 0 1-1-1v-8Z" /></svg>);
export const CompassIcon = (p: SVGProps<SVGSVGElement>) => (<svg {...base} {...p}><circle cx="12" cy="12" r="9" /><path d="m15.5 8.5-2 5-5 2 2-5 5-2Z" /></svg>);
export const MegaphoneIcon = (p: SVGProps<SVGSVGElement>) => (<svg {...base} {...p}><path d="M4 10v4l11 4V6L4 10Z" /><path d="M7 14.5 8 19h3M19 9.5a4 4 0 0 1 0 5" /></svg>);
export const TicketIcon = (p: SVGProps<SVGSVGElement>) => (<svg {...base} {...p}><path d="M4 8a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v2a2 2 0 0 0 0 4v2a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-2a2 2 0 0 0 0-4V8Z" /><path d="M14 6v12" strokeDasharray="2 3" /></svg>);
export const BellIcon = (p: SVGProps<SVGSVGElement>) => (<svg {...base} {...p}><path d="M6 9a6 6 0 0 1 12 0c0 6 2.5 7.5 2.5 7.5h-17S6 15 6 9Z" /><path d="M10 20a2 2 0 0 0 4 0" /></svg>);
export const UserIcon = (p: SVGProps<SVGSVGElement>) => (<svg {...base} {...p}><circle cx="12" cy="8.5" r="3.5" /><path d="M5 20c.8-3.6 3.5-5.5 7-5.5s6.2 1.9 7 5.5" /></svg>);
export const RupeeIcon = (p: SVGProps<SVGSVGElement>) => (<svg {...base} {...p}><path d="M7 5h10M7 9h10M7 5c5 0 7 1.5 7 4s-2 4-7 4l7 6" /></svg>);
export const FileIcon = (p: SVGProps<SVGSVGElement>) => (<svg {...base} {...p}><path d="M7 3h7l4 4v13a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z" /><path d="M14 3v4h4M9 12h6M9 16h6" /></svg>);
export const ShieldIcon = (p: SVGProps<SVGSVGElement>) => (<svg {...base} {...p}><path d="M12 3 5 6v5.5c0 4.2 2.8 7.4 7 9.5 4.2-2.1 7-5.3 7-9.5V6l-7-3Z" /><path d="m9 12 2.2 2.2L15 10.5" /></svg>);
export const ArrowUpRightIcon = (p: SVGProps<SVGSVGElement>) => (<svg {...base} {...p}><path d="M7 17 17 7M8 7h9v9" /></svg>);
export const LogoutIcon = (p: SVGProps<SVGSVGElement>) => (<svg {...base} {...p}><path d="M10 5H6a1 1 0 0 0-1 1v12a1 1 0 0 0 1 1h4M15 8l4 4-4 4M19 12H9" /></svg>);
export const PlusIcon = (p: SVGProps<SVGSVGElement>) => (<svg {...base} {...p}><path d="M12 5v14M5 12h14" /></svg>);
