"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion, useReducedMotion } from "motion/react";
import type { ReactNode } from "react";
import { BellIcon, CompassIcon, HomeIcon, MegaphoneIcon, TicketIcon, UserIcon } from "@/components/ui/icons";
import { t, type MessageKey } from "@/lib/messages";
import type { Role } from "@/lib/session";

type Item = { href: string; label: MessageKey; icon: ReactNode };

// Five places, the most a thumb-reach bar holds, in the order people use them (frontend/design/screen-plan.md section 4).
export function itemsFor(role: Role): Item[] {
  return [
    { href: "/app", label: "nav.today", icon: <HomeIcon /> },
    role === "creator" ? { href: "/app/discover", label: "nav.discover", icon: <CompassIcon /> } : { href: "/app/campaigns", label: "nav.campaigns", icon: <MegaphoneIcon /> },
    { href: "/app/deals", label: "nav.deals", icon: <TicketIcon /> },
    { href: "/app/inbox", label: "nav.inbox", icon: <BellIcon /> },
    { href: "/app/me", label: "nav.me", icon: <UserIcon /> },
  ];
}

const isActive = (pathname: string, href: string): boolean => (href === "/app" ? pathname === "/app" : pathname === href || pathname.startsWith(`${href}/`));

/** The pill on a laptop: the black thumb slides to the page you are on. */
export function TopNav({ role }: { role: Role }) {
  const pathname = usePathname();
  const reduce = useReducedMotion();
  return (
    <nav aria-label={t("nav.label")} className="hidden rounded-full bg-surface/90 p-1 shadow-[0_0_0_1px_var(--c-line)] md:flex">
      {itemsFor(role).map((item) => {
        const active = isActive(pathname, item.href);
        return (
          <Link key={item.href} href={item.href} aria-current={active ? "page" : undefined} className={`t-base relative flex min-h-11 items-center rounded-full px-5 text-sm font-medium ${active ? "text-on-accent" : "text-muted hover:text-ink"}`}>
            {active && <motion.span layoutId="top-nav-thumb" className="absolute inset-0 rounded-full bg-ink" transition={reduce ? { duration: 0 } : { type: "spring", stiffness: 500, damping: 38 }} />}
            <span className="relative">{t(item.label)}</span>
          </Link>
        );
      })}
    </nav>
  );
}

/** The bar on a phone, fixed at the bottom where the thumb is. The page you are on is the black one. */
export function BottomNav({ role }: { role: Role }) {
  const pathname = usePathname();
  return (
    <nav aria-label={t("nav.label")} className="fixed inset-x-0 bottom-0 z-30 px-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] md:hidden">
      <ul className="mx-auto grid max-w-md grid-cols-5 gap-1 rounded-[1.75rem] bg-surface/95 p-1.5 shadow-[0_0_0_1px_var(--c-line),0_18px_40px_-18px_rgb(60_40_0/0.45)] backdrop-blur-md">
        {itemsFor(role).map((item) => {
          const active = isActive(pathname, item.href);
          return (
            <li key={item.href}>
              <Link href={item.href} aria-current={active ? "page" : undefined} className={`t-base grid min-h-14 place-items-center content-center gap-0.5 rounded-2xl text-[11px] font-semibold ${active ? "bg-ink text-on-accent" : "text-muted"}`}>
                {item.icon}
                {t(item.label)}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
