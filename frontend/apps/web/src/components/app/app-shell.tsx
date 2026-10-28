"use client";

import Link from "next/link";
import { useEffect, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { Skeleton } from "@/components/ui/skeleton";
import { BellIcon } from "@/components/ui/icons";
import { initials } from "@/lib/format";
import { t } from "@/lib/messages";
import { useProfile, useUnreadCount } from "@/lib/queries";
import { restoreSession, type Role } from "@/lib/session";
import { useSession } from "@/lib/use-session";
import { BottomNav, TopNav } from "./app-nav";

function Logo() {
  return (
    <Link href="/app" className="flex min-h-11 items-center gap-2 rounded-full bg-surface/90 px-4 font-display text-[15px] font-semibold tracking-tight shadow-[0_0_0_1px_var(--c-line)]">
      <span aria-hidden className="size-2.5 rounded-full bg-ink" />
      Colyv
    </Link>
  );
}

function Header({ role }: { role: Role }) {
  const profile = useProfile(role);
  const unread = useUnreadCount();
  const count = unread.data?.unread ?? 0;
  const name = profile.data?.found ? profile.data.name : null;
  return (
    <header className="mx-auto flex w-full max-w-[1200px] items-center justify-between gap-3 px-4 pt-4 sm:px-6">
      <Logo />
      <TopNav role={role} />
      <div className="flex items-center gap-2">
        <Link href="/app/inbox" aria-label={count > 0 ? t("nav.unread", { count }) : t("nav.notifications")} className="t-base relative grid size-11 place-items-center rounded-full bg-surface/90 shadow-[0_0_0_1px_var(--c-line)] hover:bg-surface">
          <BellIcon width={20} height={20} />
          {count > 0 && <span aria-hidden className="absolute -right-0.5 -top-0.5 grid min-w-5 place-items-center rounded-full bg-highlight px-1 text-[11px] font-bold leading-5 text-on-highlight ring-2 ring-ground">{count > 9 ? "9+" : count}</span>}
        </Link>
        <Link href="/app/me" aria-label={t("nav.yourAccount")} className="t-base grid size-11 place-items-center rounded-full bg-ink text-[13px] font-semibold text-on-accent hover:bg-accent-hover">
          {name ? initials(name) : <span aria-hidden className="size-2 rounded-full bg-highlight" />}
        </Link>
      </div>
    </header>
  );
}

function Frame({ children, role }: { children: ReactNode; role: Role }) {
  return (
    <>
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-full focus:bg-ink focus:px-5 focus:py-3 focus:text-on-accent">{t("nav.skip")}</a>
      <Header role={role} />
      <main id="main" className="mx-auto w-full max-w-[1200px] flex-1 px-4 pb-32 pt-8 sm:px-6 md:pb-16">{children}</main>
      <BottomNav role={role} />
    </>
  );
}

/** The signed-in frame. Anyone who is not signed in goes to the sign-in screen; the cookie is checked first. */
export function AppShell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const state = useSession();
  useEffect(() => { void restoreSession(); }, []);
  useEffect(() => { if (state.status === "signedOut") router.replace("/sign-in"); }, [state.status, router]);

  if (state.status !== "signedIn") {
    return (
      <div aria-busy="true" aria-label={t("common.loading")} className="mx-auto grid w-full max-w-[1200px] gap-6 px-4 pt-6 sm:px-6">
        <Skeleton className="h-11 w-full" />
        <Skeleton className="h-10 w-2/3" />
        <Skeleton className="h-72 w-full rounded-3xl" />
      </div>
    );
  }
  return <Frame role={state.session.role}>{children}</Frame>;
}
