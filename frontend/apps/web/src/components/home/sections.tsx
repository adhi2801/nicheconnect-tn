import Link from "next/link";
import { ArrowRightIcon, CheckIcon, ChevronRightIcon } from "@/components/ui/icons";
import { DesignSlot } from "@/design/design-slot";
import { t, type MessageKey } from "@/lib/messages";

// Home (frontend/design/website-plan.md section 2) in the look of HD-007: white rounded cards on the soft tint, near-black for the main
// button, lime for the highlights, one sage card and one black card. The designs arrive in the slots (HD-002).
// Server components only: the page ships no JavaScript of its own, and every word comes from messages/en.json.

const WIDE = "mx-auto w-full max-w-[75rem] px-5 sm:px-8";
const CARD = "shadow-card rounded-[2rem] bg-surface";
const PRIMARY = "t-base inline-flex min-h-12 items-center justify-center rounded-full bg-accent px-7 text-[15px] font-semibold text-on-accent hover:bg-accent-hover active:scale-[0.98]";

/** A small label pill with a lime dot: the reference's tag. */
function Tag({ k, className = "" }: { k: MessageKey; className?: string }) {
  return (
    <p className={`shadow-card inline-flex h-8 items-center gap-2 rounded-full bg-surface px-3.5 text-[13px] font-medium ${className}`}>
      <span aria-hidden className="size-2 rounded-full bg-lime" />
      {t(k)}
    </p>
  );
}

function Intro({ id, eyebrow, title, lede, center = false }: { id: string; eyebrow: MessageKey; title: MessageKey; lede?: MessageKey; center?: boolean }) {
  return (
    <div className={`grid gap-5 ${center ? "mx-auto max-w-[44rem] justify-items-center text-center" : "max-w-[46rem] justify-items-start"}`}>
      <Tag k={eyebrow} />
      <h2 id={id} className="type-title">{t(title)}</h2>
      {lede && <p className={`type-lede ${center ? "text-balance" : ""}`}>{t(lede)}</p>}
    </div>
  );
}

export function Hero() {
  return (
    <section aria-labelledby="home-title" className={`${WIDE} pt-14 text-center sm:pt-20 lg:pt-24`}>
      <Tag k="home.hero.eyebrow" />
      <h1 id="home-title" className="type-display mx-auto mt-6 max-w-[18ch]">{t("home.hero.title")}</h1>
      <p className="type-lede mx-auto mt-6 max-w-[40rem] text-balance">{t("home.hero.lede")}</p>
      <div className="mt-10 flex flex-wrap items-center justify-center gap-x-7 gap-y-3">
        <Link href="/sign-in" className={PRIMARY}>{t("home.hero.cta")}</Link>
        <a href="#how" className="t-base group inline-flex min-h-12 items-center gap-1 text-[15px] font-semibold text-ink">
          {t("home.hero.secondary")}
          <ChevronRightIcon width={18} height={18} className="t-base group-hover:translate-x-0.5" />
        </a>
      </div>
      <div className={`${CARD} mt-14 p-2 sm:mt-20 sm:p-3`}>
        <DesignSlot id="home.hero" className="rounded-[1.5rem]" />
      </div>
    </section>
  );
}

const STEPS = ["1", "2", "3", "4", "5"] as const;

export function Steps() {
  return (
    <section id="how" aria-labelledby="how-title" className={`${WIDE} scroll-mt-24 py-24 sm:py-32`}>
      <Intro id="how-title" eyebrow="home.steps.eyebrow" title="home.steps.title" lede="home.steps.lede" />
      <ol className="mt-12 grid gap-4 sm:mt-14 sm:grid-cols-2 lg:grid-cols-5">
        {STEPS.map((step) => (
          // The last step, the creator being paid, is the one tinted card, as the reference tints one card on its board.
          <li key={step} className={`${step === "5" ? "rounded-[2rem] bg-sage shadow-[0_0_0_1px_var(--c-line)] sm:col-span-2 lg:col-span-1" : CARD} grid content-start gap-3 p-6`}>
            <span className="inline-flex h-7 w-fit items-center rounded-full bg-lime px-3 text-[12px] font-semibold tabular-nums text-on-lime">{step.padStart(2, "0")}</span>
            <h3 className="mt-3 text-[17px] font-semibold leading-snug tracking-[-0.01em]">{t(`home.steps.items.${step}.title`)}</h3>
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
      <div className={`${CARD} mt-12 p-2 sm:mt-14 sm:p-3`}>
        <DesignSlot id="home.product" className="rounded-[1.5rem]" />
      </div>
    </section>
  );
}

export function Record() {
  return (
    <section aria-labelledby="record-title" className={`${WIDE} pb-24 sm:pb-32`}>
      <div className={`${CARD} grid items-center gap-12 p-7 sm:p-12 lg:grid-cols-[minmax(0,1fr)_minmax(0,28rem)] lg:gap-16`}>
        <div>
          <Intro id="record-title" eyebrow="home.record.eyebrow" title="home.record.title" lede="home.record.lede" />
          <ul className="mt-9 grid gap-3">
            {(["1", "2", "3"] as const).map((point) => (
              <li key={point} className="flex items-start gap-4 rounded-2xl bg-sunk p-4 text-[16px] leading-6">
                <span aria-hidden className="mt-0.5 inline-flex size-6 shrink-0 items-center justify-center rounded-full bg-lime text-on-lime">
                  <CheckIcon width={14} height={14} strokeWidth={3} />
                </span>
                {t(`home.record.points.${point}`)}
              </li>
            ))}
          </ul>
        </div>
        <DesignSlot id="home.record" className="mx-auto rounded-[1.5rem]" />
      </div>
    </section>
  );
}

export function Money() {
  return (
    <section aria-labelledby="money-title" className={`${WIDE} pb-24 sm:pb-32`}>
      <div className="grid justify-items-center gap-6 rounded-[2rem] bg-sage px-6 py-20 text-center shadow-[0_0_0_1px_var(--c-line)] sm:py-28">
        <Tag k="home.money.eyebrow" />
        <h2 id="money-title" className="type-display max-w-[16ch]">{t("home.money.title")}</h2>
        <p className="type-lede max-w-[40rem] text-balance">{t("home.money.body")}</p>
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
    <section aria-labelledby="sides-title" className={`${WIDE} pb-24 sm:pb-32`}>
      <Intro id="sides-title" eyebrow="home.sides.eyebrow" title="home.sides.title" />
      <div className="mt-12 grid gap-4 sm:mt-14 md:grid-cols-2">
        {SIDES.map(({ side, href }) => (
          <article key={side} aria-labelledby={`side-${side}`} className={`${CARD} grid content-start p-7 sm:p-10`}>
            <h3 id={`side-${side}`} className="type-subtitle">{t(`home.sides.${side}.title`)}</h3>
            <ul className="mt-7 grid gap-2">
              {(["1", "2", "3"] as const).map((point) => (
                <li key={point} className="rounded-2xl bg-sunk px-4 py-3.5 text-[15px] leading-6 text-muted">{t(`home.sides.${side}.points.${point}`)}</li>
              ))}
            </ul>
            <Link href={href} prefetch={false} className="t-base group mt-7 inline-flex min-h-11 items-center gap-3 justify-self-start text-[15px] font-semibold text-ink">
              <span aria-hidden className="t-base inline-flex size-11 items-center justify-center rounded-full bg-lime text-on-lime group-hover:translate-x-0.5">
                <ArrowRightIcon width={18} height={18} />
              </span>
              {t(`home.sides.${side}.more`)}
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
      <div className="grid justify-items-center gap-5 rounded-[2rem] bg-accent px-6 py-20 text-center text-on-accent sm:py-24">
        <h2 id="closing-title" className="type-title max-w-[20ch]">{t("home.closing.title")}</h2>
        <p className="max-w-[34rem] text-balance text-[18px] leading-7 text-on-accent/80">{t("home.closing.body")}</p>
        <Link href="/sign-in" className="t-base mt-4 inline-flex min-h-12 items-center justify-center rounded-full bg-lime px-7 text-[15px] font-semibold text-on-lime hover:brightness-95 active:scale-[0.98]">{t("home.closing.cta")}</Link>
      </div>
    </section>
  );
}
