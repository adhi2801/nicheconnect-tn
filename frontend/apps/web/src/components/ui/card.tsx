import type { HTMLAttributes } from "react";

type Props = HTMLAttributes<HTMLDivElement> & {
  /** One dark card per screen, for the thing that needs the person most. */
  tone?: "light" | "dark";
};

export function Card({ tone = "light", className = "", ...rest }: Props) {
  const look = tone === "dark" ? "bg-ink text-on-accent" : "bg-surface text-ink shadow-card";
  return <div className={`rounded-3xl p-6 ${look} ${className}`} {...rest} />;
}
