"use client";

import Link from "next/link";
import { useEffect, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { IconButton } from "@/components/ui/icon-button";
import { BellIcon, CloseIcon, MenuIcon } from "@/components/ui/icons";
import { Skeleton } from "@/components/ui/skeleton";
import { initials } from "@/lib/format";
import { t } from "@/lib/messages";
import { useProfile, useUnreadCount } from "@/lib/queries";
import { restoreSession, type Role } from "@/lib/session";
import { useSession } from "@/lib/use-session";
import { MenuNav, TopNav } from "./app-nav";

// The colyv mark is a placeholder until the designer's logo arrives: a ring with a dot, in the outlined pill the public site uses.
function Logo() {
  return (
    <Link href="/app" className="t-base inline-flex h-11 shrink-0 items-center gap-2.5 rounded-full border border-line-strong bg-surface/70 px-4 font-display text-[19px] font-semibold tracking-[-0.035em]">
      <span aria-hidden className="grid size-5 place-items-center rounded-full border-2 border-accent"><span className="size-1.5 rounded-full bg-accent" /></span>
      Colyv
    </Link>
  );
}

function Bell({ unread }: { unread: number }) {
  return (
    <IconButton href="/app/inbox" label={unread > 0 ? t("nav.unread", { count: unread }) : t("nav.notifications")} badge={unread > 0 ? <span aria-hidden className="absolute -right-0.5 -top-0.5 grid min-w-5 place-items-center rounded-full bg-lime px-1 text-[11px] font-bold leading-5 text-on-lime ring-2 ring-ground">{unread > 9 ? "9+" : unread}</span> : null}>
      <BellIcon width={20} height={20} />
    </IconButton>
  );
}

const MENU = "app-menu";

function Frame({ children, role }: { children: ReactNode; role: Role }) {
  const profile = useProfile(role);
  const unread = useUnreadCount().data?.unread ?? 0;
  const name = profile.data?.found ? profile.data.name : null;
  return (
    <div className="min-h-screen">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-full focus:bg-ink focus:px-5 focus:py-3 focus:text-on-accent">{t("nav.skip")}</a>
      <header className="sticky top-0 z-40 pt-3 sm:pt-4">
        <div className="mx-auto flex h-14 w-full max-w-[90rem] items-center gap-4 px-5 sm:px-8">
          <Logo />
          <TopNav role={role} />
          <div className="ml-auto flex items-center gap-2.5 lg:ml-0">
            <Bell unread={unread} />
            {/* No aria-label: what a sighted person reads (the name and role) starts the link's spoken name,
                as WCAG 2.5.3 asks, and "Your account" ends it; the initials are a picture of the name. */}
            <Link href="/app/me" className="t-base hidden min-h-11 items-center gap-3 rounded-full bg-surface/90 p-1 shadow-[0_0_0_1px_var(--c-line)] hover:bg-surface lg:flex lg:pr-5">
              <span aria-hidden className="grid size-9 place-items-center rounded-full bg-accent text-[13px] font-semibold text-on-accent">{name ? initials(name) : <span aria-hidden className="size-2 rounded-full bg-highlight-deep" />}</span>
              <span className="min-w-0 text-left leading-tight">
                <span className="block max-w-40 truncate text-sm font-semibold">{name ?? " "}</span>
                <span className="block text-xs text-muted">{t(`nav.role.${role}`)}</span>
              </span>
              <span className="sr-only">{t("nav.yourAccount")}</span>
            </Link>
            <button type="button" popoverTarget={MENU} aria-label={t("nav.menu")} className="t-base inline-flex size-11 items-center justify-center rounded-full bg-surface/90 text-ink shadow-[0_0_0_1px_var(--c-line)] hover:bg-surface lg:hidden">
              <MenuIcon width={20} height={20} />
            </button>
          </div>
        </div>
        <div id={MENU} popover="auto" aria-label={t("nav.label")} className="fixed inset-0 m-0 h-dvh max-h-none w-full max-w-none overflow-y-auto border-0 bg-ground p-0 text-ink">
          <div className="flex h-16 items-center justify-between px-5 sm:px-8">
            <Logo />
            <button type="button" popoverTarget={MENU} popoverTargetAction="hide" aria-label={t("nav.close")} className="t-base inline-flex size-11 items-center justify-center rounded-full hover:bg-sunk">
              <CloseIcon width={22} height={22} />
            </button>
          </div>
          <MenuNav role={role} />
        </div>
      </header>
      <main id="main" className="mx-auto w-full max-w-[90rem] px-5 pb-20 pt-8 sm:px-8 lg:pt-10">{children}</main>
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
