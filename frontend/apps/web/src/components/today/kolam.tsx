// A small kolam, the rice-flour pattern drawn at a doorstep: a scalloped diamond of looping arcs around a lattice of dots.
// Used only where a screen is calm and empty, as a welcome and never as wallpaper.

/** A diamond whose every side is two semicircles bulging outward. `r` is the diamond's half-diagonal. */
function scallopedDiamond(cx: number, cy: number, r: number): string {
  const corners: [number, number][] = [[cx, cy - r], [cx + r, cy], [cx, cy + r], [cx - r, cy]];
  const arc = Math.hypot(r, r) / 4; // radius of each semicircle: a quarter of a side
  let d = `M ${corners[0][0]} ${corners[0][1]}`;
  for (let i = 0; i < 4; i++) {
    const [x1, y1] = corners[i];
    const [x2, y2] = corners[(i + 1) % 4];
    d += ` A ${arc} ${arc} 0 0 1 ${(x1 + x2) / 2} ${(y1 + y2) / 2} A ${arc} ${arc} 0 0 1 ${x2} ${y2}`;
  }
  return `${d} Z`;
}

export function Kolam({ size = 88, tone = "light" }: { size?: number; tone?: "light" | "dark" }) {
  const color = tone === "dark" ? "var(--c-highlight-deep)" : "var(--c-gauge-mid)";
  const dots: [number, number][] = [[48, 48], [48, 32], [48, 64], [32, 48], [64, 48], [48, 18], [48, 78], [18, 48], [78, 48]];
  return (
    <svg width={size} height={size} viewBox="0 0 96 96" fill="none" aria-hidden strokeLinecap="round" strokeLinejoin="round">
      <path d={scallopedDiamond(48, 48, 40)} stroke={color} strokeWidth={1.6} />
      <path d={scallopedDiamond(48, 48, 24)} stroke={color} strokeWidth={1.4} opacity={0.75} />
      {dots.map(([x, y], i) => (<circle key={i} cx={x} cy={y} r={i < 5 ? 2.2 : 1.7} fill={color} />))}
    </svg>
  );
}
