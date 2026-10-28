# Frontend research and the homepage prototype audit

**Version 1, 28 October 2026.** Desk research and a measured audit, made at Adhi's request ("research on all 14 and more; the latest tech available today; proper audit of how to make it better"). Nothing here is a decision. Every choice that needs a founder is marked **(decision)** and gathered in Part D.

**How it was made.**
- **The audit:** `frontend/prototypes/homepage.html` was served locally and measured with Lighthouse 12.8.2 (mobile and desktop presets), with a Playwright script that counts WebGL draw calls and triangles per frame, and with screenshots at 1440 px and 390 px.
- **The research:** 54 web searches on 28 October 2026. Each finding below names its source and how strong it is.
  - Many 2026 pages are vendor blogs. Where only a vendor says something, this file says so.
  - Where sources disagree, both are given.
  - Version numbers and dates from secondary sources are to be checked against the official release notes before a stack choice is locked (D-047's upgrade rule).

**What it does not contain:** any conversation with a real brand or creator. Every point about people here is desk research (`docs/research/README.md`).

---

## Part A. The homepage prototype, audited

### A1. Measured

| What | Mobile (Lighthouse preset: slow 4G, 4× CPU) | Desktop |
|---|---|---|
| Performance score | **30** | 56 |
| Accessibility score (automated) | 100 | 100 |
| Best practices | 75 | 74 |
| SEO | 91 | 91 |
| First Contentful Paint | 6.3 s | 1.7 s |
| Largest Contentful Paint | **8.2 s** (budget: 2.0 s) | 1.7 s |
| Total Blocking Time | **5,620 ms** | 1,160 ms |
| Time to interactive | **14.4 s** | 3.0 s |
| Main-thread work | 10.3 s, of which the page's own script 6.8 s | 2.4 s |
| Layout shift | 0.001 | 0.004 |
| Page weight | 1,291 KB | same |
| Inline JavaScript unused at load | 179 KB of 212 KB (85%) | same |
| Elements on the page | 2,335 | same |
| Page length | **32,605 px on a 390 px phone (about 39 screens)**; 21,085 px at 1440 px | |
| 3D, busiest frame (desktop, Intel Iris Xe) | up to **534 draw calls** and **267,586 triangles**; the scene redraws on about 40% of frames | |

**What these numbers cannot say.**
- The local server sent no compression and no charset. The Chrome profile also carried an extension that injected its own requests. So "insecure requests", "text compression", "charset" and part of the byte weight are artefacts of the test, not faults of the page.
- The mobile figures are a lab profile on a laptop. They are not a measurement on a budget Android phone, which `docs/standards/frontend.md` section 3 requires and we do not yet own.
- The frame-rate figures come from a laptop GPU. They say nothing about a phone.

### A2. What is strong, and must be kept

- **The idea.** A temple courtyard at golden hour, entered by scrolling, is a world no competitor has. Adhi's own direction (memory: frontend-ambition-3d).
- **The words.** Honest, specific, sourced:
  - "Colyv never holds or moves your money."
  - The 60 to 90 day payment cycle, with its source and a note that we have not verified it.
  - "Sample data" on every invented figure.
  - "A memo is a record of what was accepted, not a contract."
- **Working product previews.** The six-step walk, the payment screen, the trust record, the dispute timeline and the Passport card show the product working, not described.
- **The Brand and Creator switch** in the header, kept across the page.
- **Care already taken:**
  - 142 ARIA attributes;
  - `inert` on the hidden Passport face;
  - reduced-motion handling;
  - a WebGL context-loss handler;
  - a low-power check that keeps the 3D off on weak devices or in data-saver mode.
- **Layout shift is near zero.**
- **The pilot-list section is the standard for neatness** (Adhi, 28 October 2026):
  - the thoranam along the card's top and bottom edges;
  - the doll in an arched niche;
  - a two-column form with visible labels;
  - consent wording that admits it is not final ("Final consent wording follows legal review");
  - "Demo form: nothing is sent or saved."
  - Every section should reach this level of order and calm.

### A3. What is weak, worst first

1. **The page cannot be used on a phone for 14 seconds.**
   - The scene is built in JavaScript on the main thread at load: 6.8 s of scripting on the mobile profile and 5.6 s of blocking time.
   - A tap in that window does nothing. This alone fails the INP budget (150 ms).
2. **The largest paint is 8.2 s on mobile.** The largest element is a CSS banana-leaf layer, not the headline. The text waits behind the scene.
3. **The temple is made of primitive shapes with painted textures.**
   - The scene's code calls 24 shape constructors: boxes, cylinders, cones, spheres, one lathe and one extrusion.
   - Detail comes from canvas-drawn textures, not geometry.
   - There is no image-based lighting, no post-processing (glow, ambient occlusion, depth of field) and no physically based stone.
   - The banana plants are flat CSS layers in front of the canvas, not 3D.
   - Three.js is r128, from 2021.
   - This is why it reads as a game and not as a place.
4. **534 draw calls in a frame is high for a scene this simple.** Each shape is drawn separately, shadow pass included. Batching or merging would cut it.
5. **3D appears once.** After the opening screen every section is flat cards. D-141 asks for signature moments: a deal agreed, a deal sealed, the Passport.
6. **Too long.** 17 sections, about 39 phone screens. The strongest SaaS pages tell one story in far fewer (Part B5).
7. **Everything is the same card.** One radius, one shadow, one cream fill. The hierarchy flattens, and equal-height cards leave large empty bottoms (the trust-record row is the clearest case).
8. **Kolam ornaments are cut off** at section edges and run under the header. They look accidental, not placed.
9. **The phone header takes two rows, about 125 px, all the time**, and the floating "3D" button sits over content.
10. **Not ready to be found:**
    - no meta description and no structured data;
    - one 382 KB HTML file with all of its script inline;
    - Google Fonts loaded from Google, not self-hosted and subset (section 4 of the standard);
    - the body text in the system font.
11. **The mark reads "கோlyv.ai".** The `.ai` and the domain are undecided (memory: colyv-rename-and-english-only), and the mixed-script mark has not been tested for legibility at small sizes. **(decision)**
12. **Small faults that undercut the polish:**
    - A stray blue dot sits at the right edge beside the pilot-list card at 1440 px: the same kind of fault noted on Interview Coach AI.
    - "Posted or applied in under five minutes" is a claim nobody has measured.
    - The doll in the niche is an embedded photograph (a WebP inside the HTML), which rule 5 below now excludes.
13. **Two colour directions exist.** Harish set a deep-green direction for the apps on 28 October (`frontend/design/screen-plan.md`). This page is burgundy and gold. Both cannot ship. **(decision, both founders)**

**Verdict.** The idea and the words are the best assets Colyv has on the frontend. The ceiling is the engineering: how the 3D is made, when it loads, and how long the page is. Part C is the plan to lift exactly those, keeping everything in A2.

---

## Part B. Research, area by area

Each area gives what is current (dated), what the best do, what it means for Colyv, and what stays open.

### B1. Brand and visual identity

- **Colour and trust: there is no strong 2024 to 2026 evidence base.**
  - No peer-reviewed study of colour and trust in fintech interfaces was found.
  - Blue is the most cited trust colour, with green second in financial contexts. That rests on a table whose study is not named ([windmill.digital](https://windmill.digital/psychology-of-color-in-financial-app-design/)).
  - A 2017 study (Asian Institute of Finance with the Imagineering Institute) found hue and symmetry affect trust in online banking and insurance ([Asia Insurance Review](https://www.asiainsurancereview.com/Magazine/ReadMagazineArticle?aid=39963)).
  - No research was found on gold and trust.
  - **Meaning for Colyv:** gold on the sealed record rests on Thanjavur craft tradition (`TAMIL_DESIGN_ROOTS.md`), not on psychology, and should be described that way. Green and red for "done" and "problem" follow conventions too strong to break.
  - **Owed:** a proper literature search (Google Scholar, ACM CHI) and Adhi's book chapter on colour psychology (title not yet given).
- **Colour space.**
  - Linear moved its theme generation from HSL to LCH, for colours that look equally bright across hues ([Linear, via plushcap, 2024](https://www.plushcap.com/companies/linear/blog/summaries/2024/03)).
  - Tailwind 4 defines its palette in OKLCH.
  - **For Colyv:** define every colour token in OKLCH, so light and dark themes keep equal contrast.
- **Tamil type.**
  - Noto Sans Tamil is the most recommended body face: variable, open licence, with a UI variant for interfaces ([Figma fonts](https://www.figma.com/fonts/noto-sans-tamil-ui/)).
  - Anek Tamil is also variable and OFL ([jsDelivr](https://www.jsdelivr.com/package/npm/@fontsource-variable/anek-tamil)).
  - Mukta Malar is suggested for bilingual layouts, and Catamaran for headings only.
  - No measured readability test was found. The candidates must be tested at real sizes before one is chosen. **(decision)**

### B2. Design system

- **Tokens:** the W3C Design Tokens format, first stable version 2025.10, is already the standard's rule (section 8).
- **Component foundations:**
  - Radix is still supported but has slowed, and was acquired by WorkOS.
  - Base UI reached a stable 1.0 in late 2025.
  - React Aria gives the deepest accessibility, at the cost of more code per component.
  - shadcn/ui is a styled layer over Radix or Base UI ([GreatFrontEnd, 2026](https://www.greatfrontend.com/blog/top-headless-ui-libraries-for-react-in-2026); [Untitled UI](https://www.untitledui.com/blog/base-ui-vs-react-aria)).
  - **For Colyv:** keep shadcn/ui (locked in section 2), but on **Base UI**, not Radix. **(decision)**
- **Tailwind:** 4.2 (February 2026) and 4.3 (May 2026) added logical-property utilities, `font-features-*`, containers and scrollbars ([InfoQ, April 2026](https://infoq.com/news/2026/04/tailwind-css-4-2-webpack); [releases.sh](https://releases.sh/tailwind-css/tailwind-css/highlights)).
- **Figma (Config 2026, 24 June):**
  - Code Layers: real React code inside a design.
  - Figma Motion: a timeline that exports to CSS, JSON and React, readable by coding agents over MCP.
  - AI-generated shaders, and an agent in open beta on paid plans ([CMSWire](https://www.cmswire.com/digital-experience/figma-launches-code-layers-motion-at-config-2026/); [Noqta](https://noqta.tn/en/news/figma-config-2026-code-layers-motion-ai-2026)).
  - **For Colyv:** with the Professional plan Adhi chose, the design system lives in Figma and in code at once, and motion is specified once and exported, not re-described.

### B3. Users and UX

- **The problem is real and public.**
  - Indian trade press puts typical creator payment delays at **60 to 90 days, often past 120**, and estimates losses near ₹450 crore a year. That is an industry estimate, not audited ([Agency Reporter](https://agencyreporter.com/?p=84289); [MediaNews4U, 13 August 2026](https://www.medianews4u.com/payment-delays-are-not-the-problem-theyre-a-symptom-of-whats-broken-in-indias-creator-economy/)).
  - Kofluence's *Decoding Influence 2026* values the sector at ₹3,000 to 3,500 crore in 2025. That is a vendor report.
  - A talent agency now promises 48-hour creator payouts ([exchange4media](https://www.exchange4media.com/influence-zone-news/indias-creator-economy-moves-towards-self-serve-tech-48-hour-payouts-157971.html)).
- **For Colyv:** payment status, already the homepage's strongest section, is the hero problem. A competitor promising 48-hour payouts holds money to do it. Colyv never does (constraint 1), so our promise is visibility and proof, said plainly.
- **Owed before any flow is final:** the five conversations per side that `docs/standards/ux.md` section 2 requires. None have happened.

### B4. Motion and animation

- **GSAP is now free for everyone, all plugins included** (ScrollTrigger, SplitText, Flip, MorphSVG and the rest), for commercial use too. SplitText was rewritten 50% smaller, with screen-reader support built in ([Webflow](https://webflow.com/blog/gsap-becomes-free)).
- **Motion for React** (formerly Framer Motion) is on the 12.x line, last updated March 2026, for layout and shared-layout animation in React ([Socket](https://socket.dev/npm/package/framer-motion/overview/12.35.2); [motion.dev](https://llms.motion.dev)).
- **CSS scroll-driven animations** are an Interop 2026 focus area. They run in CSS with no main-thread script, Chrome since 115 and Safari 26; Firefox's status is unclear ([WebKit](https://webkit.org/blog/17818/announcing-interop-2026/); [Mozilla](https://hacks.mozilla.org/2026/02/launching-interop-2026/); [Chrome](https://developer.chrome.com/docs/css-ui/scroll-driven-animations)).
- **Cross-document View Transitions** (animated moves between pages without a framework): Chrome 126, Safari 18.2, not yet Firefox; also an Interop 2026 area ([Chrome](https://developer.chrome.com/docs/web-platform/view-transitions/cross-document)). React 19.2 in Next.js 16 adds View Transitions inside the app.
- **Rive or Lottie:**
  - Rive has state machines and data binding (an animation that reacts to app state), with a larger runtime.
  - Lottie is a simpler, lighter player.
  - Wikimedia's 2026 evaluation warns that text and controls must stay native, never only inside the animation ([Rive](https://rive.app/blog/rive-as-a-lottie-alternative); [Wikimedia T433250](https://phabricator.wikimedia.org/T433250)).
- **For Colyv:**
  - Scroll effects in CSS where the browser can do them, GSAP for the orchestrated scenes, and Motion for in-app state changes.
  - Rive for the thalaiyatti bommai and onboarding characters, if a designer builds them.
  - Timing tokens as already set in the standard (section 8c).

### B5. 3D

- **Three.js.**
  - The current release is **r186** (8 September 2026) ([Utsubo](https://www.utsubo.com/blog/threejs-2026-what-changed)). The prototype is on r128, five years older.
  - The WebGPU renderer falls back to WebGL 2 automatically, and its node-based shading (TSL) replaces hand-written shaders.
  - The three.js manual still recommends the WebGL renderer for pure WebGL apps, and custom `ShaderMaterial` and `onBeforeCompile` do not carry over to WebGPU ([three.js manual](https://threejs.org/manual/en/webgpurenderer.html)).
- **WebGPU is in every major browser:**
  - Chrome and Edge 113 and later;
  - Android Chrome 121 on Android 12 and later, with a compatibility mode for older GLES 3.1 phones from February 2026;
  - Safari on iOS and macOS 26;
  - Firefox from 141 on Windows, still partial elsewhere ([web.dev](https://web.dev/blog/webgpu-supported-major-browsers); [Khronos, SIGGRAPH 2026](https://www.khronos.org/developers/linkto/webgl-and-webgpu-sigg26)).
  - No usage-share figure was found. India's budget Androids on older OS versions will often get WebGL 2.
- **React Three Fiber.**
  - v10 makes WebGPU the default, but is still **alpha**; Drei v11 is alpha too ([newreleases.io](https://newreleases.io/project/npm/@react-three/fiber/release/10.0.0-alpha.6)).
  - The standard names R3F on the WebGPU renderer (section 8b). Today that means R3F v9 stable with WebGPU opt-in, or plain three.js. **(decision)**
- **Gaussian splats (photoreal captured scenes).**
  - Spark 2.0 (14 April 2026, World Labs, MIT licence) streams splats with level of detail, runs on WebGL 2 on about 98% of devices, and mixes splats with ordinary meshes in one three.js scene ([Spark](https://sparkjs.dev/docs/overview/); [GitHub](https://github.com/sparkjsdev/spark)).
  - No public scan of the Brihadeeswarar was found, and no licence to use one.
- **Asset compression.**
  - Meshopt for geometry, plus gzip or Brotli, and KTX2 textures where GPU memory or phone stutter matters, built with gltf-transform ([gltf-transform](https://gltf-transform.dev/modules/extensions/classes/EXTMeshoptCompression)).
  - Claims of "50 to 80% smaller" are not supported; one measured Draco example saved 35%.
- **Modelling.** Blender 5.0 (November 2025) added geometry-node volume grids, SDF nodes and new node-based modifiers, useful for procedural architecture ([CG Channel](https://www.cgchannel.com/2025/11/blender-5-0-is-out-check-out-its-5-key-features)).
- **The temple, as architecture.**
  - A Dravidian vimana rises as adhishthana (base), pada or bhitti (wall), prastara (cornice), griva (neck), shikhara (crown) and stupi or kalasa (finial).
  - At Thanjavur the crown is a single granite block of about 80 tonnes.
  - The height is given as 63.4 m from the inner courtyard floor, and popularly as 66 m.
  - "Thirteen storeys" comes from one student source only and is unverified ([Studio Matrx, July 2026](https://www.studiomatrx.org/architecture-canon/brihadeeswarar-temple-thanjavur); [Wikipedia](https://www.wikipedia.com/wiki/Brihadeeswarar); [Anantam IAS](https://anantamias.com/brihadeeswara-temple-thanjavur/)).
  - **Owed:** a primary architectural source (an ASI publication or a measured drawing) before the model's proportions are fixed.
- **AI image-to-3D, for first drafts of objects.**
  - In 2026 Tripo is most praised for clean, editable topology; Rodin (Gen-2.5) for surface detail and PBR materials; Meshy for balance.
  - Hunyuan3D (up to eight input views in 3.1) and TRELLIS.2 (MIT licence, PBR up to 4K, but holes and artefacts) are the open options.
  - No source is independent and the comparisons conflict, so each must be tested on our own object ([Arcframe](https://arcframe.ai/blog/best-image-to-3d-ai-models-compared); [Inker](https://inker.si/blog/best-ai-3d-model-generators-2026); [Vitalify, July 2026](https://www.vitalify.asia/en/blog/ai-image-to-3d-generators-comparison)).
  - **For Colyv:** a first draft of the doll from photos **we take of a doll we buy**, then finished by hand in Blender: retopology, the mould seam, the hand-painted surface. Never from someone else's photo, whose rights we do not hold.
- **Procedural temples.** No published shape grammar for Dravidian vimanas was found.
  - The nearest are a parametric (Grasshopper) study of Karnata-Dravida temples ([Architexturez](https://architexturez.net/doc/isbn/978-0-9955691-0-2pp-409-420)) and a Vitruvian grammar for Roman temples ([Noghani and others, VAST 2012](https://diglib.eg.org/handle/10.2312/PE.VAST.VAST12S.041-044)).
  - So the vimana generator is new work, written from the anatomy above, and its rules are worth documenting as our own.
- **Who wins awards with this.** One analysis says immersive 3D was 61% of Awwwards Sites of the Day in the first quarter of 2026, against 23% in 2024 ([Digital Strategy Force](https://digitalstrategyforce.com/journal/why-are-immersive-experiences-dominating-the-2026-awwwards/)). That is a single unofficial count.
- **For Colyv:** the method that removes the "game" look is in Part C1. It conflicts with one line of the standard: section 8b says realism comes from capture, not modelling. Adhi now asks for a made temple, not a photograph. **(decision: amend 8b to allow a procedural model with baked physically based materials, beside captured objects)**

### B6. Screens

The full screen list (public, brand, creator, shared, admin) was given in chat on 28 October and matches the API in `docs/api/openapi.json`. It is to be held in `frontend/design/screen-plan.md` with each screen's API calls, as the standard requires (no screen needs more than two calls).

### B7. Platforms and frameworks

- **Next.js 16** (21 October 2025; 16.1 and 16.2 since):
  - Cache Components with `"use cache"` replace the older partial pre-rendering;
  - Turbopack is the default bundler;
  - `proxy.ts` replaces middleware;
  - React 19.2 brings `<Activity>`, `useEffectEvent` and View Transitions;
  - the React Compiler 1.0 is supported but off by default ([Next.js](https://nextjs.org/blog/next-16)).
  - The current 16.x patch is to be checked at stack lock.
- **Images.**
  - AVIF works in all major browsers.
  - Chrome 155 (October 2026) now decodes JPEG XL, and Google recommends trying both for photographs ([Chrome](https://developer.chrome.com/blog/jpeg-xl-in-chrome); [Wikipedia](https://en.wikipedia.org/wiki/JPEG_XL)).
  - Serve AVIF with a fallback, and JPEG XL as an extra source where it is smaller.
- **Apps.**
  - The standard locks Expo (section 2, D-047). Harish's starter app in pull request #78 is Flutter. D-141 left the choice open.
  - The sources agree: Expo for a TypeScript team, shared code with the website, and over-the-air updates; Flutter for heavily custom animated UI on one engine ([Groovy Web, 2026](https://www.groovyweb.co/blog/react-native-vs-flutter-vs-expo-lynx-2026); [Shipnative](https://www.shipnative.dev/blog/expo-vs-flutter-2026)).
  - The version numbers in those sources conflict and are to be checked. **(decision, both founders)**

### B8. Accessibility

- **The floor is WCAG 2.2 AA.** The standard already goes further (7:1 body contrast, 200% text).
- **India's law is tightening:**
  - The RPwD Act 2016, section 46, places an accessibility duty on private establishments, "in accordance with the rules".
  - In *Rajive Raturi v. Union of India* (November 2024) the Supreme Court held that accessibility standards must be mandatory, and directed binding rules.
  - Draft ICT accessibility rules were reported in July 2026, with 12 to 18 months to comply. **Not confirmed from an official source.**
  - The technical yardsticks are GIGW 3.0 for government sites (WCAG 2.1 AA) and IS 17802 ([BarrierBreak, 2026](https://www.barrierbreak.com/digital-accessibility-laws-by-country/); [Deque on SEBI](https://www.deque.com/blog/sebi-sets-a-new-standard-for-digital-accessibility-in-finance-in-india/); [HalfAccessible](https://halfaccessible.com/india-digital-accessibility-compliance/)).
- **For Colyv:** what the law requires of us is a validation-pack question (constraint 6). Building to WCAG 2.2 AA and above already exceeds every named yardstick.

### B9. Performance

- **Core Web Vitals are unchanged:** LCP 2.5 s, INP 200 ms and CLS 0.1, judged at the 75th percentile of real users. Field data decides; lab scores are for finding problems. The Long Animation Frames API shows which script makes an interaction slow ([Core Web Vitals guides, 2026](https://eseospace.com/blog/core-web-vitals-in-2026-what-changed-what-still-matters-and-how-to-pass/)). Our budgets (2.0 s, 150 ms, 0.05) stay tighter.
- **Indian phones are getting dearer, not cheaper.**
  - The average selling price hit a record **$315 to 318** in the second quarter of 2026.
  - Phones under $100 fell to **4.5%** of shipments (from 15.6%).
  - The $100 to 200 band is **46.8%** of the market ([IDC](https://www.idc.com/resource-center/blog/india-smartphone-market-q1-2026/); [Counterpoint](https://counterpointresearch.com/en/insights/india-smartphone-price-hikes-average-16-percent-in-h1-2026)).
  - **For Colyv:** the reference "budget Android" should be a current ₹9,000 to ₹17,000 phone, the $100 to 200 band, not an ultra-low-end one.
- **Network:** no 2026 Ookla median for India was found. The latest found is from 2022 to 2024. The standard's slow-4G lab profile stays until we measure our own users.

### B10. Being found: search and AI answers

- Google says AI Mode and AI Overviews are search. There is no separate AI index, and a page must first be crawlable and indexable to be cited. Pages that answer specific questions directly suit how AI Mode splits a question into many searches ([Trusted Shops summary of Google's guidance](https://ai-trust-audit.trustedshops.com/en/blog/ai-overviews-and-ai-mode-google-s-requirements-for-websites-2026)).
- No evidence was found that `llms.txt` changes visibility.
- **For Colyv:**
  - every public page rendered on the server, with its own title, description and share image (standard section 8d);
  - structured data for the organisation, the FAQ and the public Passport;
  - the FAQ written as direct answers.

### B11. Engineering quality

- **Storybook 10.3** runs component tests in Vitest browser mode on Playwright by default, with accessibility checks. Chromatic adds visual snapshots to the same tests ([Storybook](https://storybook.js.org/docs/writing-tests/integrations/vitest-addon); [Chromatic](https://www.chromatic.com/blog/introducing-chromatic-for-vitest-browser-mode/)).
- **For Colyv:** the component catalogue and the visual regression gate the standard requires (sections 8 and 11) come from that one setup.

### B12. Security and privacy in the client

- **Passkeys:**
  - Conditional UI offers a saved passkey in the browser's autofill. It needs discoverable credentials and a feature check first.
  - One vendor reports 20% passkey take-up from silent upgrades alone, 40% with prompts, and 60 to 80% with full practice ([Corbado](https://www.corbado.com/blog/conditional-create-passkeys)). Those are vendor figures, and none are for India.
  - The backend already supports passkeys (D-113).
- **DPDP Rules 2025:** notified 13 November 2025.
  - Consent-manager registration starts **13 November 2026**.
  - Notice, consent, security and children's-data rules start **13 May 2027** ([Wikipedia](https://en.wikipedia.org/wiki/Digital_Personal_Data_Protection_Rules,_2025); [MirvoLegal, September 2026](https://www.mirvolegal.com/insights/dpdp-rules-2025-compliance-timeline/)).
  - These are secondary sources, and the exact duties are a validation-pack question (constraint 6).

### B13. Measuring and improving

- Real-user measurement (the web-vitals library with Long Animation Frames) is the truth for speed (B9).
- **Not researched yet:** which analytics tool, and whether self-hosted. **(gap)**

### B14. Content and law on screen

- **Already set in the standards:**
  - the 13 dark patterns the Consumer Protection Authority bans (`legal.md` section 3.5);
  - ASCI disclosure;
  - the grievance officer;
  - English only (D-054).
- **The DPDP dates in B12 set when the consent and notice screens must be live:** May 2027 at the latest, if the timeline holds.

### B15. More: AI inside the product ("Ask Colyv")

- The production pattern in 2026 is a curated set of components that the assistant picks and fills, not model-written interface.
- Vercel paused its React Server Components path for AI interfaces.
- One reported case cut drop-off from 60% to 12% by replacing a chat step with an inline form ([Alex Cloudstar, 2026](https://www.alexcloudstar.com/blog/generative-ui-developer-guide-2026/); [AI SDK RSC docs](https://v5.ai-sdk.dev/docs/ai-sdk-rsc)).
- **For Colyv:** "Ask Colyv" answers with the product's own cards (a memo, a payment status, a rate range), never free-form interface.

### B16. More: glass and material

- Apple's Liquid Glass can be approximated on the web with `backdrop-filter`, but true refraction needs SVG displacement filters that work in Chromium only, and stacked blur layers cost frame time ([buildmvpfast, 2026](https://www.buildmvpfast.com/blog/liquid-glass-css-backdrop-filter-recipes-2026); [Ekino](https://medium.com/ekino-france/liquid-glass-in-css-and-svg-839985fcb88d)).
- The prototype has 34 `backdrop-filter` rules over a moving 3D canvas. That is a likely cost on phones, still to be measured on one.

---

## Part C. How to make it far better, in order

Each item keeps what Part A2 says is strong.

**Rule 5 (Adhi, 28 October 2026): nothing is a photograph.**
- Every visual is made: the temple and the doll in 3D, ornaments as vectors or code, all detailed, sculpted and lit to look real.
- Photographs are private references only.
- The cultural roots behind each made thing are in `TAMIL_DESIGN_ROOTS.md`, section 12 (version 2).

1. **A temple that reads as a place, not a game.**
   - Model a Thanjavur-style vimana procedurally in Blender. Follow the anatomy in B5, with proportions from a primary source. Add the sculpted niches (koshta), the shala and kuta roof pavilions, and the kalasa.
   - Bake physically based materials: granite, weathered sandstone, gold leaf on the finial only.
   - Light it with a golden-hour sky that lights the scene, with post-processing: soft glow on gold, ambient occlusion, light shafts, haze, a little depth of field.
   - Add the life Adhi asked for:
     - real 3D banana and coconut plants moving in wind;
     - lamps that flicker;
     - birds crossing;
     - the kolam drawing itself on the courtyard stone.
   - Compress with meshopt and KTX2, and render with the WebGPU renderer, which falls back to WebGL 2.
   - Show it to Adhi alone first, before it touches the page.
2. **Text first, scene second.**
   - The headline and buttons paint first, from the server.
   - The scene streams in after, built off the main thread: an OffscreenCanvas in a worker where the browser allows it.
   - Target: LCP within 2.0 s and no long task over 50 ms from the 3D.
   - Weak phones get a still or a short video rendered from the same scene.
3. **Fewer draw calls.** Merge and batch static stone into a few meshes and use instancing for repeated sculpture, with a target to be set by benchmark. 534 per frame is far too many for this scene.
4. **One story, about half the length.**
   - Merge the 17 sections into about nine: the opening, the problem, how a deal works, the record, the Passport, both sides, the comparison, questions, and join.
   - The scroll walks from the gateway to the sanctum, one stage per section (`TAMIL_DESIGN_ROOTS.md`, the temple as information architecture).
5. **Signature 3D moments beyond the opening.** Each is small and loaded only when reached, and each is made by the recipes in `TAMIL_DESIGN_ROOTS.md` section 12:
   - **the doll**, modelled from a doll we buy, with a mould seam, a hand-painted surface and physics-driven rocking (12.4);
   - **the seal**, cast bronze with raised gold and an inscription-like rim (12.1, 12.5, 12.6);
   - **the deal history as a palm-leaf bundle** tied by the hash chain (12.3);
   - **the memo's woven temple border**, where the two parties meet (12.11);
   - **a kolam generated from each deal's record** (12.12);
   - **a lamp lit** when a deal completes (12.13).
6. **Hierarchy.** Not everything is a card. Use real type scale and space for most content, cards only for the product's own objects, and gold only on what is sealed.
7. **Ornament placed, never cropped.** Kolams sit inside the grid, at set sizes, away from the header.
8. **A one-row phone header.** The role switch moves into the opening section and a menu; the 3D control moves into settings or the footer.
9. **Ready to be found:**
   - server rendering in Next.js 16;
   - a meta description and share image per page;
   - structured data;
   - self-hosted, subset fonts with matched fallbacks;
   - AVIF images.
10. **Measured in CI:** Lighthouse budgets, the no-JavaScript test, axe, a frame-time test on a throttled profile, and asset-size limits (standard sections 4, 8b and 12).

---

## Part D. Decisions needed

| # | Decision | Who | Recommendation |
|---|---|---|---|
| 1 | Burgundy and gold (this homepage) or deep green (Harish, 28 October) | Both founders | One brand across site and apps; decide before any screen is built |
| 2 | Amend standard 8b so a procedural model with baked materials is allowed beside captured objects | Adhi | **Decided: D-142** |
| 3 | Install Blender 5 (free) on Adhi's machine for the model | Adhi | **Decided: D-142** (Blender 5.2.3) |
| 4 | Temple form: Thanjavur vimana, or a Madurai-style gopuram | Adhi | Thanjavur, matching the gold, the doll and the current page |
| 5 | React Three Fiber v9 with WebGPU opt-in, or plain three.js, until R3F v10 is stable | Adhi | Plain three.js for the opening scene; R3F inside the app if needed |
| 6 | Flutter or Expo for the apps | Both founders | Expo, per the locked stack, unless Harish shows Flutter's case |
| 7 | shadcn/ui on Base UI rather than Radix | Adhi | Base UI |
| 8 | The mark: "கோlyv.ai" or another form, and the domain | Adhi | After the domain is chosen (item 4 in the backlog) |
| 9 | The 3D byte budget and the reference phones (a ₹9,000 to ₹17,000 Android) | Adhi | Set from a benchmark before the scene is built |
| 10 | The Tamil body font | Adhi | Test Noto Sans Tamil and Anek Tamil at real sizes |
| 11 | Write rule 5 (nothing is a photograph) into standard 8a, which today allows licensed images | Adhi | **Decided: D-142** |
| 12 | The doll's 3D reference: a doll we buy, or the prototype's own doll picture if Adhi made it | Adhi | The prototype's picture, if Adhi made it; it is the doll he already chose |

---

## Part E. What was looked for and not found

- A 2026 Ookla mobile-speed median for India.
- Peer-reviewed 2024 to 2026 research on colour and trust in financial interfaces.
- The official Awwwards Site of the Year 2025.
- A primary source for the Brihadeeswarar vimana's storey count.
- Any licensed 3D scan of the Brihadeeswarar.
- Firefox's current status for scroll-driven animations.
- Passkey adoption in India.
- Official AI SDK v6 documentation.
- An analytics-tool comparison.

Each is a follow-up, not an assumption.
