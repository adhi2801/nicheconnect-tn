// Shown within 100 ms of a tap while the real content loads (docs/standards/frontend.md section 4).
export function Skeleton({ className = "" }: { className?: string }) {
  return <div aria-hidden className={`rounded-xl bg-sunk motion-safe:animate-pulse ${className}`} />;
}
