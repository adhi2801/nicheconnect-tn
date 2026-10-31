# Interface styles for Colyv: what to take, what to refuse (29 October 2026)

**What this is.** Adhi asked (29 October 2026) which of the current interface styles (glassmorphism, Liquid Glass, neumorphism, claymorphism, bento grids, neo-brutalism, aurora gradients and the rest) Colyv should use, after deep research. This file judges each against what Colyv is: a SaaS product people trust with their work and income, with a Tamil soul (`TAMIL_DESIGN_ROOTS.md` rule 0), used mostly on Android phones in Tamil Nadu (`docs/standards/frontend.md` section 4).

**How it was researched.** Web sources read on 29 October 2026, listed at the end. **Be honest about the evidence:** most "2026 trend" articles are agency marketing with no user testing. Where a claim rests only on those, this file says so. The strongest evidence found is Nielsen Norman Group's guidance, Apple's Human Interface Guidelines, Google's published research on Material 3 Expressive, one peer-reviewed usability study of brutalist sites, and a Mozilla bug report measuring blur on old Android GPUs. **Not done:** testing any of these styles with Tamil brand owners and creators (rule 4). Every choice below is a hypothesis until that test.

---

## 1. The verdict, in one table

| Style | Verdict for Colyv | Why, in one line |
|---|---|---|
| **Solid, high-contrast SaaS surfaces** (Stripe, Linear, Vercel) | **The base. Everywhere content lives** | Readable, fast, and the look of products people trust with money |
| **Glass (Liquid Glass, glassmorphism)** | **Navigation layer only**: the sticky header, the phone's tab bar, the command menu, sheets | Apple itself keeps it off content; contrast fails over busy backgrounds; blur stutters on old Android GPUs |
| **Bento grids** | **Yes, with hierarchy**: the landing page's "what you get", the dashboard's overview | Scans fast; but equal cards were the prototype's flaw, so tiles differ by importance |
| **Material realism** (raised gold, granite, silk, bronze) | **Yes, in a few places only**, as the standard already says | It is our signature, and it means something: gold appears only on what cannot change |
| **Expressive emphasis** (Material 3 Expressive's lesson) | **Yes, for primary actions** | Google measured key controls found up to 4x faster when made bigger, bolder and shaped |
| **Aurora / mesh gradients** | **Only as light**: the temple-dusk light of the hero, never a generic purple wash | A generic gradient is the most templated look on the web today |
| **Fine grain texture** | **Yes, subtle**, on the hero and the signature moments | Makes made light feel like light, not a flat fill; costs a tiny tiled image |
| **Dark mode** | **Yes, both themes from day one** | Tokens make it cheap; temple dusk is a natural dark theme |
| **Neumorphism** | **No** | Buttons and fields barely differ from the background: a contrast failure by design |
| **Claymorphism** | **No** | Toy-like; wrong for deals and payments |
| **Neo-brutalism** (Gumroad) | **No** | The one usability study found breaking conventions hurt; it reads as a joke where people expect care |

**The name for the result: "granite and light".** Solid, precise SaaS structure (the granite), with Tamil material and dusk light entering in three layers only, as rule 0 already says. Glass is a tool for one layer, not the style.

---

## 2. Each style, judged

### 2.1 Glass: Liquid Glass and glassmorphism

- **What it is.** Translucent panels that blur what is behind them (glassmorphism); Apple's 2025 Liquid Glass adds refraction, specular highlights and motion that responds to content.
- **What the best sources say.**
  - Apple's guidelines split materials in two: Liquid Glass is "a distinct functional layer for controls and navigation", and putting it in the content layer "can result in unnecessary complexity and a confusing visual hierarchy"; standard materials serve the content layer. Apple also advises against stacking glass on glass.
  - NN/g: translucency separates foreground from background, but text on it can become hard to read; check contrast, blur more over busy backgrounds, let people turn it down, and use it sparingly.
  - When iOS 26 shipped, accessibility reviewers measured contrast as low as about 1.5:1 in places, against the 4.5:1 that body text needs. Apple added a "Tinted" option in iOS 26.1 that tones the effect down. The reports are commentary from the launch period; how far later updates changed this was not checked.
  - A Mozilla bug report traced stutter and input lag on the mobile Twitter site to CSS `backdrop-filter` on older Adreno GPUs (330 and 530). A Mozilla engineer called the filter "very resource intensive". Budget phones are much of our audience: Counterpoint reports entry phones under ₹15,000 still a large, pressured segment in 2025.
- **How Colyv uses it.**
  - Only on the navigation layer: the sticky header once the page scrolls, the phone's bottom tab bar, the command menu, and sheets that slide over content.
  - Never on cards, tables, forms or anything people read at length.
  - Every glass surface has a solid fallback, used when the browser lacks `backdrop-filter`, when the person asks for reduced transparency (`prefers-reduced-transparency`), and on phones that report low memory or Save-Data. The fallback is the default; the blur is the enhancement.
  - Text on glass is checked at 4.5:1 over the **worst** background it can sit on (the hero render, the dark theme), with a tint behind the text where needed.
  - Our glass is warm: a faint gold edge highlight, the way polished brass catches light, not Apple's cool white.

### 2.2 Bento grids

- **What it is.** A grid of tiles of different sizes, each one idea, popularised by Apple's product pages and now common on SaaS landing pages.
- **Evidence.** Trend articles call it a 2026 standard for SaaS landing pages and dashboards; no user testing was found. The case for it is the plain one: several ideas, each scannable on its own, in a phone-friendly stack.
- **Colyv's rule.** Tiles differ in size by importance, never all equal. The audit of the homepage prototype (`FRONTEND_RESEARCH_2026.md` A1, flaw 7) found "everything is the same card", with flattened hierarchy and empty card bottoms. Each tile shows a real screen or a real number, never an illustration (section 8a). On a phone the grid becomes one column, in order of importance.

### 2.3 Expressive emphasis (from Material 3 Expressive)

- **What it is.** Google's 2025 update to Material Design: bigger, bolder primary actions, varied shapes, emphasised type and spring motion.
- **Evidence.** Google reports 46 studies with over 18,000 participants. A Google Research paper with 48 participants across 10 apps found people fixated on the right element 33% faster and finished tasks 20% faster. Google also warns that expression is not a cure-all: a free-form image layout tested well for looks but badly for clarity. Only the abstract and press coverage were read, not the full paper.
- **Colyv's rule.** Take the measured part: the one action that matters on each screen (send the memo, mark paid, approve the draft) is clearly the largest and most contrasted thing on it. Leave the decorative shapes out.

### 2.4 Material realism, our signature

- **What it is.** Surfaces that look like real materials. The old skeuomorphism, now done with physically based light instead of photo textures.
- **Colyv's rule.** Already set by `frontend.md` 8a and `TAMIL_DESIGN_ROOTS.md`: raised gold only on what cannot change (the sealed record, the seal, a confirmed payment), granite and bronze in the hero and the signature moments, the brand's deep red only at thresholds. This is what makes Colyv look like nothing else. It works because it is rare.

### 2.5 Aurora and mesh gradients

- **Colyv's rule.** Gradients appear only as light that has a source in the scene: the dusk sky behind the temple, lamp glow, gold catching light. A free-floating purple-to-blue wash is the look of a thousand templates, and nothing in our roots asks for it.

### 2.6 Neumorphism, claymorphism and neo-brutalism: refused

- **Neumorphism** draws controls as soft bumps in the same colour as the page, so the contrast between a button and its background is low by design. Several reviews say people, especially with low vision, cannot tell what is pressable. A student usability study compared flat and neumorphic interfaces (University of Warsaw thesis, 12 participants); it is too small and was not read in full.
- **Claymorphism** (puffy, toy-like 3D) suits children's products and games. Deals, payments and disputes need the opposite feeling.
- **Neo-brutalism** (thick black borders, clashing colours; Gumroad uses it). A 2022 study of brutalist websites (Palacios, 3 experiments, 31 participants) concluded that departing from established heuristics hurts the experience. It is the most memorable of these styles and the worst fit for trust.

---

## 3. What this means in the code (proposed, not yet approved)

1. **Design tokens:** solid surfaces for both themes; one `glass` token set (tint, blur, edge highlight) used only by the navigation components; a contrast test in CI for text on every surface token, glass included, over the worst background.
2. **Fallback first:** glass is applied only inside `@supports (backdrop-filter: blur(1px))` and outside `prefers-reduced-transparency: reduce`. A low-end-device switch (`navigator.deviceMemory` at 2 GB or less, or Save-Data) keeps the solid version.
3. **Measure before keeping it:** frame time while scrolling, with and without the glass header, on the budget Android reference phone. If the blur costs frames, it goes on that class of phone (section 8b's budgets).
4. **Bento:** a grid component whose tiles take a size (`hero`, `wide`, `square`) from their importance, stacking to one column on phones.
5. **Grain:** one small tiled noise image at low opacity, on the hero and the signature moments only.

## 4. Decisions for the founders

1. **The direction, "granite and light":** solid SaaS base, glass only for navigation, bento with hierarchy, material realism as the signature, and neumorphism, claymorphism and neo-brutalism refused. **(decision)**
2. **Glass on budget phones:** keep the solid fallback on low-memory phones, or show glass everywhere and accept the frame cost. Recommended: the fallback, until the reference-phone measurement says otherwise. **(decision)**
3. **Test with people before it ships:** show the two strongest versions (glass navigation versus solid navigation) to Tamil brand owners and creators (rule 4). **(founders)**

---

## Sources (read 29 October 2026)

- Nielsen Norman Group, "Glassmorphism: Definition and Best Practices": https://www.nngroup.com/articles/glassmorphism/
- Nielsen Norman Group, "Neobrutalism": https://www.nngroup.com/articles/neobrutalism/
- Apple Human Interface Guidelines, Materials: https://developer.apple.com/design/human-interface-guidelines/materials
- Apple, WWDC25 "Get to know the new design system": https://developer.apple.com/videos/play/wwdc2025/219/
- Apple Developer Forums, WWDC25 design group lab summary: https://developer.apple.com/forums/thread/791070
- Infinum, "Apple's iOS 26 Liquid Glass: sleek, shiny and questionably accessible": https://infinum.com/blog/apples-ios-26-liquid-glass-sleek-shiny-and-questionably-accessible/
- Gulf News, the iOS 26.1 "Tinted" control: https://gulfnews.com/technology/companies/apple-yields-tinted-control-in-ios-261-beta-4-tones-down-liquid-glass-after-backlash-1.500315176
- Google Research, "Usability Hasn't Peaked: Exploring How Expressive Design Overcomes the Usability Plateau": https://research.google/pubs/usability-hasnt-peaked-exploring-how-expressive-design-overcomes-the-usability-plateau/
- Dezeen, Material 3 Expressive: https://www.dezeen.com/2025/05/28/google-ushers-in-age-of-expressive-interfaces-with-material-design-update/
- Mozilla Bugzilla 1828248, `backdrop-filter` stutter on older Adreno GPUs: https://bugzilla.mozilla.org/show_bug.cgi?id=1828248
- Palacios et al., "Web Brutalism: Assessing Usability of an Ugly Web" (HCII 2022): https://cris.pucp.edu.pe/es/publications/web-brutalism-assessing-usability-of-an-ugly-web/
- University of Warsaw thesis, flat versus neumorphic interfaces: https://repozytorium.uw.edu.pl//entities/publication/3195a0a5-e4be-4439-a59b-09292fdff63e
- Counterpoint via FoneArena, India smartphone market 2025: https://www.fonearena.com/blog/474743/india-smartphone-market-2025-counterpoint.html
- Setproduct, the Vercel "blueprint grid" look: https://www.setproduct.com/blog/complete-guide-to-blueprint-grid-design
- Trend roundups, used only to list the styles people are discussing (no testing behind them): https://www.pixelmatters.com/insights/7-UI-design-trends-to-watch-in-2026, https://pixso.net/articles/7-ui-ux-design-trends/
