"use client";

import { motion, useReducedMotion } from "motion/react";
import type { ReactNode } from "react";

// The one entrance motion: a short rise and fade, staggered by `index`. It stops for people who asked for less motion.
export function Reveal({ children, index = 0, className }: { children: ReactNode; index?: number; className?: string }) {
  const reduce = useReducedMotion();
  return (
    <motion.div className={className} initial={reduce ? false : { opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, delay: reduce ? 0 : index * 0.07, ease: [0.22, 1, 0.36, 1] }}>
      {children}
    </motion.div>
  );
}
