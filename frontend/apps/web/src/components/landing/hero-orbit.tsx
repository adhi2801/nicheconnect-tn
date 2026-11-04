"use client";

import { useEffect, useRef } from "react";
import { ORBIT_FRAMES, frameAt, frameSrc, progressThrough, widthFor } from "@/lib/orbit";

// The temple turns as the reader scrolls (frontend.md 8b). The first frame is a plain image the server sends, so the
// page paints and reads without any script; only after it has painted, and only for people who have not asked for
// less motion, the other frames load in the background and a canvas takes over. No animation library: a public page
// ships almost no JavaScript (frontend.md section 4).
export function HeroOrbit({ alt, children }: { alt: string; children: React.ReactNode }) {
  const stage = useRef<HTMLElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const node = stage.current;
    const paint = canvas.current;
    if (!node || !paint || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const context = paint.getContext("2d");
    if (!context) return;

    const width = widthFor(window.innerWidth, window.devicePixelRatio);
    const frames: (HTMLImageElement | undefined)[] = new Array(ORBIT_FRAMES);
    let shown = -1;
    let queued = 0;
    let stopped = false;

    const draw = () => {
      queued = 0;
      const box = node.getBoundingClientRect();
      const wanted = frameAt(progressThrough(box.top, box.height, window.innerHeight));
      // The nearest frame that has arrived, so a slow connection shows the turn coarsely rather than not at all.
      let index = wanted;
      for (let step = 0; step < ORBIT_FRAMES && !frames[index]; step += 1) index = (wanted + (step % 2 ? step : -step) + ORBIT_FRAMES) % ORBIT_FRAMES;
      const image = frames[index];
      if (!image || index === shown) return;
      shown = index;
      const ratio = Math.max(paint.width / image.naturalWidth, paint.height / image.naturalHeight);
      const w = image.naturalWidth * ratio;
      const h = image.naturalHeight * ratio;
      context.drawImage(image, (paint.width - w) / 2, (paint.height - h) / 2, w, h);
      paint.dataset.ready = "true";
    };
    const request = () => {
      if (!queued) queued = requestAnimationFrame(draw);
    };
    const size = () => {
      const density = Math.min(2, window.devicePixelRatio || 1);
      paint.width = Math.round(paint.clientWidth * density);
      paint.height = Math.round(paint.clientHeight * density);
      shown = -1;
      request();
    };

    const load = () => {
      // Nearest the start first: the reader meets those frames first.
      for (let index = 0; index < ORBIT_FRAMES; index += 1) {
        const image = new Image();
        image.decoding = "async";
        image.onload = () => {
          if (stopped) return;
          frames[index] = image;
          request();
        };
        image.src = frameSrc(index, width);
      }
    };
    const idle = (window as Window & { requestIdleCallback?: (fn: () => void) => number }).requestIdleCallback;
    const start = () => (idle ? idle(load) : window.setTimeout(load, 200));
    if (document.readyState === "complete") start();
    else window.addEventListener("load", start, { once: true });

    size();
    window.addEventListener("scroll", request, { passive: true });
    window.addEventListener("resize", size);
    return () => {
      stopped = true;
      cancelAnimationFrame(queued);
      window.removeEventListener("scroll", request);
      window.removeEventListener("resize", size);
      window.removeEventListener("load", start);
    };
  }, []);

  return (
    <section ref={stage} className="landing-stage relative h-[260svh]" aria-labelledby="landing-title">
      <div className="sticky top-0 h-svh overflow-hidden">
        {/* The still: the page's largest paint, and all a reader without script or with reduced motion sees. */}
        <img
          src={frameSrc(0, 1280)}
          srcSet={`${frameSrc(0, 640)} 640w, ${frameSrc(0, 960)} 960w, ${frameSrc(0, 1280)} 1280w`}
          sizes="100vw"
          width={1280}
          height={720}
          alt={alt}
          fetchPriority="high"
          decoding="async"
          className="absolute inset-0 h-full w-full object-cover"
        />
        <canvas ref={canvas} aria-hidden className="landing-orbit absolute inset-0 h-full w-full" />
        <div className="landing-veil absolute inset-0" aria-hidden />
        <div className="relative mx-auto flex h-full max-w-6xl flex-col justify-end px-6 pb-16 sm:pb-24">{children}</div>
      </div>
    </section>
  );
}
