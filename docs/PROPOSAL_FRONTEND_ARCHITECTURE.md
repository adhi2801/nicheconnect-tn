# Proposal: the Colyv frontend, built properly

**Status: Proposed, 30 October 2026. Nothing here is approved, and nothing below is built until it is.** Written by Claude for Adhi, after Adhi said (30 October 2026): stop patching the landing-page prototype; design a world-class frontend architecture first, every part of it (UI, UX, components, motion, animation), with aesthetics leading; be honest; no rushed work. **Not reviewed by Erode Harish**, who owns frontend design research (CLAUDE.md section 0).

**Read with:** `docs/standards/frontend.md` (the bar, binding), `docs/research/FRONTEND_RESEARCH_2026.md` (the audit and sixteen areas of research), `docs/research/TAMIL_DESIGN_ROOTS.md` (where every visual choice must trace to), `docs/PSYCHOLOGY_AND_TRUST.md`, the "granite and light" style research on branch `docs/ui-styles` (`docs/research/UI_STYLES_2026.md`), and `frontend/design/screen-plan.md` and `execution-plan.md` (Harish's screens and dates). This proposal does not repeat them; it puts them into one architecture and says what is decided, what is open, and in what order it gets built.

---

## 1. Where we are, honestly

| Area | State on 30 October 2026 | Verdict |
|---|---|---|
| Backend | 200+ API operations, about 2,000 tests, 98% coverage, strict types, fuzzing, a tamper-evident deal record | The standard the frontend has to meet |
| Web app (`frontend/apps/web`) | Next.js 16.4.3, React 19.3.1, Tailwind 4.3, Motion 14, TanStack Query 5, Playwright 1.64. About 1,500 lines of screens: sign-in, app shell, Today, the Deals board, a design system v1 in green | Current tools, thin foundations. Adhi called it "like a kid project" (28 October) |
| Landing prototype (`frontend/prototypes/homepage.html`) | One 381 KB file, 17 sections, a live three.js gopuram (534 draw calls a frame in the audit), 2D line-art temples, CSS phone mock-ups, kolams on most sections, burgundy and gold | Adhi (30 October): "an absolute mess". Too long, too many kolams, the 2D temple reads as a child's drawing, the phone pictures are old |
| Temple | Blender renders of the vimana exist (4K hero, crown detail, a 48-frame turn) | Not on any page. Open faults listed in the render notes (granite reads as plaster, the lamp is hidden, no people) |
| Fold section (built 30 October, branch `feature/fold-scroll`) | A live three.js folding phone, six chapters, the deal seal drawn across the crease | The idea is strong (section 5.3). The build was wrong: live 3D plus large canvas textures made the page hang, and six chapters pinned the scroll for almost seven screens. **Not to be merged as is** |
| Colour | The prototype is burgundy and gold; Harish's app is deep green | Unresolved. It blocks every visual decision |
| Research done | Sixteen areas (frontend research), styles, Tamil roots, psychology, culture fit, colour (started 30 October) | Good. Not yet turned into one system |
| Research owed | Real people: no five-second test or task test has been run with Tamil brand owners or creators | The biggest honest gap. Taste is not evidence |

**Why it went wrong.** Pages were built before the system under them existed, and with the colour, the style and the temple still undecided. Each pass patched the page instead of laying a foundation, so every fix exposed the next flaw. The cure is the order of work in section 6: decisions, then foundations, then components, then signature pieces, then pages.

---

## 2. The idea that holds it together

**A SaaS product first, with a Tamil soul** (D-141, `TAMIL_DESIGN_ROOTS.md` rule 0), in the style called **granite and light** (`UI_STYLES_2026.md`):

- **Granite:** the structure, type, spacing and speed of the best SaaS products (Stripe, Linear, Vercel, Mercury). Solid surfaces wherever people read. Calm.
- **Light:** Tamil roots enter only as material (bronze, raised gold, granite), light (temple dusk, lamp glow) and a few signature moments. Never as wallpaper. **At most one ornament per screen, and none on working screens.**
- **Meaning before decoration:** gold appears only on what cannot change (a sealed record, a confirmed payment); the brand's deep red only at thresholds; colour carries state, never mood alone.

**The test for every element:** what job does it do for a brand owner or a creator, and which root or research does it trace to? If neither, it is cut (`frontend.md` 8a).

---

## 3. The architecture: forty-one parts

Each part says what world-class means here, our choice, and how it is proven. **(decision)** marks a choice that needs a founder.

### A. Identity and aesthetics

| # | Part | Our choice | Proven by |
|---|---|---|---|
| 1 | Direction | Granite and light **(decision)** | Side-by-side against Stripe, Linear and Mercury pages, judged by a founder (8a) |
| 2 | Colour | One system for the website and both apps, in OKLCH tokens so both themes keep equal contrast. **Restraint**: a near-neutral warm base, one brand accent, four state colours, gold reserved for sealed things. Burgundy or green decided by a test, not taste **(decision; section 4)** | Contrast checked in CI for every text-on-surface pair; the colour test in section 4 |
| 3 | Type | A display serif for headlines, one UI sans for everything people read, a mono for fingerprints and references; tabular numerals for money; Indian grouping (₹1,50,000) through `Intl` `en-IN`. Self-hosted, subset, metric-matched fallbacks | No layout shift from fonts (CLS budget 0.05); 200% text test |
| 4 | Mark | Waits on the name and domain (Colyv, backlog item 4); a designer brief inside the ₹5,000 budget | A founder's yes |
| 5 | Icons | One set on a 24 grid, one stroke weight, plus our own glyphs for domain objects (memo, proof, seal, UPI, record) | Visual regression of the icon sheet |
| 6 | Imagery | Real product screens only, rendered from the real components with sample data, labelled sample; nothing is a photograph (D-142) | Every image traced to a component or a made asset |
| 7 | Material and light | Granite, bronze and raised-gold recipes (`TAMIL_DESIGN_ROOTS.md` 12.5, 12.6, 12.9); one light source per scene; fine grain on signature moments only | Founder review of each material against references |
| 8 | Layout | A 12-column grid, an 8-point spacing scale, a reading width; bento tiles sized by importance, never all equal; air on marketing pages, density in the app | Visual regression at 360 px and desktop |
| 9 | Dark mode | Both themes from the same tokens; temple dusk is the natural dark theme | Contrast CI in both themes |
| 10 | Ornament budget | Kolam and thoranam only at thresholds: one on the landing page (the join), none in the app except the seal. **The seal is not a kolam**: it is the deal's own fingerprint drawn as a guilloché engraving (section 5.2) | A count in review: one ornament per screen at most |

### B. Design system

| # | Part | Our choice | Proven by |
|---|---|---|---|
| 11 | Tokens | One source in the W3C Design Tokens format, generated into CSS variables and Tailwind's theme for the web and a JS module for the apps; a raw colour, size or duration in a component fails lint | The lint rule; a token diff on every pull request |
| 12 | Primitives | Base UI under our components: headless and accessible, stable since late 2025, and shadcn/ui's default since July 2026 **(decision; dependency)** | Keyboard and screen-reader tests per component |
| 13 | Components | About forty, each with every state (default, hover, pressed, focused, disabled, loading, error). Section 7 lists them | Component tests and a screenshot per state |
| 14 | Catalogue | Every component and state on one browsable page, kept with the code **(decision: Storybook, or our own page; dependency)** | It builds in CI |
| 15 | Domain components | Built for this product, not borrowed: the deal pass, the memo, the record timeline, the seal, the payment status, the money input, the phone and code inputs, the stage stepper | Each against its backend contract and its psychology rule (always show what happens next, and when) |
| 16 | Patterns | Forms generated from the OpenAPI schemas; lists on the backend's cursor pagination; the five states on every screen (loading, empty, error, success, offline); every error code mapped to a sentence; `Idempotency-Key` on every write | Contract tests; a test per state |
| 17 | Words | Every string in a message catalogue (ICU), plain English, a check for the words CLAUDE.md constraint 1 forbids **(decision: the library; dependency)** | Pseudo-locale build and banned-words check in CI |

### C. Motion and animation

| # | Part | Our choice | Proven by |
|---|---|---|---|
| 18 | Principles | Motion explains cause and effect; one orchestrated moment per page; every movement ends in a clear still pose, as the Brihadeeswarar's karanas are "frozen moments" (`TAMIL_DESIGN_ROOTS.md` 12.7) | Review against the principles |
| 19 | Motion tokens | Durations and curves as tokens: 120 to 200 ms press, 180 to 260 ms state change, 400 to 800 ms section; springs for anything dragged (`frontend.md` 8c) | Lint bans raw durations |
| 20 | Component motion | Motion (already installed) for state changes and gestures; CSS for simple transitions | Frame time in a browser test |
| 21 | Page transitions | The View Transitions API where the browser has it (Chrome and Safari; Firefox partly), a clean cut elsewhere | Works with motion on and off |
| 22 | Scroll stories | CSS scroll-driven animations where supported (Chrome, Safari 26; Firefox still behind a flag), Motion's scroll hooks elsewhere. **No section pins the scroll for more than about two and a half screens** (the fold's lesson) | A scroll test that measures pinned length and long tasks |
| 23 | Pre-rendered sequences | **The big change.** Apple's smooth product scroll scenes draw pre-rendered frames on a canvas rather than running live 3D (third-party analyses of its AirPods page). We do the same for the temple turn and the fold: frames rendered in Blender (path-traced, so photoreal), compressed (AVIF or WebP), loaded progressively, drawn by scroll. Live WebGL only where a person interacts | Lighthouse and frame time on the budget Android; byte budget per sequence |
| 24 | Live 3D | three.js WebGPU renderer with its WebGL 2 fallback, only where interaction needs it (a seal you can turn, perhaps); never on working screens | The 3D budget in `frontend.md` 8b |
| 25 | Calm versions | Reduce motion shows stills; low-memory phones and Save-Data get the still sequence frame; nothing waits on motion to be read | Browser tests with motion on and off |

### D. Experience

| # | Part | Our choice | Proven by |
|---|---|---|---|
| 26 | Information architecture | The temple as the map (`TAMIL_DESIGN_ROOTS.md` 2): the landing page is the gateway, Discover the hall, the deal the inner courtyards, the sealed record the sanctum | A tree test with both roles |
| 27 | Navigation | Web app: a sidebar and a command menu (⌘K); phone: a bottom tab bar; glass only on these navigation layers (`UI_STYLES_2026.md`) | Task test |
| 28 | Journeys | Harish's screen plan, both roles, built against the real API | Playwright end-to-end on every pull request |
| 29 | Research with people | Five-second tests and task tests with Tamil brand owners and creators before each layer is final (rule 4). **None held yet** | Written results, in `docs/research/` |
| 30 | Onboarding and empty states | Every empty screen gives the next useful action; nothing is gated behind an install | Review of the five states |
| 31 | Trust | Facts over opinions, certainty about what happens next and when, honest labels, no dark patterns (`PSYCHOLOGY_AND_TRUST.md`, `legal.md` 3.5) | The dark-pattern checklist before release |
| 32 | Accessibility | WCAG 2.2 AA as the floor, 7:1 body text, 48 dp targets, full keyboard and screen-reader use | axe in CI, a manual TalkBack and VoiceOver pass |

### E. Engineering

| # | Part | Our choice | Proven by |
|---|---|---|---|
| 33 | Repository | pnpm workspace: `apps/web`, `apps/mobile`, and shared packages `api` (generated client), `tokens`, `ui`, `core` (rules and formatting), `messages` | Builds and type checks in CI |
| 34 | Rendering | Next.js App Router: public pages (landing, Passports, city pages, help) rendered on the server and readable without JavaScript; the signed-in app streamed from the server with client islands | The no-JavaScript test (`frontend.md` 8d) |
| 35 | Data | The generated client and TanStack Query; no hand-written API types **(decision: Hey API or Orval)** | The contract check |
| 36 | Sessions on the web | Tokens in `httpOnly` cookies or memory, never `localStorage` (`frontend.md` 10) **(security decision)** | A security test |
| 37 | Performance | Budgets from `frontend.md` 4: LCP ≤ 2.0 s, INP ≤ 150 ms, CLS ≤ 0.05, ≤ 150 KB of JavaScript per route (50 KB on public pages), Lighthouse 95/100/100/100 | Lighthouse CI and a bundle check, failing the build |
| 38 | Tests | Unit, component, end-to-end, visual regression at two widths and two themes, accessibility, pseudo-locale | All in CI (`frontend.md` 12) |
| 39 | Being found | Server-rendered metadata, share images, structured data; AI search can read every public page | The no-JavaScript test |
| 40 | Watching it live | Real-user Core Web Vitals and Sentry, with personal data scrubbed | Reviewed each release |
| 41 | The apps | Expo, sharing `core`, `api`, `tokens` and `messages` with the web **(decision by 15 November, both founders)** | A test build on Harish's phone |

---

## 4. The colour decision, made by evidence

**What research says (sources at the end):**
- Colour is a real but **small** trust cue next to content and clarity. In the most-cited study (over 200 people rating finance and medical sites) blue rated most trustworthy and black least, but colour's effect was limited.
- Hue findings disagree with each other. A 2025 review calls "blue is most trusted" methodologically unreliable; one trust experiment found no effect of blue against red.
- **Saturation is the steadiest finding:** highly saturated colour reads as aggressive and promotional and lowers trust; moderate, calm saturation is trusted more, while greying everything out also lowers it.
- In India: a small study of 120 young adults found blue the most preferred colour, red read as vibrant and auspicious, green as faith and nurturing. Saffron and orange are refused for Colyv on other grounds (rule 6, D-143).

**So the brand colour matters less than restraint, consistency and meaning.** Whichever accent wins, the system around it is the same: a calm warm-neutral base, one accent used sparingly, state colours that always mean the same thing, gold only on sealed things.

**The decision, as a test rather than a debate:**

```
DECISION NEEDED: Colyv's one accent colour, for the website and both apps
Context:      the prototype is burgundy and gold, Harish's app is deep green; both cannot ship
Option A:     deep burgundy (kumkum and kemp, TAMIL_DESIGN_ROOTS 7, 12.14) | + rooted, distinct among Indian SaaS | − red can read as error; must be kept off error states | effort S
Option B:     deep green (Harish, 28 October) | + calm, reads as "done" and money | − green is also our "success" colour, so state and brand blur | effort S
Option C:     run both on three real screens (landing opening, deal memo, payment) as a five-second test with 5 brand owners and 5 creators in Tamil Nadu | + evidence, not taste; Harish takes part | − about a week | effort M
Recommended:  C, deciding between A and B by the result, because the research says taste predicts little and our users are the judges
Risk & rollback: a token change; nothing is built in colour until this is decided, so nothing is undone
→ Approve A, B, C, or modify?
```

---

## 5. The signature pieces, kept and rebuilt

### 5.1 The temple
- **Keep:** the Thanjavur vimana, made in Blender (D-142), the dusk light, the granite.
- **Change:** the live three.js gopuram and every 2D line-art temple go. The opening shows the Blender vimana as a **pre-rendered scroll turn** (part 23): photoreal because it is path-traced, smooth because it is frames, light on a budget phone because the first frame is a single image and the rest stream in.
- **Owed before it ships:** the open render faults (granite reading as plaster, the hidden lamp, the missing life), and a primary source for the proportions (`FRONTEND_RESEARCH_2026.md` Part E).

### 5.2 The seal
- **New (30 October):** the deal's seal is its own fingerprint drawn as a guilloché engraving, the security pattern on banknotes, generated from the record's hash, so no two deals share one. It draws from both halves at once and closes where they meet. Raised gold, sealed things only.
- It replaces the kolam as the product's signature, which also answers the kolam overload.

### 5.3 The fold
- **Keep the idea:** the fold is the deal. Brand on one half, creator on the other, the seal drawn across the crease, the phone closing on the record.
- **Rebuild it properly:** **three chapters, not six** (the invite arrives and the phone opens; agreed and sealed across the crease; paid, confirmed, closed on the record), pinned for about two and a half screens, and **drawn from pre-rendered frames** (part 23) instead of live 3D with large canvas textures. The phone's proportions stay those of the iPhone Duo's published dimensions, with no maker's logo.

---

## 6. The landing page: shorter, one story

From 17 sections to **8**, in the temple's order from the street inwards (`FRONTEND_RESEARCH_2026.md` C4):

1. **The opening:** one headline, one action, the temple turning in dusk light, a real product glimpse.
2. **The two fears:** the creator's (paid late) and the brand's (paid for fake reach), with sourced facts.
3. **The fold:** one deal, both sides, three chapters.
4. **How a deal works:** one interactive stepper with real product screens (replacing six blocks of old phone pictures).
5. **The record and the seal:** tamper-evident, checkable, and what Colyv never does (holds no money).
6. **Both sides:** for brands, for creators, and the Passport.
7. **How we compare:** honest, sourced.
8. **Questions and joining the pilot:** the one thoranam, at this threshold.

Detailed, but each section earns its place. Target: about a third of today's length.

---

## 7. The component list (first pass)

**Foundations:** Button, Icon button, Link, Text and headings, Icon, Divider, Surface (solid and glass), Grain.
**Inputs:** Text, Text area, Select, Combobox, Phone (+91), One-time code, Money (₹, Indian grouping), Date, Checkbox, Radio, Switch, Segmented control, File upload with progress.
**Overlays:** Dialog, Sheet, Popover, Tooltip, Menu, Command menu, Toast.
**Display:** Card, Bento tile, Badge and pill, Avatar, Table, List, Stat, Empty state, Skeleton, Banner, Progress, Tabs.
**Domain:** Deal pass, Stage stepper, Memo view, Record timeline, Seal, Payment status, Proof card, Passport card.

Each: every state, both themes, 360 px and desktop, keyboard and screen reader, a screenshot test.

---

## 8. The order of work

| Step | What | Done when |
|---|---|---|
| 1 | **Decisions** (section 9) | Each has a yes or a choice, recorded in `docs/DECISIONS.md` |
| 2 | **The colour test** (if C) | Results written; one accent chosen |
| 3 | **Foundations:** tokens (colour, type, space, radius, elevation, motion), fonts, icons, the CI gates (Lighthouse, axe, visual regression, bundle size, banned words) | Gates run red on a deliberate breach and green on the foundations |
| 4 | **Components** (section 7) in the catalogue | Every state screenshot-tested, keyboard and screen-reader checked |
| 5 | **Signature pieces:** temple sequence, seal, fold sequence | Within the byte and frame budgets on the budget Android; founder judged against references |
| 6 | **The landing page** (section 6) on the system | Lighthouse 95/100/100/100, LCP ≤ 2.0 s on slow 4G, readable without JavaScript, judged better than the prototype and the references |
| 7 | **The app screens** (Harish's plan) | Per `execution-plan.md` |

**Honest about time:** launch is planned for 1 January 2027 and the build deadline of 10 December is not confirmed. Steps 1 to 4 done properly take about three weeks of focused work alongside the backend. The landing page comes after the system, not before. If the dates cannot hold, the scope of screens shrinks, never the bar.

---

## 9. Decisions needed now

| # | Decision | Recommendation |
|---|---|---|
| 1 | Approve this architecture as the plan | Yes |
| 2 | Style: granite and light | Yes |
| 3 | Colour: A, B or the test C (section 4) | C |
| 4 | Primitives: Base UI | Yes (dependency) |
| 5 | Component catalogue: Storybook, or a page of our own | Our own page first; Storybook only if it earns its weight (dependency) |
| 6 | Message catalogue library | next-intl, as the Next.js standard (dependency; to be checked against its current release) |
| 7 | API client generator: Hey API or Orval | To be benchmarked on our 200+ operations before choosing |
| 8 | Signature scenes as pre-rendered frames, live 3D only for interaction | Yes |
| 9 | Landing page: 8 sections, 2D temples and kolam overload removed | Yes |
| 10 | The apps: Expo or Flutter | By 15 November, both founders (`execution-plan.md`) |
| 11 | Who judges "better than the reference" | Adhi and Harish together, with the colour test's people where possible |

Each dependency gets its own request in the CLAUDE.md format before it is added.

---

## 10. The twelve dimensions, for this proposal

- **Quality:** every part has a measure in CI or a named review; nothing is "done" on taste alone.
- **Novelty:** the seal from the deal's fingerprint and the fold as the deal are, as far as research found, used by no competitor (`COMPETITIVE_LANDSCAPE.md`).
- **Architecture:** frontend only; the backend contract is the boundary; `ARCHITECTURE_SCALE.md` unchanged.
- **Research:** the documents listed at the top, plus the sources below; people research is the gap.
- **Security:** sessions, CSP and the client rules in `frontend.md` 10; part 36 is a security decision.
- **Privacy and law:** no personal data in analytics or logs; the dark-pattern checklist (`legal.md` 3.5); sample data labelled.
- **Trust and safety:** honest labels, flags shown beside text, block and report one tap away (`trust-and-safety.md` 5).
- **Performance:** the budgets in part 37, measured on the budget Android on slow 4G.
- **Design:** sections 2 to 7.
- **Business:** brands and creators judge Colyv in seconds on the landing page; a calm, fast, honest page earns the first deal. Cost: time, and a designer brief within ₹5,000 for the mark.
- **Reliability:** every screen's five states; retries with `Idempotency-Key`; the 503 and 429 rules (`frontend.md` 5).
- **Maintainability:** one token source, one component system, one generated client, so a change happens in one place.

---

## Sources

- Kosova (2025), "Coloring Trust: Insights and Research Perspectives", *New Psychological Research*, doi 10.51217/npsyresearch_2025_05_01_04: https://journals.rcsi.science/2782-2184/article/view/298120
- Alberts and van der Geest (2011), "Color Matters: Color as Trustworthiness Cue in Web Sites", *Technical Communication* 58(2): https://research.utwente.nl/en/publications/color-matters-color-as-trustworthiness-cue-in-web-sites
- The negative impact of saturation on website trustworthiness and appeal (2016), *Computers in Human Behavior*: https://www.sciencedirect.com/science/article/abs/pii/S0747563216302254
- Colour appeal in website design within and across cultures (2009), *International Journal of Human-Computer Studies*: https://sciencedirect.com/science/article/abs/pii/S1071581909001116
- What is hidden in colours? Perception of colours by youth in India (small sample): https://www.academia.edu/44774261/What_is_Hidden_in_Colours_An_Empirical_Study_on_the_Perception_of_Colours_by_Youth_in_India
- Apple-style scroll sequences, third-party analyses: CSS-Tricks https://css-tricks.com/?p=308477 ; Setproduct https://www.setproduct.com/blog/how-to-3d-animate-scroll
- three.js WebGPU: Utsubo migration guide (2026) https://www.utsubo.com/blog/webgpu-threejs-migration-guide ; buildmvpfast (2026) https://www.buildmvpfast.com/blog/threejs-webgl-to-webgpu-renderer-migration-2026
- Base UI and shadcn/ui: OpenReplay https://blog.openreplay.com/shadcn-ui-radix-base-ui-switch/ ; shadcn release notes https://releasebot.io/updates/shadcn/shadcn
- View Transitions: Chrome developer docs https://developer.chrome.com/docs/web-platform/view-transitions ; 2026 guide https://devtoolbox.dedyn.io/blog/css-view-transitions-complete-guide
- Scroll-driven animations: buildmvpfast (2026) https://www.buildmvpfast.com/blog/css-scroll-driven-animations-replace-js-2026 ; Mozilla Connect https://connect.mozilla.org/t5/ideas/implement-css-scroll-driven-animations-animation-timeline/idc-p/116613

**Checked against secondary sources only, to confirm against primary ones before building:** the browser support figures, the three.js production status, Base UI's version, and Apple's use of image sequences.
