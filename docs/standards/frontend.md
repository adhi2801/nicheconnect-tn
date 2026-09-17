# Frontend Standard

**Status: for later.** Frontend work (brand web dashboard, creator mobile app) starts only after the backend is complete (D-004). Nothing in this file is built in the backend repository. It exists so the backend is designed to serve a first-class frontend, and so frontend work starts with an agreed bar.

Rules marked **(decision)** are decided when frontend work begins.

---

## 1. Platforms and stack

- **(decision)** web framework (e.g. Next.js or React + Vite) and mobile framework (React Native per the original plan, e.g. with Expo).
- TypeScript in strict mode everywhere. No `any` without a comment explaining why.
- API client and types are generated from the backend's OpenAPI schema, never typed by hand.
- One shared design-token source feeds web and mobile (colours, type, spacing, radii, motion).

## 2. Who we're building for

- Brands: small and mid-size Tamil Nadu businesses, often on laptops, sometimes on phones.
- Creators: mostly on **Android phones, including low and mid-range devices, on mobile data**.
- Both: Tamil and English speakers. Many prefer Tamil for reading, and English for technical terms.

Design and performance decisions start from the creator on a budget Android phone on a patchy 4G connection.

## 3. Performance budgets

**Web (measured at the 75th percentile on mobile):**

| Metric | Budget |
|---|---|
| Largest Contentful Paint | ≤ 2.5 s |
| Interaction to Next Paint | ≤ 200 ms |
| Cumulative Layout Shift | ≤ 0.1 |
| JavaScript per route (compressed) | ≤ 170 KB initial |
| Lighthouse performance, mobile | ≥ 90 |

**Mobile app:**

| Metric | Budget |
|---|---|
| Cold start to usable screen, mid-range Android | ≤ 2.5 s |
| Scrolling and animations | 60 fps, no dropped frames on lists |
| Install size | as small as practical; tracked each release |
| Crash-free sessions | ≥ 99.5% |

- Images are responsive, compressed (WebP/AVIF) and lazy-loaded.
- Lists virtualise. Screens show skeletons within 100 ms.

## 4. Resilience

- Every screen designs for four states: **loading, empty, error, and success**.
- Network errors show a clear message and a retry. No infinite spinners; requests time out.
- Mobile: recently viewed data is cached for offline reading; actions taken offline are queued or clearly blocked. **(decision)** which ones.
- Forms keep what the user typed if a submit fails.
- Optimistic updates only where the backend operation is idempotent.

## 5. Accessibility

- **WCAG 2.2 AA** minimum, on web and mobile.
- Text contrast ≥ 4.5:1 (≥ 3:1 for large text and UI components).
- Touch targets ≥ 44 × 44 px.
- Everything works with a keyboard (web) and screen readers (TalkBack, VoiceOver).
- Supports text scaling to 200% without breaking layout.
- Automated checks (axe or equivalent) in CI, plus a manual screen-reader pass before each release.

## 6. Localisation

- Tamil and English from the first screen. No hard-coded strings; everything goes through the i18n system.
- Tamil text is written by a fluent speaker, not machine-translated without review.
- Layouts allow for longer Tamil strings and use fonts with full Tamil glyph support.
- Numbers, dates and currency use Indian conventions: `₹1,50,000`, `17 Sep 2026`.

## 7. Security on the client

- Tokens: on web, in httpOnly secure cookies or memory, never `localStorage`. On mobile, in the platform keystore or keychain.
- Never store PII in analytics events or crash reports.
- Validate inputs on the client for usability; the backend remains the authority.

## 8. Code quality

- Component folders by feature, not by type.
- Server state through one data-fetching library with caching; no hand-rolled global stores for API data. **(decision)** which library.
- Unit tests for logic, component tests for key UI, end-to-end tests for core journeys (sign up, post campaign, apply, accept deal memo, mark and confirm payment).
- Lint, format and type check in CI; merge blocked on failure.

## 9. Analytics and release

- A privacy-respecting analytics plan with named events tied to success metrics. **(decision)** tool.
- Feature flags for risky features.
- Staged mobile rollouts (e.g. 10% → 50% → 100%) with crash monitoring.
