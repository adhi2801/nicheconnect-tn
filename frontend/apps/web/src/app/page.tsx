import { Closing, Hero, Money, Product, Record, Sides, Steps } from "@/components/home/sections";
import { SiteFooter } from "@/components/site/site-footer";
import { SiteHeader } from "@/components/site/site-header";

// Home (frontend/design/website-plan.md section 2): the structure, in the neutral look, with design slots where the temple, the
// product board and the seal will go (HD-002). Server-rendered and complete with no script.
export default function Home() {
  return (
    <>
      <SiteHeader />
      <main>
        <Hero />
        <Steps />
        <Product />
        <Record />
        <Money />
        <Sides />
        <Closing />
      </main>
      <SiteFooter />
    </>
  );
}
