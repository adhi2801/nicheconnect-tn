"use client";

import Link from "next/link";
import { useEffect, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { IconButton } from "@/components/ui/icon-button";
import { BellIcon } from "@/components/ui/icons";
import { Skeleton } from "@/components/ui/skeleton";
import { initials } from "@/lib/format";
import { t } from "@/lib/messages";
import { useProfile, useUnreadCount } from "@/lib/queries";
import { restoreSession, type Role } from "@/lib/session";
import { useSession } from "@/lib/use-session";
import { BottomNav, SideNav } from "./app-nav";

// The colyv mark is a placeholder until the designer's logo arrives: a green ring with a dot.
function Logo() {
  return (
    <Link href="/app" className="flex min-h-11 items-center gap-2.5 font-display text-xl font-semibold tracking-tight">
      <span aria-hidden className="grid size-8 place-items-center rounded-full border-[3px] border-accent"><span className="size-2 rounded-full bg-accent" /></span>
      Colyv
    </Link>
  );
}

function Bell({ unread }: { unread: number }) {
  return (
    <IconButton href="/app/inbox" label={unread > 0 ? t("nav.unread", { count: unread }) : t("nav.notifications")} badge={unread > 0 ? <span aria-hidden className="absolute -right-0.5 -top-0.5 grid min-w-5 place-items-center rounded-full bg-accent px-1 text-[11px] font-bold leading-5 text-on-accent ring-2 ring-ground lg:ring-sunk">{unread > 9 ? "9+" : unread}</span> : null}>
      <BellIcon width={20} height={20} />
    </IconButton>
  );
}

function Frame({ children, role }: { children: ReactNode; role: Role }) {
  const profile = useProfile(role);
  const unread = useUnreadCount().data?.unread ?? 0;
  const name = profile.data?.found ? profile.data.name : null;
  return (
    <div className="min-h-screen lg:p-5">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-full focus:bg-ink focus:px-5 focus:py-3 focus:text-on-accent">{t("nav.skip")}</a>
      <div className="mx-auto min-h-screen max-w-[1520px] lg:min-h-[calc(100vh-2.5rem)] lg:grid lg:grid-cols-[16.5rem_minmax(0,1fr)] lg:gap-3 lg:rounded-[2.25rem] lg:bg-surface lg:p-3 lg:shadow-card">
        <aside className="hidden px-5 py-5 lg:grid lg:content-start lg:gap-10">
          <Logo />
          <SideNav role={role} unread={unread} />
        </aside>
        <div className="flex min-w-0 flex-col gap-4 px-4 pt-4 sm:px-6 lg:gap-5 lg:rounded-[1.75rem] lg:bg-sunk lg:p-5">
          <header className="flex items-center justify-between gap-3">
            <div className="lg:hidden"><Logo /></div>
            <div className="flex items-center gap-2.5 lg:ml-auto">
              <Bell unread={unread} />
              <Link href="/app/me" aria-label={t("nav.yourAccount")} className="t-base flex min-h-11 items-center gap-3 rounded-full bg-surface p-1 shadow-card hover:bg-sunk lg:pr-5">
                <span className="grid size-9 place-items-center rounded-full bg-accent text-[13px] font-semibold text-on-accent">{name ? initials(name) : <span aria-hidden className="size-2 rounded-full bg-highlight-deep" />}</span>
                <span className="hidden min-w-0 text-left leading-tight lg:grid">
                  <span className="max-w-40 truncate text-sm font-semibold">{name ?? " "}</span>
                  <span className="text-xs text-muted">{t(`nav.role.${role}`)}</span>
                </span>
              </Link>
            </div>
          </header>
          <main id="main" className="flex-1 pb-28 lg:rounded-3xl lg:bg-surface lg:p-6 lg:pb-8 lg:shadow-card">{children}</main>
        </div>
      </div>
      <BottomNav role={role} />
    </div>
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
