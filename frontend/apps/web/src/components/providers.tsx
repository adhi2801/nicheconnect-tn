"use client";

import { useEffect, useState, type ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { retryDelayMs, shouldRetry } from "@/lib/errors";
import { getSessionState, subscribeToSession } from "@/lib/session";

export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(() => new QueryClient({ defaultOptions: { queries: { staleTime: 15_000, refetchOnWindowFocus: true, retry: shouldRetry, retryDelay: (_failures, error) => retryDelayMs(error) } } }));
  // Nothing sensitive stays cached once the person signs out (docs/standards/frontend.md section 9).
  useEffect(() => subscribeToSession(() => { if (getSessionState().status !== "signedIn") client.clear(); }), [client]);
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
