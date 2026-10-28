"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion, useReducedMotion } from "motion/react";
import type { ReactNode } from "react";
import { BellIcon, CompassIcon, HomeIcon, LogoutIcon, MegaphoneIcon, TicketIcon, UserIcon } from "@/components/ui/icons";
import { t, type MessageKey } from "@/lib/messages";
import { signOut, type Role } from "@/lib/session";

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

function Caption({ children }: { children: ReactNode }) {
  return <p className="px-3 pb-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-muted">{children}</p>;
}

/** The sidebar on a laptop. The page you are on is bold, with a slim green bar that slides to it. */
export function SideNav({ role, unread }: { role: Role; unread: number }) {
  const pathname = usePathname();
  const reduce = useReducedMotion();
  const menu = itemsFor(role).filter((i) => i.href !== "/app/me");
  const row = "t-base relative flex min-h-11 w-full items-center gap-3 rounded-xl px-3 text-[15px] font-medium text-muted hover:bg-sunk hover:text-ink";
  return (
    <div className="grid content-start gap-8">
      <nav aria-label={t("nav.label")}>
        <Caption>{t("nav.menu")}</Caption>
        <ul className="grid gap-1">
          {menu.map((item) => {
            const active = isActive(pathname, item.href);
            return (
              <li key={item.href}>
                <Link href={item.href} aria-current={active ? "page" : undefined} className={`${row} ${active ? "font-semibold !text-ink" : ""}`}>
                  {active && <motion.span layoutId="side-bar" aria-hidden className="absolute -left-4 top-1/2 h-7 w-1 -translate-y-1/2 rounded-r-full bg-accent" transition={reduce ? { duration: 0 } : { type: "spring", stiffness: 500, damping: 38 }} />}
                  <span className={active ? "text-accent" : ""}>{item.icon}</span>
                  {t(item.label)}
                  {item.href === "/app/inbox" && unread > 0 && <span aria-hidden className="ml-auto rounded-full bg-ink px-2 py-0.5 text-xs font-semibold text-on-accent">{unread > 9 ? "9+" : unread}</span>}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
      <div>
        <Caption>{t("nav.general")}</Caption>
        <ul className="grid gap-1">
          <li>
            <Link href="/app/me" aria-current={isActive(pathname, "/app/me") ? "page" : undefined} className={`${row} ${isActive(pathname, "/app/me") ? "font-semibold !text-ink" : ""}`}>
              {isActive(pathname, "/app/me") && <motion.span layoutId="side-bar" aria-hidden className="absolute -left-4 top-1/2 h-7 w-1 -translate-y-1/2 rounded-r-full bg-accent" transition={reduce ? { duration: 0 } : { type: "spring", stiffness: 500, damping: 38 }} />}
              <span className={isActive(pathname, "/app/me") ? "text-accent" : ""}><UserIcon /></span>
              {t("nav.account")}
            </Link>
          </li>
          <li>
            <button type="button" onClick={() => void signOut()} className={row}><LogoutIcon />{t("nav.signOut")}</button>
          </li>
        </ul>
      </div>
    </div>
  );
}

/** The bar on a phone, fixed at the bottom where the thumb is. The page you are on is the dark one. */
export function BottomNav({ role }: { role: Role }) {
  const pathname = usePathname();
  return (
    <nav aria-label={t("nav.label")} className="fixed inset-x-0 bottom-0 z-30 px-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] lg:hidden">
      <ul className="mx-auto grid max-w-md grid-cols-5 gap-1 rounded-[1.75rem] bg-surface/95 p-1.5 shadow-[0_0_0_1px_var(--c-line),0_18px_40px_-18px_rgb(15_27_21/0.35)] backdrop-blur-md">
        {itemsFor(role).map((item) => {
          const active = isActive(pathname, item.href);
          return (
            <li key={item.href}>
              <Link href={item.href} aria-current={active ? "page" : undefined} className={`t-base grid min-h-14 place-items-center content-center gap-0.5 rounded-2xl text-[11px] font-semibold ${active ? "bg-accent text-on-accent" : "text-muted"}`}>
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
