import Link from "next/link";
import { t } from "@/lib/app-messages";

/** Two places a creator moves between while finding work: what is open, and what they already sent. Links, so each has its address. */
export function DiscoverTabs({ current }: { current: "open" | "mine" }) {
  const tab = (id: "open" | "mine", href: string) => (
    <Link href={href} aria-current={current === id ? "page" : undefined} className={`t-base inline-flex min-h-10 items-center rounded-full px-4 text-sm font-semibold ${current === id ? "bg-ink text-on-accent" : "text-muted hover:text-ink"}`}>
      {t(id === "open" ? "discover.tabs.open" : "discover.tabs.mine")}
    </Link>
  );
  return (
    <nav aria-label={t("discover.tabs.label")} className="inline-flex gap-1 justify-self-start rounded-full bg-sunk p-1">
      {tab("open", "/app/discover")}
      {tab("mine", "/app/applications")}
    </nav>
  );
}
