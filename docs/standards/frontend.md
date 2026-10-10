# Frontend Standard

**Status: for later, and binding from the first line of frontend code.** Design may run now; frontend **code** starts only when the backend is complete (D-004, amended by D-053), in a repository of its own, never this one. This file exists so the backend is built to serve an excellent frontend, and so frontend work starts with a bar already agreed.

**The bar is excellent, not acceptable.** Every rule here is either measured by a tool and gated in CI, or checked at a named release step. A rule nobody can check is not in this file. Where a published threshold exists (Google's Core Web Vitals, Google Play's Android vitals), our target is stricter than it: staying under a platform's "bad behaviour" line only avoids a penalty.

Rules marked **(decision)** are open and are decided, with a `docs/DECISIONS.md` entry, when frontend work begins. Everything else is settled.

---

## 1. Platforms and roles

- **Three clients: a website, an Android app and an iOS app. Each serves brands and creators in full**; the role you sign in with decides what you see (D-046: Adhi's direction, awaiting Erode Harish). Nothing in the backend assumes one client per role.
- **The website is the front door and the desk; the app is the pocket** (`docs/PLATFORM_AND_TECH_PLAN.md` section 2). The website wins on being found, on bulk work and on side-by-side comparison; the app wins on capture, alerts, offline and instant login.
- **Everyone can see everything on both.** "App only" means a task done better on a phone, never data withheld from the website. No install wall, ever (section 2.5 of the plan: Myntra's 2015 to 2016 lesson).
- **Android first.** India is 92 to 95% Android. A feature that ships on one platform first ships on Android.
- **Adults only** (D-086): sign-up asks for the date of birth once, says it is not kept, and nothing is built for minors.

## 2. Stack (locked, D-047)

The stack is the one in `docs/PLATFORM_AND_TECH_PLAN.md` section 4.3, re-checked against current releases when frontend work starts (D-047's upgrade rule): **Expo** (React Native, New Architecture, Hermes, Expo Router) for both apps, **Next.js** for the website, **TypeScript** everywhere, **Expo UI** for genuinely native controls (SwiftUI and Jetpack Compose), **Tailwind CSS v4 with shadcn/ui** on the website and **NativeWind** in the apps, **PowerSync** for offline, **Playwright** and **Maestro** for end-to-end tests.

Still open: the API client generator (Hey API or Orval) **(decision)**, the lint tool (Biome or Oxlint) **(decision)**, the login provider **(decision)**, the deferred deep-link provider **(decision)**.

Rules that hold whatever the versions:

- **One repository for the frontend, three apps, one shared core.** The core holds the generated API client, design tokens, message catalogues, formatting, and business rules. A rule written twice is a bug waiting to disagree with itself.
- **TypeScript at its strictest**: `strict`, `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`, `noImplicitOverride`. `any`, `as` casts and non-null assertions (`!`) need a comment saying why; the linter enforces it.
- **The API client and its types are generated from `docs/api/openapi.json`**, never written by hand, and regenerated in CI. The backend already fails its own build when the contract changes unannounced, so a client generated from it cannot silently drift.
- **Request validation comes from the same contract.** Form schemas are generated from the OpenAPI schemas, so a field the backend refuses is refused in the form first, with the same limits.

## 3. Who we build for, and the devices we test on

- **Creators**: mostly on Android phones, many of them budget or mid-range, on mobile data that drops in and out. **Brands**: small and mid-size Tamil Nadu businesses, at a laptop or on the move.
- **Every design and performance decision starts from the creator on a budget Android phone on patchy 4G.** A screen that is excellent there is excellent everywhere.

**Reference devices (a physical test bench, not only emulators)** **(decision: exact models, chosen by current Indian sales at frontend start):**

| Tier | Example class | Used for |
|---|---|---|
| Budget Android | 4 GB RAM, Android 14 or later, entry chipset | Every performance budget below is measured here |
| Mid-range Android | 6 to 8 GB RAM, current mid-range chipset | The "typical creator" check |
| Older iPhone | The oldest iPhone the current iOS supports | iOS budgets |
| Laptop | Mid-range Windows laptop, Chrome | Website desk work |

**Reference network**: lab tests throttle to a slow 4G profile (about 1.6 Mbps down, 150 ms round trip) and also run fully offline. Widths from **360 px** to large desktop; text scaled to 200%.

## 4. Performance budgets

Measured, never estimated (`CLAUDE.md` section 7). **Field data** (real users) is the truth; **lab data** (CI) catches regressions before release. A budget breached in CI fails the build.

**Website, at the 75th percentile of real mobile visits:**

| Metric | Google's "good" line | **Our budget** |
|---|---|---|
| Largest Contentful Paint | ≤ 2.5 s | **≤ 2.0 s** |
| Interaction to Next Paint | ≤ 200 ms | **≤ 150 ms** |
| Cumulative Layout Shift | ≤ 0.1 | **≤ 0.05** |
| Time to First Byte | ≤ 0.8 s | **≤ 0.6 s** |
| JavaScript per route, compressed, first load | — | **≤ 150 KB**; public pages (Creator Passports, city pages) **≤ 50 KB** |
| Lighthouse, mobile, in CI | — | **Performance ≥ 95, Accessibility 100, Best practices 100, SEO 100** |

**Apps, on the budget Android reference device:**

| Metric | Google Play's limit | **Our budget** |
|---|---|---|
| Cold start to a usable screen | — | **≤ 2.0 s** (iOS reference: ≤ 1.5 s) |
| Frames | — | **60 fps; under 1% of frames slow** on scrolling lists and transitions |
| User-perceived crash rate | 1.09% overall, 8% per device | **Crash-free sessions ≥ 99.8%** |
| User-perceived ANR (app frozen) rate | 0.47% overall, 8% per device | **≤ 0.2% overall, ≤ 1% on any device model** |
| Download size, Android | — | **≤ 30 MB**, tracked every release (each extra 6 MB costs about 1% of installs) |
| Memory | — | No out-of-memory crash on the 4 GB reference device across the core journeys |

**How the budgets are kept:**

- Images are served in AVIF or WebP at the size displayed, lazy-loaded below the fold, with fixed dimensions so nothing shifts. Proof images arrive already re-encoded by the backend (D-065).
- Fonts are subset, self-hosted and preloaded, with metrics-matched fallbacks so text never shifts as they load.
- Lists of any length are virtualised. A screen shows its skeleton within **100 ms** of the tap.
- Public pages render on the server and ship almost no JavaScript.
- Every API call a screen needs is made in parallel, never in a chain. A screen that needs more than two calls to render is a backend request (`docs/standards/ux.md` section 7), not something to work around.

## 5. Resilience: nothing a person does is ever lost

- **Every screen designs five states**: loading, empty (with the next useful action), error, success, and **offline**. Designs without all five are not ready to build.
- **Every request has a timeout and a visible way out.** No spinner runs forever; after the timeout the person sees what happened and a retry.
- **Every write carries an `Idempotency-Key`** (D-040). A retry after a dropped connection can never create a second campaign or a second payment mark; the backend guarantees it, the client must use it.
- **Optimistic updates only where the write is idempotent**, and they roll back visibly when the server says no.
- **What a person types survives everything**: a failed submit, a lost connection, the app killed in the background. Drafts persist on the device until sent.
- **Uploads resume** after a dropped connection or a killed app, compressed on the device first (`docs/PLATFORM_AND_TECH_PLAN.md` A8). Proof files upload straight to storage with the signed form the backend issues (D-065).
- **Offline** (apps): recently viewed deals, memos and proofs stay readable; actions taken offline are queued and sent in order, or clearly refused **(decision: which actions queue)**. The person always knows which.
- **Errors come from the backend's one format** (RFC 9457 problem details, `application/problem+json`). The client maps each `code` to a message in the catalogue; it never shows a raw status code, a stack trace or the word "error" alone.

## 6. Accessibility

**WCAG 2.2 AA is the floor, on every platform.** Above it:

- Body text contrast **≥ 7:1** (AAA); large text and UI components ≥ 4.5:1. Colour is never the only signal.
- Touch targets **≥ 48 × 48 dp** on Android and **44 × 44 pt** on iOS, with spacing between them.
- Text scales to **200%** with nothing cut off or overlapping; the apps follow the system text size.
- Everything works with a keyboard on the website, and with TalkBack and VoiceOver in the apps, in a sensible order, with every control named.
- Motion respects "reduce motion"; nothing flashes more than three times a second.
- Every form field has a visible label, and every error is announced and tied to its field.

**Checked by:** automated checks (axe-core on the website, the platform accessibility scanners in the apps) in CI, failing the build; Lighthouse accessibility 100; **a manual TalkBack and VoiceOver pass on the core journeys before every release**; and usability sessions that include people who use assistive technology (`docs/standards/ux.md` section 2). Any legal accessibility duty is a validation pack question, never assumed (constraint 6).

## 7. Language, numbers and words

- **English only** (D-054). **Every string lives in a message catalogue**, never in a component, using ICU MessageFormat so plurals and variables are right ("1 applicant", "3 applicants"). A second language stays possible without a rewrite.
- **CI runs a pseudo-locale build** (every string accented and 40% longer). A string that appears unchanged was hard-coded; a layout that breaks was not built for longer text. Either fails the build.
- **Indian formats everywhere, through `Intl` with the `en-IN` locale, never by hand**: `₹1,50,000`, `17 Sep 2026`, and times in IST, because every deadline in this product is a date somebody lives (D-030).
- **Words that are never allowed**, enforced by a CI check over the catalogue and the code: "escrow", "wallet", "guaranteed funds", "split settlement", or anything implying we hold or move money (`CLAUDE.md` constraint 1).
- **Results read from proof are always labelled "read from the creator's screenshot"**, never "verified" (D-070). Only platform-verified numbers may say verified, and the same holds for every claim (`docs/standards/legal.md` section 1, rule 3).
- **No dark patterns.** Every screen is checked against the thirteen banned by the Consumer Protection Authority (`docs/standards/legal.md` section 3.5) before release, and the yearly self-audit the e-commerce rules require from 1 January 2027 is a release step (section 12).
- Microcopy follows `docs/standards/ux.md` section 6: buttons say what happens; errors say what went wrong and how to fix it.

## 8. Design system

- **One token source** in the W3C Design Tokens format (first stable version, 2025.10), feeding the website, both apps and the design tool. Colour, type, spacing, radii, elevation and motion are tokens; a raw value in a component fails lint.
- **Light and dark themes**, both meeting section 6's contrast, from the same tokens.
- **Native where it counts**: Expo UI renders real SwiftUI and Jetpack Compose controls, so iPhone feels like iPhone (Liquid Glass) and Android like Android (Material 3 Expressive). Brand comes from tokens, not from fighting the platform.
- **Every component is documented with every state** (default, pressed, focused, disabled, loading, error) in a component catalogue, and **visual regression tests** catch an unintended change to any of them.
- No one-off styles in screens. A missing component is added to the system first (`docs/standards/ux.md` section 4).

## 9. Data and state

- **Server data lives in one query cache** (TanStack Query, through the generated client), never copied into a hand-rolled global store. Local UI state stays local.
- **Lists use the backend's cursor pagination** (`?limit=&cursor=`, `next_cursor`) for infinite scroll; nothing fetches "everything".
- **Times shown are the server's**, formatted in IST. The device clock is never trusted for a deadline.
- **Nothing sensitive is cached** beyond what offline reading needs, and the cache is wiped on logout.

## 10. Security and privacy on the client

- **Tokens**: on the website, in `httpOnly`, `Secure`, `SameSite` cookies or in memory, **never `localStorage`**. In the apps, in the platform keystore or keychain only.
- **A strict Content Security Policy** on the website, with nonces, no inline scripts and Trusted Types; third-party scripts need a recorded reason.
- **Deep links are validated** before they act. A link can open a screen, never perform an action without the person confirming.
- **Another person's text is never made clickable.** Links arrive as fields the backend has already checked against its host list (`app/core/links.py`), and the client shows the host before opening one.
- **Warnings are shown, never suppressed**: every `text_flags` entry renders beside its field (`docs/standards/trust-and-safety.md` section 5).
- **UPI pay details** (D-085) are shown only on the brand's pay screen, never cached, and never logged. The `upi://pay` link opens the brand's own UPI app, or renders as a QR code on the website. The screen says to check the name the UPI app shows, and flags an ID changed in the last 24 hours (`upi_id_changed_recently`).
- **No personal data in analytics, logs or crash reports.** Phone numbers, payment references and message text are scrubbed before anything leaves the device.
- **Big steps are confirmed** with the device's fingerprint or Face ID where the platform offers it: accepting a memo, marking a payment sent (`docs/PLATFORM_AND_TECH_PLAN.md` A15, a security gate when built).
- **Dependencies** are pinned by lockfile, audited in CI, and licence-checked. A new package follows the same approval gate as the backend (`CLAUDE.md` section 5).
- Client checks are for usability only; **the backend is always the authority**.

## 11. Testing

| Layer | What | Bar |
|---|---|---|
| Unit | Business rules and formatting in the shared core | Every rule, including its failure cases |
| Component | Key components in every state | Every state in section 8 |
| End to end | **The core journeys** on the website (Playwright) and both apps (Maestro): sign up, with the adults-only check; post a campaign; discover and apply; invite, and work together again; shortlist; send, review and accept a deal memo; submit proof with files; pay by UPI link and mark the payment sent; confirm receipt or raise a dispute; block and report | Pass on every pull request, against the slow-4G profile, and offline where the journey allows |
| Contract | The generated client against `docs/api/openapi.json` | Regenerated in CI; any change is a reviewed diff |
| Visual | Screenshots of every component and core screen | No unreviewed pixel change |
| Accessibility | Section 6 | Automated in CI; manual before each release |
| Performance | Section 4 | Lab budgets in CI; field data reviewed each release |

Coverage floor: **90% of the shared core**, measured, never estimated; a high number never excuses a missing failure case (`docs/standards/testing.md`).

## 12. CI gates and release

**A pull request merges only when all of these pass**: format, lint and type check; unit, component, contract and end-to-end tests; bundle and download-size budgets; Lighthouse budgets; automated accessibility; the pseudo-locale check; the banned-words check; the dependency audit.

**Releases:**

- **Staged rollouts** for the apps (1%, then 10%, 50%, 100%), each step held until crash-free sessions and ANR rate meet section 4.
- **Over-the-air updates** only for JavaScript fixes inside the store's rules; anything native goes through a store release.
- **Feature flags** for anything risky, so it can be switched off without a release.
- **Every release can be rolled back**, and the steps are written down before the first one.
- **Once a year, and before launch: the dark-pattern self-audit** (`docs/standards/legal.md` section 3.4), with its result displayed as the e-commerce rules require from 1 January 2027.

## 13. Observability and analytics

- **Real-user performance** (Core Web Vitals on the website, start-up time and frame rate in the apps) is collected and reviewed against section 4 every release.
- **Errors and crashes go to Sentry**, with personal data scrubbed (`docs/standards/backend.md`), so a frontend error can be traced to the backend request behind it.
- **Analytics are privacy-respecting**, with named events tied to the success measures in `docs/standards/ux.md` section 2 **(decision: tool)**. Consent and retention follow the validation pack (constraint 6), never a guess.

## 14. Definition of done, for a screen

- [ ] Designed in all five states (section 5), at 360 px and at desktop width, light and dark
- [ ] Every string in the catalogue; pseudo-locale and banned-words checks pass
- [ ] Accessibility: automated checks pass, keyboard and screen reader work, 200% text works
- [ ] Performance budgets met on the reference device and network
- [ ] Every write sends an `Idempotency-Key`; every error maps a backend `code` to a message
- [ ] Unit, component and end-to-end tests written, including failure and offline cases
- [ ] No personal data in logs, analytics or crash reports
- [ ] Reviewed, CI green, and checked by a person on a real budget Android phone

---

## Sources

- [Core Web Vitals thresholds (web.dev)](https://web.dev/articles/vitals)
- [Android vitals: bad behaviour thresholds (Play Console Help)](https://support.google.com/googleplay/android-developer/answer/9844486?hl=en), [Raising the bar on technical quality on Google Play](https://android-developers.googleblog.com/2022/10/raising-bar-on-technical-quality-on-google-play.html)
- [Design Tokens specification reaches first stable version (W3C, 28 October 2025)](https://www.w3.org/community/design-tokens/2025/10/28/design-tokens-specification-reaches-first-stable-version/)
- [WCAG 2.2](https://www.w3.org/TR/WCAG22/)
- [RFC 9457: Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457)
- The stack, the platform split and the evidence behind them: `docs/PLATFORM_AND_TECH_PLAN.md` sections 2 and 4.3
