import type { ReactNode } from "react";

const TICKS = 60;

/** A ring with tick marks (the reference's work-time dial): `fraction` of it is filled. The centre is the words, so the ring is only
 *  a picture of them and is hidden from a screen reader. */
export function Ring({ fraction, children }: { fraction: number; children: ReactNode }) {
  const f = Math.min(1, Math.max(0, fraction));
  return (
    <div className="relative mx-auto aspect-square w-full max-w-[13rem]">
      <svg viewBox="0 0 160 160" aria-hidden className="absolute inset-0 size-full">
        {Array.from({ length: TICKS }, (_, i) => {
          const a = (i / TICKS) * Math.PI * 2;
          const r1 = 66, r2 = i % 5 === 0 ? 76 : 72;
          return <line key={i} x1={80 + Math.sin(a) * r1} y1={80 - Math.cos(a) * r1} x2={80 + Math.sin(a) * r2} y2={80 - Math.cos(a) * r2} stroke="var(--c-line-strong)" strokeWidth={i % 5 === 0 ? 1.6 : 1} strokeLinecap="round" opacity={0.55} />;
        })}
        <circle cx="80" cy="80" r="54" fill="none" stroke="var(--c-sunk)" strokeWidth="9" />
        {f > 0 && <circle cx="80" cy="80" r="54" fill="none" stroke="var(--c-accent)" strokeWidth="9" strokeLinecap="round" pathLength={100} strokeDasharray={`${f * 100} 200`} transform="rotate(-90 80 80)" />}
      </svg>
      <div className="absolute inset-0 grid place-content-center justify-items-center text-center">{children}</div>
    </div>
  );
}
