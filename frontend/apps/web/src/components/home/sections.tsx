import Link from "next/link";
import { CheckIcon, ChevronRightIcon, ArrowRightIcon } from "@/components/ui/icons";
import { DesignSlot } from "@/design/design-slot";
import { t, type MessageKey } from "@/lib/messages";

// Home (frontend/design/website-plan.md section 2): what Colyv is and who it is for, how a deal goes, the product, the record, the
// money promise, both sides, and the way in. Structure in the neutral look (HD-004); the designs arrive in the slots (HD-002).
// Server components only: the page ships no JavaScript of its own, and every word comes from messages/en.json.

const WIDE = "mx-auto w-full max-w-[75rem] px-5 sm:px-8";
const PRIMARY = "t-base inline-flex min-h-12 items-center justify-center rounded-full bg-accent px-7 text-[15px] font-semibold text-on-accent hover:bg-accent-hover active:scale-[0.98]";

function Intro({ id, eyebrow, title, lede, center = false }: { id: string; eyebrow: MessageKey; title: MessageKey; lede?: MessageKey; center?: boolean }) {
  return (
    <div className={`grid gap-4 ${center ? "mx-auto max-w-[44rem] justify-items-center text-center" : "max-w-[46rem]"}`}>
      <p className="type-eyebrow">{t(eyebrow)}</p>
      <h2 id={id} className="type-title">{t(title)}</h2>
      {lede && <p className={`type-lede ${center ? "text-balance" : ""}`}>{t(lede)}</p>}
    </div>
  );
}

export function Hero() {
  return (
    <section aria-labelledby="home-title" className={`${WIDE} pt-16 text-center sm:pt-24 lg:pt-28`}>
      <p className="type-eyebrow">{t("home.hero.eyebrow")}</p>
      <h1 id="home-title" className="type-display mx-auto mt-5 max-w-[18ch]">{t("home.hero.title")}</h1>
      <p className="type-lede mx-auto mt-6 max-w-[40rem] text-balance">{t("home.hero.lede")}</p>
      <div className="mt-10 flex flex-wrap items-center justify-center gap-x-7 gap-y-3">
        <Link href="/sign-in" className={PRIMARY}>{t("home.hero.cta")}</Link>
        <a href="#how" className="t-base group inline-flex min-h-12 items-center gap-1 text-[15px] font-semibold text-ink">
          {t("home.hero.secondary")}
          <ChevronRightIcon width={18} height={18} className="t-base group-hover:translate-x-0.5" />
        </a>
      </div>
      <DesignSlot id="home.hero" className="mt-14 rounded-[1.75rem] sm:mt-20" />
    </section>
  );
}

const STEPS = ["1", "2", "3", "4", "5"] as const;

export function Steps() {
  return (
    <section id="how" aria-labelledby="how-title" className={`${WIDE} scroll-mt-20 py-24 sm:py-32`}>
      <Intro id="how-title" eyebrow="home.steps.eyebrow" title="home.steps.title" lede="home.steps.lede" />
      <ol className="mt-14 grid border-t border-line sm:mt-16 lg:grid-cols-5">
        {STEPS.map((step) => (
          <li key={step} className="grid content-start gap-3 border-b border-line py-7 lg:border-b-0 lg:border-l lg:px-6 lg:pb-0 lg:pt-8 lg:first:border-l-0 lg:first:pl-0 lg:last:pr-0">
            <span className="text-[13px] font-semibold tabular-nums text-muted">{step.padStart(2, "0")}</span>
            <h3 className="text-[17px] font-semibold leading-snug tracking-[-0.01em]">{t(`home.steps.items.${step}.title`)}</h3>
            <p className="text-[15px] leading-6 text-muted">{t(`home.steps.items.${step}.body`)}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}

export function Product() {
  return (
    <section aria-labelledby="product-title" className={`${WIDE} pb-24 sm:pb-32`}>
      <Intro id="product-title" eyebrow="home.product.eyebrow" title="home.product.title" lede="home.product.lede" center />
      <DesignSlot id="home.product" className="mt-14 rounded-[1.75rem] sm:mt-16" />
    </section>
  );
}

export function Record() {
  return (
    <section aria-labelledby="record-title" className="border-t border-line bg-surface">
      <div className={`${WIDE} grid items-center gap-14 py-24 sm:py-32 lg:grid-cols-[minmax(0,1fr)_minmax(0,30rem)] lg:gap-20`}>
        <div>
          <Intro id="record-title" eyebrow="home.record.eyebrow" title="home.record.title" lede="home.record.lede" />
          <ul className="mt-10 grid border-t border-line">
            {(["1", "2", "3"] as const).map((point) => (
              <li key={point} className="flex gap-4 border-b border-line py-5 text-[16px] leading-6">
                <span aria-hidden className="mt-0.5 inline-flex size-5 shrink-0 items-center justify-center rounded-full bg-accent text-on-accent">
                  <CheckIcon width={12} height={12} strokeWidth={3} />
                </span>
                {t(`home.record.points.${point}`)}
              </li>
            ))}
          </ul>
        </div>
        <DesignSlot id="home.record" className="mx-auto rounded-[1.75rem]" />
      </div>
    </section>
  );
}

export function Money() {
  return (
    <section aria-labelledby="money-title" className="border-y border-line">
      <div className={`${WIDE} py-24 sm:py-36`}>
        <div className="mx-auto grid max-w-[48rem] justify-items-center gap-5 text-center">
          <p className="type-eyebrow">{t("home.money.eyebrow")}</p>
          <h2 id="money-title" className="type-display">{t("home.money.title")}</h2>
          <p className="type-lede max-w-[40rem] text-balance">{t("home.money.body")}</p>
        </div>
      </div>
    </section>
  );
}

const SIDES = [
  { side: "brands", href: "/brands" },
  { side: "creators", href: "/creators" },
] as const;

export function Sides() {
  return (
    <section aria-labelledby="sides-title" className={`${WIDE} py-24 sm:py-32`}>
      <Intro id="sides-title" eyebrow="home.sides.eyebrow" title="home.sides.title" />
      <div className="mt-14 grid gap-5 sm:mt-16 md:grid-cols-2">
        {SIDES.map(({ side, href }) => (
          <article key={side} aria-labelledby={`side-${side}`} className="grid content-start rounded-[1.75rem] border border-line bg-surface p-7 sm:p-10">
            <h3 id={`side-${side}`} className="type-subtitle">{t(`home.sides.${side}.title`)}</h3>
            <ul className="mt-7 grid border-t border-line">
              {(["1", "2", "3"] as const).map((point) => (
                <li key={point} className="border-b border-line py-4 text-[15px] leading-6 text-muted">{t(`home.sides.${side}.points.${point}`)}</li>
              ))}
            </ul>
            <Link href={href} prefetch={false} className="t-base group mt-7 inline-flex min-h-11 items-center gap-1.5 justify-self-start text-[15px] font-semibold text-ink">
              {t(`home.sides.${side}.more`)}
              <ArrowRightIcon width={16} height={16} className="t-base group-hover:translate-x-0.5" />
            </Link>
          </article>
        ))}
      </div>
    </section>
  );
}

export function Closing() {
  return (
    <section aria-labelledby="closing-title" className={`${WIDE} pb-24 sm:pb-32`}>
      <div className="grid justify-items-center gap-5 rounded-[1.75rem] bg-sunk px-6 py-20 text-center sm:py-24">
        <h2 id="closing-title" className="type-title max-w-[20ch]">{t("home.closing.title")}</h2>
        <p className="type-lede max-w-[34rem] text-balance">{t("home.closing.body")}</p>
        <Link href="/sign-in" className={`${PRIMARY} mt-4`}>{t("home.closing.cta")}</Link>
      </div>
    </section>
  );
}
