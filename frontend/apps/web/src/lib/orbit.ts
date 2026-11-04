// The landing page's turning temple: which pre-rendered frame to show for how far the reader has scrolled.
// The frames are made in Blender (frontend/3d/temple, D-142) and exported by export_web.py; this file only does the arithmetic.

export const ORBIT_FRAMES = 48;
/** Widths the frames are exported at, smallest first. */
export const ORBIT_WIDTHS = [640, 960, 1280] as const;
export type OrbitWidth = (typeof ORBIT_WIDTHS)[number];

/** How far through its stage the hero has scrolled, from 0 to 1, given the stage's box and the viewport's height. */
export function progressThrough(top: number, height: number, viewport: number): number {
  const travel = height - viewport;
  if (travel <= 0) return 0;
  return clamp(-top / travel, 0, 1);
}

/** The frame for a progress from 0 to 1: the first at 0, the last at 1, never outside the set. */
export function frameAt(progress: number, count: number = ORBIT_FRAMES): number {
  if (!Number.isFinite(progress) || count <= 0) return 0;
  return Math.min(count - 1, Math.max(0, Math.round(clamp(progress, 0, 1) * (count - 1))));
}

/**
 * The width to load for a screen this many CSS pixels wide at this pixel density: the smallest set at least as wide
 * as the screen shows it, counting density up to 2 (past that the eye gains little and the bytes triple).
 */
export function widthFor(cssWidth: number, density: number): OrbitWidth {
  const shown = Math.max(0, cssWidth) * Math.min(2, Math.max(1, density));
  return ORBIT_WIDTHS.find((width) => width >= shown) ?? ORBIT_WIDTHS[ORBIT_WIDTHS.length - 1];
}

export function frameSrc(index: number, width: OrbitWidth): string {
  return `/landing/orbit/${width}/f${String(index).padStart(2, "0")}.webp`;
}

function clamp(value: number, low: number, high: number): number {
  return Math.min(high, Math.max(low, value));
}
