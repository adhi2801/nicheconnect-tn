import { HeroOrbit } from "@/components/landing/hero-orbit";
import { Closing, HeroText, Money, Record, SiteHeader, Sides, Steps } from "@/components/landing/sections";
import { t } from "@/lib/messages";

// The landing page (D-141): the turning temple, then what a deal is, the record, the money promise, both sides, and the
// way in. Server-rendered and readable with no script; only the hero's turn runs in the browser.
export default function Home() {
  return (
    <main>
      <div className="landing-stage relative">
        <SiteHeader />
        <HeroOrbit alt={t("landing.hero.imageAlt")}>
          <HeroText />
        </HeroOrbit>
      </div>
      <Steps />
      <Record />
      <Money />
      <Sides />
      <Closing />
    </main>
  );
}
