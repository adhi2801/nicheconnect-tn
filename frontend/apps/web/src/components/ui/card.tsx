import type { HTMLAttributes } from "react";

type Props = HTMLAttributes<HTMLDivElement> & {
  /** One dark card per screen, for the thing that needs the person most. */
  tone?: "light" | "dark";
};

export function Card({ tone = "light", className = "", ...rest }: Props) {
  const look = tone === "dark" ? "hero on-dark" : "bg-surface text-ink shadow-card";
  return <div className={`rounded-[1.75rem] p-6 ${look} ${className}`} {...rest} />;
}
