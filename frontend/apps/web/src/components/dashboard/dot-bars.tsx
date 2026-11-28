const ROWS = 10;

/** Bars drawn in dots (the reference's dotted chart), one column per item. A picture only: the numbers it shows are in the list beside
 *  it, so it is hidden from a screen reader. A value of zero or nothing draws no dots; any real value draws at least one. */
export function DotBars({ values }: { values: (number | null)[] }) {
  const max = Math.max(1, ...values.map((v) => v ?? 0));
  return (
    <div aria-hidden className="flex h-24 items-end justify-start gap-2.5">
      {values.map((value, i) => {
        const filled = value && value > 0 ? Math.max(1, Math.round((value / max) * ROWS)) : 0;
        return (
          <div key={i} className="grid content-end gap-1">
            {Array.from({ length: ROWS }, (_, row) => (
              <span key={row} className={`block size-2 rounded-full ${ROWS - row <= filled ? "bg-accent" : "bg-line"}`} />
            ))}
          </div>
        );
      })}
    </div>
  );
}
