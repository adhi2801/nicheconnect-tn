import Link from "next/link";
import { DesignSlot } from "@/design/design-slot";
import { t, type MessageKey } from "@/lib/messages";
import { Wordmark } from "./site-header";

const GROUPS: { key: MessageKey; links: { href: string; key: MessageKey }[] }[] = [
  {
    key: "site.footer.groups.product",
    links: [
      { href: "/creators", key: "site.footer.links.creators" },
      { href: "/brands", key: "site.footer.links.brands" },
      { href: "/how-it-works", key: "site.footer.links.how" },
      { href: "/trust", key: "site.footer.links.trust" },
    ],
  },
  {
    key: "site.footer.groups.company",
    links: [
      { href: "/about", key: "site.footer.links.about" },
      { href: "/help", key: "site.footer.links.help" },
      { href: "/pilot", key: "site.footer.links.pilot" },
    ],
  },
  {
    key: "site.footer.groups.legal",
    links: [
      { href: "/legal/privacy", key: "site.footer.links.privacy" },
      { href: "/legal/terms", key: "site.footer.links.terms" },
    ],
  },
];

/** The public pages' footer, with the ornament band's design slot above it. */
export function SiteFooter() {
  return (
    <footer className="mt-auto">
      <DesignSlot id="footer.ornament" className="!bg-transparent" />
      <div className="border-t border-line">
        <div className="mx-auto grid w-full max-w-[75rem] gap-12 px-5 py-14 sm:px-8 lg:grid-cols-[1fr_auto] lg:gap-24">
          <div className="grid content-start gap-3">
            <Wordmark />
            <p className="max-w-[22rem] text-[15px] leading-6 text-muted">{t("site.footer.tagline")}</p>
          </div>
          <nav aria-label={t("site.footer.label")} className="grid grid-cols-2 gap-x-8 gap-y-10 sm:grid-cols-3 lg:gap-x-16">
            {GROUPS.map((group) => (
              <div key={group.key} className="grid content-start gap-3">
                <h2 className="text-[13px] font-semibold text-ink">{t(group.key)}</h2>
                <ul className="grid gap-1">
                  {group.links.map((link) => (
                    <li key={link.href}>
                      <Link href={link.href} prefetch={false} className="t-base inline-flex min-h-11 items-center text-[14px] sm:min-h-9 text-muted hover:text-ink">{t(link.key)}</Link>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </nav>
        </div>
        <div className="mx-auto flex w-full max-w-[75rem] flex-col gap-2 border-t border-line px-5 py-6 text-[13px] text-muted sm:flex-row sm:justify-between sm:px-8">
          <p>{t("site.footer.line")}</p>
          <p>{t("site.footer.rights", { year: new Date().getFullYear() })}</p>
        </div>
      </div>
    </footer>
  );
}
