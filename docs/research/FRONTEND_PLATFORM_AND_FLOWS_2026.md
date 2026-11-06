# Frontend platform and flows: today's releases against our code, and the marketplace flows against the leaders

**For:** whoever builds the website and the apps, and `docs/FRONTEND_COMPLETE.md`, which turns each *Next* into an item. **Written 6 November 2026** at Adhi's request ("world class research with depth ... frontend, UX, UI, motion, Framer"). It adds to the 31 October set (`FEEL_AND_MOTION_2026.md`, `FUTURIST_FRONTEND_2026.md`, `FRONTEND_RESEARCH_2026.md` and the rest), which researched look, motion physics, 3D and what is new; this file does two things they did not: it reads **our code** against the platform's current releases, and it sets **the marketplace's own flows** against the leaders'. Every claim about our code was read from `main` that day.

---

## 1. The web platform, release by release

| What | Current release | Ours (`frontend/apps/web`) | Next |
|---|---|---|---|
| **Next.js** | 16 (21 October 2025): Turbopack the default bundler; **Cache Components** (`"use cache"` on pages, components and functions, replacing the experimental partial prerendering flag); **React Compiler support stable but opt-in** (`reactCompiler: true`) (Next.js blog, "Next.js 16") | 16.4.3; only `inlineCss` set; **Compiler off; Cache Components off** | (1) Switch the React Compiler on behind the frame test (`FEEL_AND_MOTION_2026.md` section 10) and the interaction budget: it removes most hand-written memoisation, and its gain is measured, not assumed. (2) Cache Components for the public pages (landing, Passport, ranking explained), each cached with the tag the API's change invalidates |
| **React** | 19.3 (9 September 2026): **`<ViewTransition>` stable** (DOM only) with `addTransitionType`; Fragment Refs stable; no breaking changes (React blog). 19.2 (1 October 2025) brought `<Activity>` and `useEffectEvent` | 19.3.1; no `<ViewTransition>` anywhere | Move between screens with `<ViewTransition>` and the browser's own View Transitions, typed per kind of move (forward, back, open a detail), so the browser animates on the compositor; `<Activity>` to keep a list's scroll and filters alive while a detail is open |
| **Motion** (formerly Framer Motion) | 14.x (the changelog pages found were cached at 13.1 and 12.40; Motion UI's first entry is dated 23 July 2026; Motion+ added "curtains" page transitions) | `motion` ^14.0.0 | Keep Motion for what the platform does not do: springs on gestures, drag, shared layout inside a screen, scroll-linked values. Route transitions move to `<ViewTransition>` (above), so the two never animate the same thing. Read motion.dev's changelog for 14.x before the next upgrade, since the cached pages are stale |
| **Data** | TanStack Query 5 | ^5.104.1 | Hold every list to the API's keyset pages with `useInfiniteQuery`, and every create to the API's `Idempotency-Key`, so a retried tap never makes two applications (backend research 1.2) |

## 2. Measuring what real people feel

- **The bar:** Google's thresholds are unchanged for 2026: largest paint under 2.5 s, interaction to next paint (INP) under 200 ms, layout shift under 0.1, judged on 28 days of real-user data (CrUX); lab scores are for debugging (web.dev; secondary 2026 guides). The `web-vitals` library (6.x) attributes a slow interaction to the long animation frames behind it (LoAF entries on `onINP`'s attribution); **soft navigations** (measuring each screen of a single-page app as its own page) are still experimental.
- **Ours:** no real-user measurement in the app; the frame test and Lighthouse are lab tools.
- **Next:** the attribution build of `web-vitals` sending each page's vitals, its long animation frames and the device class (never a person's identity, `legal.md`) to an endpoint of our own API, rate limited; budgets per device from `REFERENCE_DEVICES_2026.md`; a weekly report beside the backend's. Soft navigations switched on when they leave experimental. **Ahead:** publish the 75th-percentile INP on budget Android phones in Tamil Nadu, the users competitors' dashboards are slowest for.

## 3. The apps

- **The evidence:** Flutter renders with Impeller on iOS and Android; React Native's New Architecture removed the old bridge, and Expo SDK 55 (React Native 0.83, React 19.2) has dropped the legacy architecture. The one frame benchmark found (SynergyBoat, cited by Shorebird, a vendor in Flutter's ecosystem) reports worst-case frame drops of 0% for Flutter with Impeller, 15.51% for React Native and 1.61% for native Swift; other 2026 comparisons call both "native-class" for most work and disagree on market share. Treat the benchmark as one vendor-cited data point.
- **Ours:** `frontend/apps/mobile` is a Flutter project (Dart SDK ^3.13.5); the design tokens already generate Dart (`colyv_tokens.dart`), checked in CI. Which framework the apps use for good is still both founders' decision (`CLAUDE.md` section 0).
- **Next:** settle it by our own test, not vendors': one screen (the campaign list with its filters and a detail) built in both, run on the reference phones under the frame test; the result and a D-entry. Recommended going in: Flutter, for frame consistency on budget phones and the token pipeline already there.

## 4. The marketplace's flows against the leaders

The evidence on what makes a list usable and a stranger trusted:

- **Lists:** across Baymard's benchmark of 344 e-commerce sites, sites with mediocre product-list usability saw 67 to 90% of users abandon, against 17 to 33% for a slightly better filtering toolset (Baymard, filtering research); Baymard's marketplace benchmark rates 24 leading marketplaces on 1,254 interface elements (detail behind its paywall).
- **Trust between strangers:** in a controlled study, moderate, credible ratings raised trust while extremely high ratings or enormous counts sometimes raised suspicion; listings with no reviews were trusted least; a visible photo and a verified badge raised confidence (Télécom Paris, Quant UX lab). Ratings, reviews and full profiles act as "systems of control" that make trust possible without meeting (Hesse et al., HICSS-53).

| Flow | The leader's version | Ours, and how it goes further | Next |
|---|---|---|---|
| A brand posts a campaign | Aspire: publish a "proposal" to its marketplace in seconds, creators apply in its portal; Collabstr: post a brief, creators come to you (paid plans) | Festival templates prefill a campaign (D-161, D-165); the brief drafter writes one from a brand's own words (item 40) | The posting flow measured against Baymard-style task success with five brands (`PEOPLE_RESEARCH_KIT.md`) before it is called done |
| A brand finds creators | Collabstr lists rates on every profile before contact | Rate cards public only with the creator's consent (D-055); search in plain words that shows how it read them (D-158); every match with its reasons and the brand's own payment record beside the creator's delivery record | Filters held to Baymard's list rules: applied filters always visible and removable one by one, counts before applying, no dead ends |
| A creator decides whether to trust a brand | Upwork shows whether a client's payment is verified and its hiring history | A brand's median days to pay and its record (D-027), a verified domain (item 74), a look-alike name flagged (item 75) | Show counts with every average ("4.6 from 3 deals"), an honest "new on Colyv" for no history, never a bare 5.0: the study above says extreme ratings and empty profiles both cost trust |
| Agreeing a deal | Platforms that handle the money hold it until delivery | A sealed deal memo both sides accept; payment tracked, never held (constraint 1); any party can verify the record (`DEAL_RECORD_VERIFY.md`) | The memo screen as the clearest page in the product: every term in plain words, the seal explained in one line |
| Feedback | Two-sided reviews | Revealed only when both answered or the window closed (D-136), no retaliation | Show the reveal rule at the moment of writing, so people write honestly |

## 5. Craft: the bar for the landing page

Framer-built sites and Awwwards winners are the craft people compare a startup's landing page to. Craft is judged here by measurement, not by resemblance: the frame test, the interaction budget and the people sessions (`FEEL_AND_MOTION_2026.md`, `LANDING_CINEMA_2026.md`, `AESTHETICS_2026.md`'s 25-point canon), on the reference phones. A landing that looks like a Framer template fails D-141's Tamil soul, whatever its polish.

## 6. What this research adds to the frontend finish line

React Compiler on, behind the frame test; Cache Components for public pages with API-driven invalidation; `<ViewTransition>` for screen changes, Motion for gestures and in-screen layout only; idempotent creates and keyset lists in TanStack Query; real-user vitals with long-animation-frame attribution and a weekly report; the apps' framework settled by our own two-screen test; filters to Baymard's rules; counts with every rating and an honest "new"; the deal memo as the clearest screen; the feedback reveal rule shown when writing.

## Sources (read 6 November 2026)

- Next.js 16: https://nextjs.org/blog/next-16
- React 19.3: https://react.dev/blog/2026/09/09/react-19-3 ; React 19.2: https://www.react.dev/blog/2025/10/01/react-19-2
- Motion changelog: https://motion.dev/changelog?lib=motion ; https://motion.dev/updates
- web-vitals: https://cdn.jsdelivr.net/npm/web-vitals@6.2.3/README.md ; web.dev, Find slow interactions in the field: https://web.dev/find-slow-interactions-in-the-field/
- Flutter and React Native: https://shorebird.dev/blog/react-native-vs-flutter-for-enterprise-apps ; https://dev.to/kumarharsh/flutter-vs-react-native-in-2026-a-technical-architecture-comparison-13pd ; https://www.groovyweb.co/blog/react-native-vs-flutter-vs-expo-vs-lynx-2026
- Baymard: https://baymard.com/ecommerce-product-lists/benchmark/page-types/filtering-options ; https://baymard.com/ux-benchmark/collections/marketplace
- Trust cues: https://quantux.telecom-paris.fr/?p=489 ; Hesse et al., HICSS-53: https://scholarspace.manoa.hawaii.edu/items/a5557992-d575-436f-912e-1357044086df
- Aspire and Collabstr flows: https://help.aspireiq.com/en/articles/5834942-publish-your-project-in-the-marketplace ; https://collabstr.com/features/post-campaigns/
- Upwork, client verification: https://www.upwork.com/resources/upwork-vs-fiverr
