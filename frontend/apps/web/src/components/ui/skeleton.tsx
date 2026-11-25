// Shown within 100 ms of a tap while the real content loads (docs/standards/frontend.md section 4).
// A block <span>, not a <div>, so it may stand in for text inside a <p> or a heading without breaking the HTML (React warns, and the
// browser would move it out of the paragraph).
export function Skeleton({ className = "" }: { className?: string }) {
  return <span aria-hidden className={`block rounded-xl bg-sunk motion-safe:animate-pulse ${className}`} />;
}
