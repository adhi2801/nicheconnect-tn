import Link from "next/link";
import { CloseIcon, MenuIcon } from "@/components/ui/icons";
import { DesignSlot } from "@/design/design-slot";
import { t, type MessageKey } from "@/lib/messages";

// The public pages' links (frontend/design/website-plan.md section 2). Pages not built yet answer "not found" until they are, so no
// link is prefetched: a prefetch of a missing page would only add a failed request to the console.
export const SITE_LINKS: { href: string; key: MessageKey }[] = [
  { href: "/creators", key: "site.nav.creators" },
  { href: "/brands", key: "site.nav.brands" },
  { href: "/how-it-works", key: "site.nav.how" },
  { href: "/trust", key: "site.nav.trust" },
];

const MENU = "site-menu";

/** The wordmark, inside the logo's design slot: the designer's logo replaces it with one line in src/design/registry.ts. */
export function Wordmark() {
  return (
    <Link href="/" aria-label={t("site.home")} className="t-base inline-flex h-11 w-fit items-center rounded-full border border-line-strong bg-surface/70 px-4">
      <DesignSlot id="brand.mark" fallback={<span className="block font-display text-[21px] font-semibold leading-7 tracking-[-0.035em]">{t("site.brand")}</span>} />
    </Link>
  );
}

/**
 * The public pages' header: the wordmark, four links, Sign in and the one action. On a phone the links move into a full-screen menu
 * opened by the browser's own popover, so the menu works with no script at all (frontend.md section 8d), and Escape or a tap
 * outside closes it.
 */
export function SiteHeader({ current }: { current?: string }) {
  return (
    <header className="sticky top-0 z-40 pt-3 sm:pt-4">
      <div className="mx-auto flex h-14 w-full max-w-[75rem] items-center gap-4 px-5 sm:px-8">
        <Wordmark />
        <nav aria-label={t("site.nav.label")} className="hidden flex-1 justify-center lg:flex">
          <ul className="flex items-center gap-1 rounded-full bg-surface/90 p-1 shadow-[0_0_0_1px_var(--c-line)] backdrop-blur-md">
            {SITE_LINKS.map((link) => {
              const here = current === link.href;
              return (
                <li key={link.href}>
                  <Link
                    href={link.href}
                    prefetch={false}
                    aria-current={here ? "page" : undefined}
                    className={`t-base inline-flex h-9 items-center rounded-full px-4 text-[13px] font-medium ${here ? "bg-accent text-on-accent" : "text-ink hover:bg-sunk"}`}
                  >
                    {t(link.key)}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>
        <div className="ml-auto flex items-center gap-2 lg:ml-0">
          <Link href="/sign-in" className="t-base hidden h-11 items-center rounded-full bg-surface/90 px-5 text-[13px] font-medium text-ink shadow-[0_0_0_1px_var(--c-line)] hover:bg-surface sm:inline-flex">{t("site.nav.signIn")}</Link>
          <Link href="/sign-in" className="t-base inline-flex h-11 items-center rounded-full bg-accent px-5 text-[13px] font-semibold text-on-accent hover:bg-accent-hover active:scale-[0.98]">{t("site.nav.start")}</Link>
          <button type="button" popoverTarget={MENU} aria-label={t("site.nav.menu")} className="t-base inline-flex size-11 items-center justify-center rounded-full bg-surface/90 text-ink shadow-[0_0_0_1px_var(--c-line)] hover:bg-surface lg:hidden">
            <MenuIcon width={20} height={20} />
          </button>
        </div>
      </div>

      <div id={MENU} popover="auto" aria-label={t("site.nav.label")} className="site-menu fixed inset-0 m-0 h-dvh max-h-none w-full max-w-none overflow-y-auto border-0 bg-ground p-0 text-ink">
        <div className="flex h-16 items-center justify-between px-5 sm:px-8">
          <Wordmark />
          <button type="button" popoverTarget={MENU} popoverTargetAction="hide" aria-label={t("site.nav.close")} className="t-base -mr-2 inline-flex size-11 items-center justify-center rounded-full hover:bg-sunk">
            <CloseIcon width={22} height={22} />
          </button>
        </div>
        <nav aria-label={t("site.nav.label")} className="px-5 pb-10 pt-4 sm:px-8">
          <ul className="grid">
            {SITE_LINKS.map((link) => (
              <li key={link.href} className="border-b border-line">
                <Link href={link.href} prefetch={false} className="flex min-h-16 items-center font-display text-[28px] font-semibold tracking-[-0.03em]">{t(link.key)}</Link>
              </li>
            ))}
          </ul>
          <div className="mt-8 grid gap-3">
            <Link href="/sign-in" className="t-base inline-flex min-h-12 items-center justify-center rounded-full bg-accent px-6 text-[15px] font-semibold text-on-accent hover:bg-accent-hover">{t("site.nav.start")}</Link>
            <Link href="/sign-in" className="t-base inline-flex min-h-12 items-center justify-center rounded-full border border-line-strong px-6 text-[15px] font-semibold hover:bg-sunk">{t("site.nav.signIn")}</Link>
          </div>
        </nav>
      </div>
    </header>
  );
}
