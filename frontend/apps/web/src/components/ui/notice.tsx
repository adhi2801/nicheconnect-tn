import type { ReactNode } from "react";
import { AlertIcon, InfoIcon } from "./icons";

type Props = { tone?: "info" | "error"; children: ReactNode; action?: ReactNode };

// Errors say what happened and how to fix it. role="alert" so a screen reader announces it at once.
export function Notice({ tone = "info", children, action }: Props) {
  const isError = tone === "error";
  return (
    <div role={isError ? "alert" : "status"} className={`flex items-start gap-3 rounded-2xl px-4 py-3 text-sm leading-6 ${isError ? "bg-bad-soft text-bad" : "bg-sunk text-muted"}`}>
      <span className="mt-1 shrink-0">{isError ? <AlertIcon /> : <InfoIcon />}</span>
      <div className="min-w-0 flex-1">
        {children}
        {action && <div className="mt-2">{action}</div>}
      </div>
    </div>
  );
}
