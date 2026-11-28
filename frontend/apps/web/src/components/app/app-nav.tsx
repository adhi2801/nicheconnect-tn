"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { t, type MessageKey } from "@/lib/messages";
import { signOut, type Role } from "@/lib/session";
import { LogoutIcon, UserIcon } from "@/components/ui/icons";

// `also`: other pages that belong to the same place, so the place stays marked while you are on them.
type Item = { href: string; label: MessageKey; also?: string[] };

/** The places in the top menu, in the order people use them (frontend/design/screen-plan.md section 4). Account is the person's own
 *  button at the right, so it is not a tab. */
export function itemsFor(role: Role): Item[] {
  return [
    { href: "/app", label: "nav.today" },
    role === "creator" ? { href: "/app/discover", label: "nav.discover", also: ["/app/applications"] } : { href: "/app/campaigns", label: "nav.campaigns" },
    { href: "/app/deals", label: "nav.deals" },
    { href: "/app/inbox", label: "nav.inbox" },
  ];
}

const under = (pathname: string, href: string): boolean => pathname === href || pathname.startsWith(`${href}/`);
const isActive = (pathname: string, href: string, also: string[] = []): boolean => (href === "/app" ? pathname === "/app" : under(pathname, href) || also.some((a) => under(pathname, a)));

/** The pill-shaped menu across the top on a laptop (the reference's): the page you are on is the black one. */
export function TopNav({ role }: { role: Role }) {
  const pathname = usePathname();
  return (
    <nav aria-label={t("nav.label")} className="hidden flex-1 justify-center lg:flex">
      <ul className="flex items-center gap-1 rounded-full bg-surface/90 p-1 shadow-[0_0_0_1px_var(--c-line)] backdrop-blur-md">
        {itemsFor(role).map((item) => {
          const active = isActive(pathname, item.href, item.also);
          return (
            <li key={item.href}>
              <Link href={item.href} aria-current={active ? "page" : undefined} className={`t-base inline-flex h-9 items-center rounded-full px-4 text-[13px] font-medium ${active ? "bg-accent text-on-accent" : "text-ink hover:bg-sunk"}`}>
                {t(item.label)}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

/** The same places as big rows, in the full-screen menu a phone opens (the browser's own popover: no script to open it). */
export function MenuNav({ role }: { role: Role }) {
  const pathname = usePathname();
  const row = "t-base flex min-h-16 items-center border-b border-line font-display text-[28px] font-medium tracking-[-0.03em]";
  return (
    <nav aria-label={t("nav.label")} className="px-5 pb-10 pt-4 sm:px-8">
      <ul className="grid">
        {itemsFor(role).map((item) => (
          <li key={item.href}>
            <Link href={item.href} aria-current={isActive(pathname, item.href, item.also) ? "page" : undefined} className={`${row} ${isActive(pathname, item.href, item.also) ? "" : "text-muted"}`}>{t(item.label)}</Link>
          </li>
        ))}
        <li>
          <Link href="/app/me" aria-current={isActive(pathname, "/app/me") ? "page" : undefined} className={`${row} gap-3 ${isActive(pathname, "/app/me") ? "" : "text-muted"}`}><UserIcon width={24} height={24} />{t("nav.account")}</Link>
        </li>
        <li>
          <button type="button" onClick={() => void signOut()} className={`${row} w-full gap-3 text-muted`}><LogoutIcon width={24} height={24} />{t("nav.signOut")}</button>
        </li>
      </ul>
    </nav>
  );
}
