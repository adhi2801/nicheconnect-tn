import Link from "next/link";
import { StageColumn } from "@/components/deals/stage-column";
import { EXAMPLE_BOARD } from "@/lib/landing-examples";
import { t, type MessageKey } from "@/lib/messages";

// The landing page below the hero (LANDING_CULTURE_FIT.md, the sections judged "keep"). Server components only: they
// ship no JavaScript, and every word comes from messages/en.json.

const STEPS = ["1", "2", "3", "4", "5"] as const;
// The Tamil script's own digits, one to five (LANDING_CULTURE_FIT.md Part D).
const TAMIL_DIGITS: Record<(typeof STEPS)[number], string> = { "1": "௧", "2": "௨", "3": "௩", "4": "௪", "5": "௫" };

function Eyebrow({ k }: { k: MessageKey }) {
  return <p className="text-xs font-semibold uppercase tracking-[0.18em] text-accent">{t(k)}</p>;
}

export function HeroText() {
  return (
    <div className="max-w-2xl">
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[var(--stage-muted)]">{t("landing.hero.eyebrow")}</p>
      <h1 id="landing-title" className="mt-4 font-display text-4xl font-semibold leading-[1.05] tracking-tight sm:text-6xl">
        {t("landing.hero.title")}
      </h1>
      <p className="mt-5 max-w-xl text-base leading-relaxed text-[var(--stage-muted)] sm:text-lg">{t("landing.hero.lede")}</p>
      <div className="mt-8 flex flex-wrap items-center gap-4">
        <Link href="/sign-in" className="t-base rounded-full bg-[var(--stage-ink)] px-6 py-3 text-sm font-semibold text-[var(--stage)] hover:bg-white focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[var(--stage-ink)]">
          {t("landing.hero.cta")}
        </Link>
        <a href="#how" className="t-base rounded-full px-2 py-3 text-sm font-semibold text-[var(--stage-ink)] underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[var(--stage-ink)]">
          {t("landing.hero.secondary")}
        </a>
      </div>
    </div>
  );
}

export function SiteHeader() {
  return (
    <header className="absolute inset-x-0 top-0 z-10">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-5 text-[var(--stage-ink)]">
        <Link href="/" className="font-display text-xl font-semibold tracking-tight">{t("landing.nav.brand")}</Link>
        <Link href="/sign-in" className="t-base rounded-full border border-white/25 px-4 py-2 text-sm font-medium hover:border-white/60 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--stage-ink)]">
          {t("landing.nav.signIn")}
        </Link>
      </div>
    </header>
  );
}

export function Steps() {
  return (
    <section id="how" aria-labelledby="how-title" className="mx-auto max-w-6xl scroll-mt-8 px-6 py-24 sm:py-32">
      <Eyebrow k="landing.steps.eyebrow" />
      <h2 id="how-title" className="mt-3 max-w-2xl font-display text-3xl font-semibold tracking-tight sm:text-5xl">{t("landing.steps.title")}</h2>
      <p className="mt-4 max-w-2xl text-lg leading-relaxed text-muted">{t("landing.steps.lede")}</p>
      <ol className="mt-14 grid gap-5 sm:grid-cols-2 lg:grid-cols-5">
        {STEPS.map((step) => (
          <li key={step} className="shadow-card flex flex-col rounded-xl bg-surface p-6">
            <span className="tamil-numeral text-3xl leading-none text-accent" aria-hidden>{TAMIL_DIGITS[step]}</span>
            <span className="sr-only">{step}.</span>
            <h3 className="mt-5 font-display text-lg font-semibold leading-snug">{t(`landing.steps.items.${step}.title` as MessageKey)}</h3>
            <p className="mt-2 text-sm leading-relaxed text-muted">{t(`landing.steps.items.${step}.body` as MessageKey)}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}

/** The product itself: the app's own deal board, fed three example deals, as a creator sees it. Not a picture of a screen, and
 *  the caption says the deals are made up. */
export function Product() {
  const noPayments = new Map();
  return (
    <section aria-labelledby="product-title" className="mx-auto max-w-6xl px-6 pb-24 sm:pb-32">
      <Eyebrow k="landing.product.eyebrow" />
      <h2 id="product-title" className="mt-3 max-w-3xl font-display text-3xl font-semibold tracking-tight sm:text-5xl">{t("landing.product.title")}</h2>
      <p className="mt-4 max-w-2xl text-lg leading-relaxed text-muted">{t("landing.product.lede")}</p>
      <figure className="mt-12">
        <div className="rounded-[2rem] bg-sunk p-4 sm:p-6">
          <div className="grid gap-6 lg:grid-cols-3">
            {EXAMPLE_BOARD.map(({ stage, memo }, i) => (
              <StageColumn key={stage} stage={stage} memos={[memo]} role="creator" byMemo={noPayments} connect={i > 0} preview />
            ))}
          </div>
        </div>
        <figcaption className="mt-4 text-sm text-muted">{t("landing.product.caption")}</figcaption>
      </figure>
    </section>
  );
}

export function Record() {
  return (
    <section aria-labelledby="record-title" className="landing-stage">
      <div className="mx-auto grid max-w-6xl items-center gap-12 px-6 py-24 sm:py-32 lg:grid-cols-2">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--stage-muted)]">{t("landing.record.eyebrow")}</p>
          <h2 id="record-title" className="mt-3 font-display text-3xl font-semibold tracking-tight sm:text-5xl">{t("landing.record.title")}</h2>
          <p className="mt-5 text-lg leading-relaxed text-[var(--stage-muted)]">{t("landing.record.lede")}</p>
          <ul className="mt-8 space-y-4">
            {(["1", "2", "3"] as const).map((point) => (
              <li key={point} className="flex gap-3 text-base leading-relaxed">
                <span aria-hidden className="mt-2.5 h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--stage-ink)]" />
                {t(`landing.record.points.${point}` as MessageKey)}
              </li>
            ))}
          </ul>
        </div>
        {/* eslint-disable-next-line @next/next/no-img-element -- pre-sized WebP from export_landing.py; no optimiser to run */}
        <img
          src="/landing/seal-960.webp"
          srcSet="/landing/seal-640.webp 640w, /landing/seal-960.webp 960w"
          sizes="(min-width: 1024px) 560px, 92vw"
          width={960}
          height={960}
          alt={t("landing.record.imageAlt")}
          loading="lazy"
          decoding="async"
          className="mx-auto w-full max-w-[560px] rounded-xl"
        />
      </div>
    </section>
  );
}

export function Money() {
  return (
    <section aria-labelledby="money-title" className="mx-auto max-w-6xl px-6 py-24 sm:py-32">
      <div className="hero rounded-xl px-8 py-14 sm:px-14">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] opacity-80">{t("landing.money.eyebrow")}</p>
        <h2 id="money-title" className="mt-3 max-w-3xl font-display text-3xl font-semibold tracking-tight sm:text-5xl">{t("landing.money.title")}</h2>
        <p className="mt-5 max-w-2xl text-lg leading-relaxed opacity-90">{t("landing.money.body")}</p>
      </div>
    </section>
  );
}

export function Sides() {
  const sides = ["brands", "creators"] as const;
  return (
    <section aria-labelledby="sides-title" className="mx-auto max-w-6xl px-6 pb-24 sm:pb-32">
      <Eyebrow k="landing.sides.eyebrow" />
      <h2 id="sides-title" className="sr-only">{t("landing.sides.eyebrow")}</h2>
      <div className="mt-6 grid gap-5 md:grid-cols-2">
        {sides.map((side) => (
          <article key={side} className="shadow-card rounded-xl bg-surface p-8">
            <h3 className="font-display text-2xl font-semibold tracking-tight">{t(`landing.sides.${side}.title` as MessageKey)}</h3>
            <ul className="mt-6 space-y-4">
              {(["1", "2", "3"] as const).map((point) => (
                <li key={point} className="flex gap-3 leading-relaxed text-muted">
                  <span aria-hidden className="mt-2.5 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
                  {t(`landing.sides.${side}.points.${point}` as MessageKey)}
                </li>
              ))}
            </ul>
          </article>
        ))}
      </div>
    </section>
  );
}

export function Closing() {
  return (
    <section aria-labelledby="closing-title" className="border-t border-line">
      <div className="mx-auto flex max-w-6xl flex-col items-start gap-6 px-6 py-20 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 id="closing-title" className="font-display text-3xl font-semibold tracking-tight">{t("landing.closing.title")}</h2>
          <p className="mt-2 text-muted">{t("landing.closing.body")}</p>
        </div>
        <Link href="/sign-in" className="t-base shrink-0 rounded-full bg-accent px-6 py-3 text-sm font-semibold text-on-accent hover:bg-accent-hover focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-accent">
          {t("landing.closing.cta")}
        </Link>
      </div>
      <footer className="mx-auto flex max-w-6xl flex-col gap-2 border-t border-line px-6 py-8 text-sm text-muted sm:flex-row sm:justify-between">
        <p>{t("landing.footer.line")}</p>
        <p>{t("landing.footer.rights", { year: new Date().getFullYear() })}</p>
      </footer>
    </section>
  );
}
