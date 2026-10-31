# The frontend's finish line

**For:** the founders, to see how far the website and both apps are from complete, counted rather than guessed; and whoever builds the frontend, to pick the next item. **Written 31 October 2026** at Adhi's request ("bigger like backend and more"; "smooth as butter and billion times better in all aspects"), as the frontend's counterpart to `docs/BACKEND_COMPLETE.md`. **Counted from the code and branches on 31 October 2026.** Not reviewed by Erode Harish, who owns frontend design research (`CLAUDE.md` section 0).

**Keeping count:** an item stays in its table when built, marked **Built** with its date and decision, so progress is counted from this file alone, as the backend's finish line does. The numbers in section 2 are generated from the tables.

**The research behind it** (each read before working in its area):

| Area | File |
|---|---|
| The bar, binding | `docs/standards/frontend.md` |
| The architecture: 41 parts, the order of work | `docs/PROPOSAL_FRONTEND_ARCHITECTURE.md` |
| Feel and motion: smoothness, measured | `docs/research/FEEL_AND_MOTION_2026.md` |
| Colour psychology | `docs/research/COLOUR_PSYCHOLOGY_2026.md` |
| Interface psychology | `docs/research/INTERFACE_PSYCHOLOGY_2026.md` |
| Trust, and the line we never cross | `docs/PSYCHOLOGY_AND_TRUST.md` |
| Aesthetics and the craft canon | `docs/research/AESTHETICS_2026.md` |
| Interface styles: glass and every "morphism" | `docs/research/UI_STYLES_2026.md` |
| Typography | `docs/research/TYPOGRAPHY_2026.md` |
| The futurist frontend | `docs/research/FUTURIST_FRONTEND_2026.md` |
| The test bench: phones and laptop | `docs/research/REFERENCE_DEVICES_2026.md` |
| Research with people, ready to run | `docs/research/PEOPLE_RESEARCH_KIT.md` |
| Tamil roots of every visual choice | `docs/research/TAMIL_DESIGN_ROOTS.md` |
| The landing page judged against our people | `docs/research/LANDING_CULTURE_FIT.md` |
| The prototype audit and sixteen areas of research | `docs/research/FRONTEND_RESEARCH_2026.md` |
| Screens and their API | `frontend/design/screen-plan.md`, `docs/FRONTEND_BLUEPRINT_MAPPING.md` |

---

## 1. What "complete" means

The frontend is complete when **every item below is built and proven to `docs/standards/frontend.md`, or deferred past launch by a recorded decision**, on the website and in both apps. Items blocked from outside count once their part is built behind a switch.

It does **not** mean:
- **Not "live".** Going live needs the AWS account and the store accounts.
- **Not "every idea built".** An item is here because launch quality, the screen plan or the bar needs it.
- **Not "it looks good to us".** Every visual item marked *Judged* is set beside its named reference and the prototypes and judged better by a founder (`frontend.md` section 8a), and every item has a proof a tool or a person can check.

## 2. Where we are

**341 items: 0 built on `main` (0.0%), 4 built on a branch and not merged (1.2%), 52 started (15.2%), 275 open, 10 blocked.**

| Section | Items | Built | On a branch | Started | Open | Blocked |
|---|---|---|---|---|---|---|
| 4. Decisions that come first | 19 | 0 | 0 | 4 | 15 | 0 |
| 5. Visual identity | 21 | 0 | 2 | 1 | 17 | 1 |
| 6. Design system foundations | 15 | 0 | 1 | 5 | 9 | 0 |
| 7. Components | 68 | 0 | 0 | 19 | 49 | 0 |
| 8. Experience and research with people | 17 | 0 | 0 | 2 | 15 | 0 |
| 9. Journeys, end to end | 16 | 0 | 0 | 1 | 15 | 0 |
| 10. Screens | 69 | 0 | 0 | 8 | 59 | 2 |
| 11. The landing page and public pages | 15 | 0 | 0 | 0 | 11 | 4 |
| 12. Motion | 14 | 0 | 0 | 1 | 13 | 0 |
| 13. Animation, 3D and the signature moments | 16 | 0 | 0 | 3 | 13 | 0 |
| 14. Accessibility | 10 | 0 | 1 | 1 | 8 | 0 |
| 15. Performance and smoothness | 11 | 0 | 0 | 0 | 11 | 0 |
| 16. Engineering and quality | 14 | 0 | 0 | 5 | 8 | 1 |
| 17. Being found and shared | 6 | 0 | 0 | 0 | 6 | 0 |
| 18. The apps | 18 | 0 | 0 | 1 | 16 | 1 |
| 19. Ahead of everyone | 6 | 0 | 0 | 1 | 4 | 1 |
| 20. Release and operations | 6 | 0 | 0 | 0 | 6 | 0 |
| **All** | **341** | **0** | **4** | **52** | **275** | **10** |

**Read honestly:**
- **Nothing is built to the bar on `main` yet.** The merged web app (pull request #78) is a first version: its screens and components are counted as *Started*, to be rebuilt, not patched (`frontend.md`, "Gaps, named").
- **"On a branch"** is the design-foundations work (OKLCH tokens, the contrast gate over 112 pairs, both themes, the token pipeline), on `feature/design-foundations`, not merged.
- **Started 3D** is the temple and seal renders on `feature/temple-study`, below the bar by their own notes.
- **No item has been tested with people yet.** Section 8 is where that starts, and `docs/research/PEOPLE_RESEARCH_KIT.md` makes each session ready to run.
- **The research behind every area is checked against primary sources** (31 October 2026): browser support from MDN's browser-compat-data, fonts from their own files, springs from Google's Compose source, studies from their original papers. What only people, the founders or outside parties can settle is an item below with its owner, never an open question.

## 3. How an item is counted and proven

- **Built**: merged to `main`, its proof passing in CI or written up, and, if *Judged*, judged better than its reference by a founder. Marked with the date and the decision.
- **On a branch**: built and proven on a branch, not merged.
- **Started**: something exists, below the bar.
- **Open**: nothing yet.
- **Blocked**: waits on something outside the code, named in its row.

**Gates:** *Decision* (a founder's choice, recorded), *Dependency* (a package, approved in `CLAUDE.md` section 5's format), *Security* (a security review), *Judged* (a founder judges it against the reference), or none beyond the bar.

**Every rule is broken on purpose** where it is a gate (token lint, banned words, contrast, frame test, budgets, axe): the check must be seen to fail before it counts, as on the backend (`CLAUDE.md` section 7.0).

---

## 4. Decisions that come first

Each is a founder's choice, recorded in `docs/DECISIONS.md` before the work it shapes. Nothing below that depends on one is built before it.

| # | Item | Done when (the proof) | Gate | Status |
|---|---|---|---|---|
| F1 | **The accent colour**, by the five-second test with brand owners and creators | Test written up; one accent locked (`docs/research/COLOUR_PSYCHOLOGY_2026.md` section 8) | Decision | Started |
| F2 | **The style, "granite and light"** | A decision entry (`docs/research/UI_STYLES_2026.md` section 4) | Decision | Open |
| F3 | **The apps' framework**: Expo (the locked stack) or Flutter (Harish's app) | Both founders, by 15 November (`docs/PROPOSAL_FRONTEND_ARCHITECTURE.md` section 9) | Decision | Open |
| F4 | **Primitives**: Base UI under our components | Dependency request approved | Dependency | Open |
| F5 | **The component catalogue**: our own page or Storybook | Decision entry | Dependency | Started |
| F6 | **The message catalogue library** | Dependency request approved | Dependency | Open |
| F7 | **The API client generator**: Hey API or Orval, benchmarked on our 200+ operations | Benchmark written; decision entry | Dependency | Started |
| F8 | **The lint tool**: Biome or Oxlint | Decision entry (`frontend.md` section 2) | Dependency | Open |
| F9 | **Sessions on the web**: httpOnly cookies through the website's own server routes | Security review written; decision entry | Security | Started |
| F10 | **Scroll**: native everywhere; a smooth-scroll library only after a measured win | Decision entry (`docs/research/FEEL_AND_MOTION_2026.md` section 13) | Decision | Open |
| F11 | **Scene engine**: GSAP for pinned signature scenes, Motion for the rest | Frame test run; decision entry | Dependency | Open |
| F12 | **3D stack**: three.js WebGPU renderer with WebGL 2, plain or through React Three Fiber | Decision entry (`FRONTEND_RESEARCH_2026.md` B5) | Dependency | Open |
| F13 | **The byte budgets**: per frame-sequence scene, per 3D scene, fonts per page | Set by benchmark on the budget Android | Decision | Open |
| F14 | **The reference phones and laptop**: a Galaxy A07, a Galaxy A17 or A27, a second-hand iPhone 11 or SE (2nd generation), a founder's laptop | Bought, as `docs/research/REFERENCE_DEVICES_2026.md` section 2 recommends | Decision | Open |
| F15 | **The typefaces**: interface sans, display, mono, Tamil companion | Tests in `docs/research/TYPOGRAPHY_2026.md` section 7 run; decision entry | Decision | Open |
| F16 | **Analytics tool**, privacy-respecting, events tied to success measures | Decision entry (`frontend.md` section 13) | Dependency | Open |
| F17 | **Which offline actions queue** in the apps | Decision entry (`frontend.md` section 5) | Decision | Open |
| F18 | **Who judges "better than the reference"** | Decision entry (`docs/research/AESTHETICS_2026.md` section 6) | Decision | Open |
| F19 | **Where the frontend lives for good** and how it deploys | Both founders (`docs/PROPOSAL_FRONTEND_HOME_AND_STACK.md`) | Decision | Open |

## 5. Visual identity

The look, as a system. Research: `docs/research/AESTHETICS_2026.md`, `COLOUR_PSYCHOLOGY_2026.md`, `TYPOGRAPHY_2026.md`, `UI_STYLES_2026.md`, `TAMIL_DESIGN_ROOTS.md`.

| # | Item | Done when (the proof) | Gate | Status |
|---|---|---|---|---|
| F20 | **Colour system**: OKLCH tokens, warm neutral base, one accent, state colours, raised gold for sealed things | Contrast gate passes every text-on-surface pair at 7:1 body, both themes | — | On a branch |
| F21 | **Colour roles** bound to meanings (`COLOUR_PSYCHOLOGY_2026.md` section 3) | Lint: a state token used for decoration fails | — | Open |
| F22 | **Colour-vision safety**: state colours checked under deuteranomaly, protanomaly, tritanomaly simulations | CI test fails below the set difference | — | Open |
| F23 | **Dark theme** (temple dusk), designed not inverted | Screenshots of every component in both themes; contrast gate | — | On a branch |
| F24 | **High contrast and forced colours** (Windows high contrast, `forced-colors`) | Browser test in forced-colours mode | — | Open |
| F25 | **Type system**: three or four steps, tabular figures, Indian grouping | Type-scale visual test; lint on number components | — | Open |
| F26 | **The display face** in the landing opening and signature moments | Founder judges against the references | Judged | Open |
| F27 | **The mark (logo)**, within the ₹5,000 budget | Waits on the name and domain (backend item 4) | Decision | Blocked |
| F28 | **Icon set** on a 24 grid, one stroke | Icon-sheet visual test | — | Started |
| F29 | **Our own glyphs**: memo, proof, seal, UPI, record, stage, payment | Each drawn, named and in the sheet | Judged | Open |
| F30 | **Spacing scale** (8-point, 4 for tight UI) and the 12-column grid | Lint: no raw spacing | — | Open |
| F31 | **Radii and nesting rule**; squircle corners as an enhancement | Token rule and visual test | — | Open |
| F32 | **Elevation**: three levels, layered shadows from the one light | Tokens; visual test both themes | — | Open |
| F33 | **The light**: temple dusk from the front-left, one source per scene | Every scene and highlight checked against it | Judged | Open |
| F34 | **Materials in 2D**: raised gold, bronze, granite, silk-border recipes in CSS and SVG | Each against its reference photo (private), founder judged | Judged | Open |
| F35 | **Glass** on navigation only, at most two blurs on screen, solid fallback and a setting | Contrast over the worst background; frame test with and without | — | Open |
| F36 | **Grain**: one tiled asset, hero and signature moments only | Asset budgeted; visual test | — | Open |
| F37 | **The kolam generator**: half a kolam at an edge, by kolam rules, at most one per page | Generator tested; count in review | Judged | Open |
| F38 | **The thoranam**, once, at the join | Founder judged | Judged | Open |
| F39 | **Imagery register**: every visual a real screen or a made asset, rights written | Register complete before release (D-142) | — | Open |
| F40 | **The craft canon** (25 details, `AESTHETICS_2026.md` section 5) as a review checklist | Checklist in every screen review | — | Open |

## 6. Design system foundations

One source for every value, and the checks that keep screens from drifting.

| # | Item | Done when (the proof) | Gate | Status |
|---|---|---|---|---|
| F41 | **Token pipeline**: W3C Design Tokens to CSS variables, Tailwind theme, Dart and JS | Generated in CI; a token diff on every pull request | — | On a branch |
| F42 | **Token lint**: a raw colour, size, radius or duration in a component fails | Lint rule broken on purpose, seen to fail | — | Open |
| F43 | **Motion tokens**: springs (duration, bounce) for space, eased durations for effects | Tokens generated; lint bans raw durations | — | Open |
| F44 | **Primitives** under every interactive component | Keyboard and screen-reader test per primitive | Dependency | Open |
| F45 | **The catalogue**: every component and state on one browsable page | Builds in CI; every state present | — | Started |
| F46 | **Visual regression harness** at 360 px and desktop, light and dark | An unreviewed pixel change fails | Dependency | Open |
| F47 | **Message catalogue** (ICU), every string out of components | Pseudo-locale build in CI | Dependency | Open |
| F48 | **Banned-words check** over catalogue and code (constraint 1) | CI check broken on purpose, seen to fail | — | Open |
| F49 | **Generated API client and types** from `docs/api/openapi.json` | Regenerated in CI; drift fails | — | Started |
| F50 | **Forms from the OpenAPI schemas**: same limits as the backend | A field the backend refuses is refused in the form first, tested | — | Open |
| F51 | **Every error code mapped to a sentence** | A test that every `code` in the contract has a message | — | Open |
| F52 | **The five-state kit**: loading, empty, error, success, offline | Each state a component, screenshot-tested | — | Started |
| F53 | **Formatting core**: money (₹1,50,000), IST dates, relative time | Unit tests, Intl `en-IN`, 90% coverage | — | Started |
| F54 | **Query conventions**: TanStack Query keys, cursor pagination, no copied server state | Lint and review rule; contract tests | — | Started |
| F55 | **Idempotency-Key on every write**, retry rules for 503 and 429 | Test per write (`frontend.md` section 5) | — | Open |

## 7. Components

Each is done when it has every state (default, hover, pressed, focused, disabled, loading, error), both themes, 360 px and desktop, keyboard and screen reader, a screenshot test per state, and its catalogue entry (`frontend.md` section 8). **Started** means a first version exists in `frontend/apps/web/src/components` (pull request #78, green, v1); it is rebuilt to this bar, not patched.

| # | Item | Done when (the proof) | Gate | Status |
|---|---|---|---|---|
| F56 | **Button (primary, secondary, quiet, danger; sizes; loading)** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Started |
| F57 | **Icon button** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Started |
| F58 | **Link** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Open |
| F59 | **Text and headings** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Open |
| F60 | **Icon** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Started |
| F61 | **Divider** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Open |
| F62 | **Surface (solid and glass)** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Open |
| F63 | **Grain** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Open |
| F64 | **Text field** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Started |
| F65 | **Text area with a counter** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Open |
| F66 | **Select (native and customizable)** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Open |
| F67 | **Combobox (search as you type)** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Open |
| F68 | **Phone field (+91)** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Open |
| F69 | **One-time code field** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Started |
| F70 | **Money field (₹, Indian grouping, paise on the wire)** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Open |
| F71 | **Date field and calendar (IST)** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Open |
| F72 | **Checkbox** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Open |
| F73 | **Radio and choice group** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Started |
| F74 | **Switch** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Open |
| F75 | **Segmented control** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Open |
| F76 | **File upload with progress, resumable** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Open |
| F77 | **Slider and range (followers, budget)** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Open |
| F78 | **Dialog** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Open |
| F79 | **Sheet (bottom on phones, side on web)** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Open |
| F80 | **Popover** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Open |
| F81 | **Tooltip** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Open |
| F82 | **Menu** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Open |
| F83 | **Command menu (⌘K)** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Open |
| F84 | **Toast stack** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Open |
| F85 | **Card** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Started |
| F86 | **Bento tile (hero, wide, square)** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Open |
| F87 | **Badge and status pill (word plus icon)** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Started |
| F88 | **Avatar and avatar stack** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Open |
| F89 | **Table, virtualised, sortable** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Started |
| F90 | **List, virtualised, infinite (cursor)** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Open |
| F91 | **Stat and number ticker** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Started |
| F92 | **Empty state** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Started |
| F93 | **Skeleton (shaped, left-to-right shimmer)** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Started |
| F94 | **Banner and notice** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Started |
| F95 | **Progress (linear and steps)** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Open |
| F96 | **Tabs** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Open |
| F97 | **Accordion** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Open |
| F98 | **Pagination control (load more)** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Open |
| F99 | **Image viewer (proof gallery, pinch and zoom)** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Open |
| F100 | **QR code (UPI on the web)** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Open |
| F101 | **Chart: sparkline and bar (reliability, earnings)** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Started |
| F102 | **Countdown to a real deadline (IST)** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Started |
| F103 | **Timeline** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Open |
| F104 | **Deal pass (the hub of one deal)** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Open |
| F105 | **Stage stepper with whose move it is** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Started |
| F106 | **Deal board (stages as columns)** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Started |
| F107 | **Memo view** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Open |
| F108 | **Memo changes (what changed since the last version)** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Open |
| F109 | **Record timeline (sealed entries, who acted)** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Open |
| F110 | **Seal (guilloché from the record's hash)** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Open |
| F111 | **Payment status card** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Started |
| F112 | **Proof card** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Open |
| F113 | **Draft review card** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Open |
| F114 | **Passport card** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Open |
| F115 | **Delivery record summary** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Open |
| F116 | **Brand reliability card** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Open |
| F117 | **Text-flag warning beside a field** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Open |
| F118 | **Step-up code sheet** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Open |
| F119 | **Offer sheet (name a figure, accept, counter)** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Open |
| F120 | **Fair-rate meter (five creators or nothing)** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Open |
| F121 | **Availability calendar** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Open |
| F122 | **Brand switcher (team members in several brands)** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Open |
| F123 | **Kolam edge (generated)** | Every state, both themes, two widths, keyboard and screen reader, screenshot-tested | — | Started |

## 8. Experience and research with people

Research: `docs/research/INTERFACE_PSYCHOLOGY_2026.md`, `docs/PSYCHOLOGY_AND_TRUST.md`, `docs/standards/ux.md`. Every item here is about people, so its proof is a written result in `docs/research/`. The founders run them; `docs/research/PEOPLE_RESEARCH_KIT.md` holds the scripts, numbers and write-up format.

| # | Item | Done when (the proof) | Gate | Status |
|---|---|---|---|---|
| F124 | **Five conversations per side** before a flow is final (the Mom Test) | Ten write-ups (kit section 3; `docs/standards/ux.md` section 2) | — | Open |
| F125 | **Five-second tests** of the landing opening and both Today screens, 10 brand owners and 10 creators | Pass marks met (kit section 4) | — | Open |
| F126 | **Task tests** of each core journey, completion and errors measured | 90% completion, no critical confusion (kit section 6) | — | Open |
| F127 | **The colour test** (accent, trust and clarity) | Written result (kit section 5) | — | Open |
| F128 | **Sessions with people who use assistive technology** | Every blocker fixed (kit section 7) | — | Open |
| F129 | **Site map as the temple**: gateway, hall, courtyards, sanctum | Tree test with both roles | — | Open |
| F130 | **Navigation**: web sidebar and ⌘K, phone bottom tabs, depth of three taps at most | Tree test; end-to-end depth check | — | Started |
| F131 | **Onboarding**: a creator's first application in under five minutes | Timed in task tests | — | Open |
| F132 | **Empty states** on every screen with the next useful step | Five-state review | — | Started |
| F133 | **Peak and end designed**: deal sealed, payment confirmed, record closed | Pilot debrief: what people remember (`INTERFACE_PSYCHOLOGY_2026.md` section 4) | Judged | Open |
| F134 | **The worst moments calmed**: late payment, dispute, refusal | Copy and screen review against the rules | — | Open |
| F135 | **Defaults that protect the person** who does not change them | Review of every default | — | Open |
| F136 | **Voice and microcopy guide**: plain English, buttons say what happens | Guide written; catalogue reviewed against it (`docs/standards/ux.md` section 6) | — | Open |
| F137 | **Notifications design**: what, when, how urgent, quiet hours shown | Matrix of events and channels reviewed | — | Open |
| F138 | **Search and filter experience** for Discover and Find creators | Task test | — | Open |
| F139 | **Success measures and named events** for each journey | Events listed and tied to measures (`docs/standards/ux.md` section 2) | — | Open |
| F140 | **Dark-pattern audit** against the thirteen banned patterns | Checklist passed before release (`docs/standards/legal.md` section 3) | — | Open |

## 9. Journeys, end to end

Each runs in Playwright on the website and Maestro in the apps, on every pull request, against the slow-4G profile and offline where the journey allows (`frontend.md` section 11).

| # | Item | Done when (the proof) | Gate | Status |
|---|---|---|---|---|
| F141 | **Sign up, with the adults-only check, both roles** | Passes on web and both apps, slow 4G, failure cases included | — | Started |
| F142 | **Post a campaign (four steps) and publish it** | Passes on web and both apps, slow 4G, failure cases included | — | Open |
| F143 | **Discover campaigns and apply, with rate guidance** | Passes on web and both apps, slow 4G, failure cases included | — | Open |
| F144 | **Invite a creator; work together again from a finished deal** | Passes on web and both apps, slow 4G, failure cases included | — | Open |
| F145 | **Shortlist, accept and reject with a reason** | Passes on web and both apps, slow 4G, failure cases included | — | Open |
| F146 | **Offers: name a figure, counter, accept** | Passes on web and both apps, slow 4G, failure cases included | — | Open |
| F147 | **Write, send, review, change and accept a deal memo** | Passes on web and both apps, slow 4G, failure cases included | — | Open |
| F148 | **Draft first: submit a draft, approve or ask for changes** | Passes on web and both apps, slow 4G, failure cases included | — | Open |
| F149 | **Submit proof with files; approve or ask for a fix** | Passes on web and both apps, slow 4G, failure cases included | — | Open |
| F150 | **Pay by UPI link or mark a payment sent, one or many** | Passes on web and both apps, slow 4G, failure cases included | — | Open |
| F151 | **Confirm receipt, or open a dispute and add evidence** | Passes on web and both apps, slow 4G, failure cases included | — | Open |
| F152 | **Barter: ship goods, confirm receipt** | Passes on web and both apps, slow 4G, failure cases included | — | Open |
| F153 | **Block and report, and see what became of a report** | Passes on web and both apps, slow 4G, failure cases included | — | Open |
| F154 | **A brand's team: invite, join, act in a role, leave** | Passes on web and both apps, slow 4G, failure cases included | — | Open |
| F155 | **Delete my account, and cancel it within 30 days** | Passes on web and both apps, slow 4G, failure cases included | — | Open |
| F156 | **Download my data** | Passes on web and both apps, slow 4G, failure cases included | — | Open |

## 10. Screens

Every screen in `frontend/design/screen-plan.md` (Harish's plan, with his IDs) and its section 6b, plus what the backend has added since. A screen is done when it meets `frontend.md` section 14 on the website **and** in both apps. **Started** means a v1 exists on the website from pull request #78. B13 to B15 are C11 to C13 from the brand's side and are counted there.

| # | Item | Done when (the proof) | Gate | Status |
|---|---|---|---|---|
| F157 | **S1 Sign in** (Both; Must) | `frontend.md` section 14, on web and both apps | — | Started |
| F158 | **S2 Enter code** (Both; Must) | `frontend.md` section 14, on web and both apps | — | Started |
| F159 | **C0 Onboarding, two steps** (Creator; Must) | `frontend.md` section 14, on web and both apps | — | Open |
| F160 | **C1 Today** (Creator; Must) | `frontend.md` section 14, on web and both apps | — | Started |
| F161 | **C2 Discover** (Creator; Must) | `frontend.md` section 14, on web and both apps | — | Open |
| F162 | **C3 Campaign** (Creator; Must) | `frontend.md` section 14, on web and both apps | — | Open |
| F163 | **C4 Apply** (Creator; Must) | `frontend.md` section 14, on web and both apps | — | Open |
| F164 | **C5 My applications** (Creator; Must) | `frontend.md` section 14, on web and both apps | — | Open |
| F165 | **C6 Deals** (Creator; Must) | `frontend.md` section 14, on web and both apps | — | Started |
| F166 | **C7 Deal pass** (Creator; Must) | `frontend.md` section 14, on web and both apps | — | Open |
| F167 | **C8 Memo, read and answer** (Creator; Must) | `frontend.md` section 14, on web and both apps | — | Open |
| F168 | **C9 Send work** (Creator; Must) | `frontend.md` section 14, on web and both apps | — | Open |
| F169 | **C10 Payment** (Creator; Must) | `frontend.md` section 14, on web and both apps | — | Open |
| F170 | **C11 Dispute** (Both; Must) | `frontend.md` section 14, on web and both apps | — | Open |
| F171 | **C12 Deal record** (Both; Must) | `frontend.md` section 14, on web and both apps | — | Open |
| F172 | **C13 Inbox** (Both; Must) | `frontend.md` section 14, on web and both apps | — | Open |
| F173 | **C14 Me** (Creator; Must) | `frontend.md` section 14, on web and both apps | — | Started |
| F174 | **C15 Passport** (Creator; Must) | `frontend.md` section 14, on web and both apps | — | Open |
| F175 | **C16 About you** (Creator; Must) | `frontend.md` section 14, on web and both apps | — | Open |
| F176 | **C17 Channels** (Creator; Must) | `frontend.md` section 14, on web and both apps | — | Open |
| F177 | **C18 Rate card** (Creator; Must) | `frontend.md` section 14, on web and both apps | — | Open |
| F178 | **C19 Account** (Both; Must) | `frontend.md` section 14, on web and both apps | — | Open |
| F179 | **B0 Brand setup** (Brand; Must) | `frontend.md` section 14, on web and both apps | — | Open |
| F180 | **B1 Today** (Brand; Must) | `frontend.md` section 14, on web and both apps | — | Started |
| F181 | **B2 Campaigns** (Brand; Must) | `frontend.md` section 14, on web and both apps | — | Open |
| F182 | **B3 New campaign, four steps** (Brand; Must) | `frontend.md` section 14, on web and both apps | — | Open |
| F183 | **B4 Campaign applicants** (Brand; Must) | `frontend.md` section 14, on web and both apps | — | Open |
| F184 | **B5 Creator profile** (Brand; Must) | `frontend.md` section 14, on web and both apps | — | Open |
| F185 | **B6 Suggested creators** (Brand; Should) | `frontend.md` section 14, on web and both apps | — | Open |
| F186 | **B7 Write memo** (Brand; Must) | `frontend.md` section 14, on web and both apps | — | Open |
| F187 | **B8 Review and send** (Brand; Must) | `frontend.md` section 14, on web and both apps | — | Open |
| F188 | **B9 Deals** (Brand; Must) | `frontend.md` section 14, on web and both apps | — | Started |
| F189 | **B10 Deal pass** (Brand; Must) | `frontend.md` section 14, on web and both apps | — | Open |
| F190 | **B11 Review work** (Brand; Must) | `frontend.md` section 14, on web and both apps | — | Open |
| F191 | **B12 Pay creators** (Brand; Must) | `frontend.md` section 14, on web and both apps | — | Started |
| F192 | **B16 Me** (Brand; Must) | `frontend.md` section 14, on web and both apps | — | Open |
| F193 | **Invitation, answer one** (Creator; Must) | `frontend.md` section 14, on web and both apps | — | Open |
| F194 | **Invite a creator** (Brand; Must) | `frontend.md` section 14, on web and both apps | — | Open |
| F195 | **Offer sheet** (Both; Must) | `frontend.md` section 14, on web and both apps | — | Open |
| F196 | **Report and block** (Both; Must) | `frontend.md` section 14, on web and both apps | — | Open |
| F197 | **Delete my account** (Both; Must) | `frontend.md` section 14, on web and both apps | — | Open |
| F198 | **Step-up sheet** (Both; Must) | `frontend.md` section 14, on web and both apps | — | Open |
| F199 | **Draft review (send a draft; approve or ask for changes)** (Both; Must) | `frontend.md` section 14, on web and both apps | — | Open |
| F200 | **Earnings** (Creator; Should) | `frontend.md` section 14, on web and both apps | — | Open |
| F201 | **My UPI ID** (Creator; Should) | `frontend.md` section 14, on web and both apps | — | Open |
| F202 | **Notification preferences** (Both; Should) | `frontend.md` section 14, on web and both apps | — | Open |
| F203 | **Where I am signed in** (Both; Should) | `frontend.md` section 14, on web and both apps | — | Open |
| F204 | **Download my data** (Both; Should) | `frontend.md` section 14, on web and both apps | — | Open |
| F205 | **Feedback on a finished deal** (Both; Should) | `frontend.md` section 14, on web and both apps | — | Open |
| F206 | **Deal notes** (Both; Should) | `frontend.md` section 14, on web and both apps | — | Open |
| F207 | **Product shipment (barter)** (Both; Should) | `frontend.md` section 14, on web and both apps | — | Open |
| F208 | **Work together again** (Brand; Should) | `frontend.md` section 14, on web and both apps | — | Open |
| F209 | **Add dates to my calendar** (Both; Should) | `frontend.md` section 14, on web and both apps | — | Open |
| F210 | **Find creators** (Brand; Should) | `frontend.md` section 14, on web and both apps | — | Open |
| F211 | **Verify my website** (Brand; Should) | `frontend.md` section 14, on web and both apps | — | Open |
| F212 | **Team: invite, roles, remove** (Brand; Should) | `frontend.md` section 14, on web and both apps | — | Open |
| F213 | **My team invites, and choosing a brand** (Brand; Should) | `frontend.md` section 14, on web and both apps | — | Open |
| F214 | **Change my phone number** (Both; Later) | `frontend.md` section 14, on web and both apps | — | Open |
| F215 | **Saved creator lists** (Brand; Later) | `frontend.md` section 14, on web and both apps | — | Open |
| F216 | **More like my best** (Brand; Later) | `frontend.md` section 14, on web and both apps | — | Open |
| F217 | **Campaign alerts** (Creator; Later) | `frontend.md` section 14, on web and both apps | — | Open |
| F218 | **My availability** (Creator; Later) | `frontend.md` section 14, on web and both apps | — | Open |
| F219 | **Campaign report (page and spreadsheet)** (Brand; Later) | `frontend.md` section 14, on web and both apps | — | Open |
| F220 | **Content library** (Brand; Later) | `frontend.md` section 14, on web and both apps | — | Open |
| F221 | **Assistant tokens and invite codes** (Both; Later) | `frontend.md` section 14, on web and both apps | — | Open |
| F222 | **Connected accounts (Instagram, YouTube)** (Creator; Later) | `frontend.md` section 14, on web and both apps | — | Blocked |
| F223 | **Passkeys** (Both; Later) | `frontend.md` section 14, on web and both apps | — | Blocked |
| F224 | **Admin console (report queue, legal clocks)** (Founders; Decision) | `frontend.md` section 14, on web and both apps | — | Open |
| F225 | **Not found, offline and error pages** (Both; Must) | `frontend.md` section 14, on web and both apps | — | Open |

## 11. The landing page and public pages

Eight sections in the temple's order (`docs/PROPOSAL_FRONTEND_ARCHITECTURE.md` section 6), each judged beside its strongest reference and the prototype, plus the public pages people reach from a link.

| # | Item | Done when (the proof) | Gate | Status |
|---|---|---|---|---|
| F226 | **1. The opening**: one headline, one action, the temple turning in dusk light, a real product glimpse | LCP ≤ 2.0 s on slow 4G; judged better than the prototype | Judged | Open |
| F227 | **2. The two fears**: paid late, paid for fake reach, with sourced facts | Sources linked; judged | Judged | Open |
| F228 | **3. The fold**: one deal, both sides, three chapters | Frame test; ≤ 2.5 screens pinned; judged | Judged | Open |
| F229 | **4. How a deal works**: an interactive stepper with real screens | Keyboard operable; judged | Judged | Open |
| F230 | **5. The record and the seal**, and what Colyv never does | Words checked against constraint 1; judged | Judged | Open |
| F231 | **6. Both sides**: for brands, for creators, the Passport | Judged | Judged | Open |
| F232 | **7. How we compare**: honest and sourced | Every claim sourced (`docs/standards/legal.md` section 1) | Judged | Open |
| F233 | **8. Questions and joining the pilot**, the thoranam at this threshold | Form works when its endpoint exists (backend item 23) | Judged | Blocked |
| F234 | **Header and footer**: glass header on scroll, footer with the legal links | Contrast and frame tests | — | Open |
| F235 | **Public Passport** (`/c/handle`) with its share card | ≤ 50 KB JavaScript; readable without JavaScript | — | Open |
| F236 | **City pages** (`/creators/:city/:niche`), five or nothing | Server-rendered; structured data | — | Open |
| F237 | **Trust page**: how we use data, ASCI, DPDP | Waits on the validation pack's wording | — | Blocked |
| F238 | **Privacy notice and terms** | Waits on the validation pack | — | Blocked |
| F239 | **Pricing page** | Waits on the pricing model | Decision | Blocked |
| F240 | **Help and questions** | Server-rendered; searchable | — | Open |

## 12. Motion

Research: `docs/research/FEEL_AND_MOTION_2026.md`. Every item has a reduced-motion version and passes the frame test (≤ 1% dropped frames, no frame over 50 ms on the throttled profile).

| # | Item | Done when (the proof) | Gate | Status |
|---|---|---|---|---|
| F241 | **Motion principles** written: cause and effect, one moment per page, a still pose at the end | Principles in the catalogue; reviewed | — | Started |
| F242 | **Press feedback** within one frame on every control | Frame test on tap | — | Open |
| F243 | **State changes**: open, close, select, expand, with spatial springs | Frame test; reduce-motion test | — | Open |
| F244 | **Shared-element transitions** into a deal, memo or Passport (React `ViewTransition`) | Works with motion on and off | — | Open |
| F245 | **Cross-page transitions** on public pages, a cut where unsupported | Browser matrix test | — | Open |
| F246 | **List motion**: items entering, leaving and reordering on the deal board | No layout shift; frame test | — | Open |
| F247 | **Number ticker** for money and counts, tabular, never jittering | Visual test | — | Open |
| F248 | **Scroll reveals** in CSS scroll timelines, Motion `scroll()` as fallback | Content visible without JavaScript and with reduce motion | — | Open |
| F249 | **Sheets and drawers** that follow the finger and keep its velocity | Frame test on the budget Android | — | Open |
| F250 | **Toasts and banners** entering and leaving | Frame test | — | Open |
| F251 | **Loading choreography**: nothing heavy before the page is readable | Lighthouse: LCP untouched by motion | — | Open |
| F252 | **Haptics** in the apps where a physical act completes | Device test | — | Open |
| F253 | **Calm versions of everything** (reduce motion, reduce transparency, Save-Data) | Browser and device tests both ways (WCAG 2.3.3, AAA) | — | Open |
| F254 | **The frame test in CI**, broken on purpose and seen to fail | Deliberately bad fixture fails the gate | — | Open |

## 13. Animation, 3D and the signature moments

Made, never photographed (D-142). Research: `TAMIL_DESIGN_ROOTS.md` sections 9 and 12, `FRONTEND_RESEARCH_2026.md` B5, `FEEL_AND_MOTION_2026.md` sections 6 to 8.

| # | Item | Done when (the proof) | Gate | Status |
|---|---|---|---|---|
| F255 | **The temple, modelled**: the Thanjavur vimana from a primary source for its proportions | Primary source cited; founder judged | Judged | Started |
| F256 | **Temple faults closed**: granite reading as plaster, the hidden lamp, no people, palms, base mouldings, pavilion variety at 4K | Each fault closed in the render notes; judged | Judged | Started |
| F257 | **The temple scroll sequence**: path-traced frames, AVIF, progressive, on a canvas | Within its byte budget; frame test; poster first | — | Open |
| F258 | **The seal**: a guilloché generated from the record's hash, raised gold | Unit test: one hash, one seal; judged | Judged | Started |
| F259 | **The seal closing**: drawn from both halves, meeting at the crease | Frame test; reduced version | Judged | Open |
| F260 | **The fold sequence**: three chapters as pre-rendered frames | ≤ 2.5 screens pinned; frame test; judged | Judged | Open |
| F261 | **The thalaiyatti bommai**: bought or commissioned, then modelled or drawn in Rive | Rights written; judged | Decision | Open |
| F262 | **Deal agreed** moment | One orchestrated moment; reduced version | Judged | Open |
| F263 | **Deal sealed** moment | Judged; reduced version | Judged | Open |
| F264 | **Payment confirmed** moment: calm, final, gold | Judged; reduced version | Judged | Open |
| F265 | **The Passport card**, live and interactive where it earns it | Live 3D budget; WebGL 2 path | Judged | Open |
| F266 | **A turnable seal** (live WebGPU, WebGL 2 fallback), if it earns its place | Frame and byte budgets; paused off screen | Decision | Open |
| F267 | **Poster stills** for every scene, rendered from the same scene | Shown for reduce motion, Save-Data and weak phones | — | Open |
| F268 | **Asset pipeline**: gltf-transform, meshopt, KTX2; frames to AVIF | CI checks every asset's size | — | Open |
| F269 | **Adaptive grandeur**: quality chosen by device class in the first second | Test on each reference phone | — | Open |
| F270 | **The 3D budget gate** in CI | Broken on purpose, seen to fail | — | Open |

## 14. Accessibility

WCAG 2.2 AA is the floor; above it as `frontend.md` section 6 sets, and AAA for motion (2.3.3).

| # | Item | Done when (the proof) | Gate | Status |
|---|---|---|---|---|
| F271 | **axe in CI** on every page and component, failing the build | Broken on purpose, seen to fail | — | Started |
| F272 | **Keyboard**: every action reachable, a visible focus ring that belongs to the design | Keyboard test per journey | — | Open |
| F273 | **Screen readers**: TalkBack, VoiceOver, NVDA pass on the core journeys | Manual pass before each release | — | Open |
| F274 | **Text at 200%** with nothing cut off | Browser test | — | Open |
| F275 | **Targets** 48 dp and 44 pt with spacing | Lint on component sizes; device check | — | Open |
| F276 | **Body text 7:1**, components 4.5:1, both themes, glass included | Contrast gate | — | On a branch |
| F277 | **Reduced motion and transparency** everywhere | Tests with each setting on | — | Open |
| F278 | **Forms**: visible labels, errors announced and tied to fields | axe and screen-reader test | — | Open |
| F279 | **3D and scenes say everything in text too** | Screen reader hears the text, not the scene | — | Open |
| F280 | **Accessibility statement** published | Reviewed; duties confirmed by the validation pack (constraint 6) | — | Open |

## 15. Performance and smoothness

Budgets in `frontend.md` section 4, measured on the reference devices and network, never estimated.

| # | Item | Done when (the proof) | Gate | Status |
|---|---|---|---|---|
| F281 | **Lighthouse CI**: Performance 95, Accessibility, Best practices and SEO 100 | Gate fails the build | — | Open |
| F282 | **LCP ≤ 2.0 s, INP ≤ 150 ms, CLS ≤ 0.05** at the 75th percentile | Lab in CI; field each release | — | Open |
| F283 | **JavaScript per route** ≤ 150 KB, public pages ≤ 50 KB | Bundle check fails the build | — | Open |
| F284 | **The frame test**: ≤ 1% dropped, no frame over 50 ms | Playwright and CDP trace in CI (`FEEL_AND_MOTION_2026.md` section 10) | — | Open |
| F285 | **Real-user monitoring**: Core Web Vitals with Long Animation Frame attribution | Dashboard reviewed each release | Dependency | Open |
| F286 | **Fonts**: subset, self-hosted, preloaded, metric-matched fallbacks | No font layout shift | — | Open |
| F287 | **Images**: AVIF or WebP at display size, fixed dimensions, lazy below the fold | Lighthouse image audits pass | — | Open |
| F288 | **Instant navigation**: prefetch, and Speculation Rules on public pages | Measured navigation time on the reference phone | — | Open |
| F289 | **Skeleton within 100 ms**; no loader under about 300 ms | Browser test with delayed responses | — | Open |
| F290 | **Slow-4G and offline end-to-end runs** | Every journey under the profile | — | Open |
| F291 | **The reference bench** used for every release | Results recorded per release | — | Open |

## 16. Engineering and quality

`frontend.md` sections 2, 9 to 12.

| # | Item | Done when (the proof) | Gate | Status |
|---|---|---|---|---|
| F292 | **Repository**: pnpm workspace with apps and shared packages (`api`, `tokens`, `ui`, `core`, `messages`) | Builds and type checks in CI | — | Started |
| F293 | **TypeScript at its strictest**, casts commented | Type check and lint in CI | — | Started |
| F294 | **Shared core** with 90% coverage | Coverage gate | — | Open |
| F295 | **Unit and component tests** for every rule and state | In CI | — | Started |
| F296 | **Contract test**: the generated client against `docs/api/openapi.json` | Drift fails CI | — | Started |
| F297 | **Content Security Policy** with nonces and Trusted Types | Security test | Security | Open |
| F298 | **Sessions**: tokens in httpOnly cookies or memory, never localStorage | Security test | Security | Started |
| F299 | **Deep links validated**; a link opens, never acts | Test per link type | Security | Open |
| F300 | **No personal data** in logs, analytics or crash reports | Scrubbing tests | Security | Open |
| F301 | **Sentry** for the website and apps, scrubbed | An error traced to its backend request | Dependency | Open |
| F302 | **Dependency audit and licence check** in CI | Gate fails on a finding | — | Open |
| F303 | **Preview deployment per pull request** | Link on every pull request | Decision | Open |
| F304 | **Feature flags**, reading which backend features are on | Waits on backend request R6 (`frontend/design/screen-plan.md` section 8) | — | Blocked |
| F305 | **Frontend CI workflow** running every gate above | All gates green on a pull request | — | Open |

## 17. Being found and shared

`frontend.md` section 8d.

| # | Item | Done when (the proof) | Gate | Status |
|---|---|---|---|---|
| F306 | **Every public page server-rendered**, complete without JavaScript | The no-JavaScript test in CI | — | Open |
| F307 | **Titles, descriptions and canonical links** per page | SEO 100 in Lighthouse | — | Open |
| F308 | **Generated share cards** for Passports, city pages and the landing page | Snapshot test of each card | — | Open |
| F309 | **Structured data** where it applies | Validator in CI | — | Open |
| F310 | **Sitemap and robots**, Passports included only when published | Test against publish state | — | Open |
| F311 | **Readable by AI search**: every public page's text in the HTML | No-JavaScript test | — | Open |

## 18. The apps

Android first (`frontend.md` section 1). Each screen in the Screens section is built in the apps too; these are the platform pieces around them.

| # | Item | Done when (the proof) | Gate | Status |
|---|---|---|---|---|
| F312 | **Framework set up** with the shared core, tokens and client | Builds in CI for both platforms | — | Started |
| F313 | **Native controls** where it counts (iPhone feels like iPhone, Android like Android) | Device review | — | Open |
| F314 | **Push** registered on login, removed on logout | Device test against `PUT /api/v1/me/devices` | — | Open |
| F315 | **Lock-screen deal stages**: Android 16 Live Updates, iOS Live Activities | Device test (`FUTURIST_FRONTEND_2026.md` section 1) | — | Open |
| F316 | **Home-screen widget**: what needs me today | Device test | Decision | Open |
| F317 | **Offline**: recent deals, memos and proof readable; queued actions in order | Offline end-to-end tests | Decision | Open |
| F318 | **Camera proof capture**, compressed on the phone, resumable upload | Kill-the-app test mid-upload | — | Open |
| F319 | **Fingerprint or Face ID** to confirm accepting a memo or marking paid | Device test | Security | Open |
| F320 | **Deep links** from WhatsApp and notifications | Test per link | Security | Open |
| F321 | **Haptics** on completed physical acts | Device test | — | Open |
| F322 | **Cold start** ≤ 2.0 s on the budget Android, 1.5 s on the older iPhone | Measured each release | — | Open |
| F323 | **60 fps, under 1% slow frames** on lists and transitions | Platform frame tools each release | — | Open |
| F324 | **Crash-free sessions ≥ 99.8%**, ANR ≤ 0.2% | Staged rollout gates | — | Open |
| F325 | **Download size ≤ 30 MB** on Android | Tracked every release | — | Open |
| F326 | **Maestro end-to-end** for every journey | On every pull request | — | Open |
| F327 | **Store listings**: screenshots, descriptions, privacy labels | Reviewed before submission | — | Open |
| F328 | **Staged rollout and over-the-air rules** | Written before the first release | — | Open |
| F329 | **App review submissions** (Play, App Store) | Accepted by both stores | — | Blocked |

## 19. Ahead of everyone

The pieces no competitor in `docs/COMPETITIVE_LANDSCAPE.md` was found to have (`docs/research/FUTURIST_FRONTEND_2026.md` section 5). Each also appears where it is built; here they are counted as the product's promise.

| # | Item | Done when (the proof) | Gate | Status |
|---|---|---|---|---|
| F330 | **A deal's stage on the lock screen** | Shipped in the apps' first release | — | Open |
| F331 | **The seal from the deal's own fingerprint**, closing across the fold | Shipped on the landing page and the sealed record | Judged | Started |
| F332 | **Instant public pages**: prerendered on intent, gliding between each other | Measured navigation under 100 ms on the reference laptop | — | Open |
| F333 | **Share cards per Passport** that look professional in a WhatsApp group | Snapshot tests; judged | Judged | Open |
| F334 | **Adaptive grandeur**: the richest version each phone can hold | Reference-phone tests | — | Open |
| F335 | **"Ask Colyv" answering with real components**, constrained to ours | Waits on backend items 40 and 41 | Decision | Blocked |

## 20. Release and operations

`frontend.md` sections 12 and 13.

| # | Item | Done when (the proof) | Gate | Status |
|---|---|---|---|---|
| F336 | **Design review ritual**: each screen beside its reference and the prototypes | Notes kept per screen | Judged | Open |
| F337 | **The dark-pattern self-audit**, yearly and before launch | Result displayed as the e-commerce rules require | — | Open |
| F338 | **Rollback steps written** before the first release | Rehearsed once | — | Open |
| F339 | **Field data reviewed** each release against the budgets | Review notes per release | — | Open |
| F340 | **Changelog** people can read | Published with each release | — | Open |
| F341 | **Founders' sign-off** that the frontend is complete | Both founders, against this file | Decision | Open |

---

## 21. Keeping this file true

- Updated in the same pull request as any work that moves an item; the counts in section 2 are regenerated, never typed.
- An item leaves *Open* only with its proof; it becomes *Built* only on `main`.
- Re-checked against `frontend/design/screen-plan.md` when the screen plan changes, and against the research files when one is revised.
- When every item is built or deferred by decision, and the backend's finish line is complete too, both founders sign off (the last item).
