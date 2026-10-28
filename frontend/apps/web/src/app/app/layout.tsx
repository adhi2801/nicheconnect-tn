import type { ReactNode } from "react";
import { AppShell } from "@/components/app/app-shell";
import { Providers } from "@/components/providers";

// Everything under /app needs a signed-in person; AppShell checks that and draws the frame around the page.
export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <Providers>
      <AppShell>{children}</AppShell>
    </Providers>
  );
}
