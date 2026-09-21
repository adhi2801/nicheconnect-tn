# Platform and technology plan

**What this is:** one place for what we build on each platform, how we stand apart from every competitor, and which technology every layer should use, with what starts now and what comes later. Written 22 September 2026 by Adhi's session from web research done that day. Sources are listed at the end.

**Last checked against current releases: 22 September 2026.** Re-check monthly (section 9). In this field a plan older than a month is already behind.

**Nothing here overrides `CLAUDE.md`.** Every item still goes through its approval gate. The constraints hold throughout: we never hold or move money, no personal data in embeddings, and compliance details come from the validation pack, never from research like this.

**Status words used below**

| Word | Meaning |
|---|---|
| **Decided** | Recorded in `docs/DECISIONS.md` |
| **Proposed** | A founder's direction or a written proposal, waiting for the approval it needs |
| **Recommended** | Claude's recommendation; nobody has decided yet |
| **Blocked** | Waiting on the validation pack or another decision |

**When words used below**

| Word | Meaning |
|---|---|
| **Now** | Backend work that can start this week or next |
| **Next** | Backend work that can start as soon as its decision is made |
| **Later** | The frontend phase, after the backend is complete (D-004) |
| **Watch** | Not ready yet; re-check at every monthly review |

---

## 1. Product scope

**Proposed (D-046, Adhi's direction on 22 September; needs Erode Harish too):**

- **Three platforms: a website, an Android app and an iOS app.**
- **Every platform serves brands and creators in full.** There is one app per platform; the role you sign in with decides what you see. The earlier split ("brand web dashboard, creator Android app") is withdrawn. It still appears in `CLAUDE.md` section 1, `docs/standards/frontend.md` and `docs/FRONTEND_BLUEPRINT_MAPPING.md`, which are updated once D-046 is decided.
- **The backend needs no rework for this.** Every endpoint already serves whichever role is signed in, from any client.
- **Order stays backend first (D-004).** Design, then the website and apps, start when the backend is complete.

**Open question for both founders:** today one phone number is one account with one role (`account.phone` is unique; D-014). With one app for both sides, someone who is both a food creator and a bakery owner needs two phone numbers. Keep that, or allow both roles on one number with a switch? The second changes the account tables (Data track, a migration, and a security review).

---

## 2. What the website is for, and what the app is for

**The rule: the website is the front door and the desk; the app is the pocket.**

- **Anyone can see anything on either.** Blocking a brand from checking a deal in a browser would cost trust, and Google penalises full-screen "install the app" walls on mobile pages.
- **Things done in the moment happen in the app.** Capture, alerts, voice, offline, instant login.
- **Things done in bulk or on a big screen happen on the website.** Building campaigns, comparing applicants, paying many creators, reports.

**Why the app has to earn its place:** apps keep people about 1.6 times better than the mobile web (32% against 20% at 90 days) and convert 2 to 4 times better. But 56% of apps are uninstalled within 7 days, mostly for storage, and every extra 6 MB of app size costs about 1% of installs. So the app needs real reasons to exist, and it has to stay small.

### 2.1 Only in the app

✅ only possible in an app · ◐ possible on the web, but only done properly in the app

| # | Feature | Why it matters | Technology | When |
|---|---|---|---|---|
| A1 | ✅ **Share a post from Instagram straight into NicheConnect as proof** | Proof in two taps, no copying links | Share extension (`expo-share-intent`) | Later |
| A2 | ✅ **Share the UPI receipt; the reference fills itself in; the payment is marked sent** | "Mark paid" becomes one tap after paying. We still never touch the money | On-device text recognition reads the UTR. **Needs testing** across UPI apps' receipt formats | Later |
| A3 | ✅ **Deal status on the lock screen and home screen**: "₹12,000 due to you, 2 days" | Nobody in this space has it | iOS Live Activities, Android 16/17 Live Updates, `expo-widgets` (Expo SDK 56) | Later |
| A4 | ✅ **Alerts that arrive.** On iPhone, web notifications only work once a site is added to the home screen | The app is the real-time channel; WhatsApp is the fallback for everyone | Push through FCM/APNs; backend stores device tokens (Data track) | Next (backend), Later (app) |
| A5 | ✅ **Login with no code to type**: the carrier confirms the SIM, then Face ID or fingerprint | Two-second login, safe from SIM-swap | Silent network authentication (Jio and Vi today through OTPless; Airtel in talks), then passkeys | Next (decision), Later (app) |
| A6 | ✅ **Works offline**: read memos, draft pitches, queue proof on patchy 4G | iOS web cannot sync in the background | PowerSync (local SQLite synced with Postgres) plus our retry-safe API (D-040) | Later |
| A7 | ✅ **Private AI on the phone**: proofread a pitch or summarise a memo without internet | Nothing leaves the phone | Apple Foundation Models (iOS 26+; iOS 27 lets any provider plug in), Gemini Nano Prompt API on Android. **Most budget Android phones lack Gemini Nano, so the cloud path stays the main one** | Later |
| A8 | ✅ **Uploads that survive app kills and bad networks**, compressed on the phone (D-024) | No lost work | Resumable (tus) background upload | Later |
| A9 | ◐ **Speak in Tamil or Tanglish**: pitches, briefs and replies by voice; memos read aloud | Tamil as the interface, not a filter | Sarvam Saaras v3 (speech to text, code-mixing), Bulbul v3 (Tamil voices); Bhashini as a free fallback | Next (backend), Later (app) |
| A10 | ✅ **Scan a shop's QR and apply at once on iPhone** | Offline to online in Tamil Nadu towns | App Clip. Android Instant Apps shut down in December 2025, so Android opens the website | Later |

### 2.2 Only on the website

| # | Feature | Why it matters | When |
|---|---|---|---|
| W1 | **Public Creator Passports, and pages like "food creators in Madurai"**, fast and indexed | How new people find us. Google's AI Mode only cites pages that rank in Google, and tables of facts are among the most cited formats | Later (pages); the Passport API already exists |
| W2 | **The brand desk**: compare 50 applicants side by side, a campaign builder with preview, bulk "mark paid" from a bank CSV (D-043), reports | Desk work belongs on a desk | Later |
| W3 | **Start without installing**: a first application or a first campaign from a WhatsApp link | No friction first; the app afterwards | Later |
| W4 | **Deal receipt check**: anyone scans a receipt's QR and verifies it in a browser, with no account | Trust that works outside our platform (see D1) | Next (backend), Later (page) |
| W5 | **AI agents and agencies**: run NicheConnect from inside ChatGPT or Claude; later a public API | A new way in. MCP Apps now work inside both | Later |
| W6 | **Account deletion link and privacy rights page** | Google Play requires the web link (section 7) | Blocked (validation pack) |

### 2.3 The bridge between them

- **Offer the app at the right moment, never with a wall:** a small, dismissible banner (Safari Smart App Banner, or our own small bar), shown after something the app does better. Examples: after an application is sent ("get told the moment they reply"), or after a memo is accepted ("see your payment clock on your lock screen").
- **The app opens on the exact thing the person was looking at**, even straight after install ("deferred deep linking"). Firebase Dynamic Links shut down on 25 August 2025, so this needs Branch, AppsFlyer OneLink or a self-hosted option such as LinkForty. **Decision later.**
- **App size budget (Recommended): under 30 MB download on Android**, tracked every release. Android App Bundles, Hermes bytecode, and heavy assets fetched only when needed.

---

## 3. How we stand clear of every competitor

The market in September 2026: discovery is free inside Instagram and YouTube. Paid platforms race on AI agents that work for brands (GRIN, Upfluence, Passionfroot, Agentio, TikTok Symphony) and on AI fake-follower screening (Reelax). **Their AI works for the brand, speaks English first, and estimates. Nobody owns the truth of the deal, Tamil as the product's language, or working well on a ₹10,000 phone.** The full competitor list is in `docs/COMPETITIVE_LANDSCAPE.md`.

| # | Differentiator | Why nobody else can match it | Technology | Owner | Status | When |
|---|---|---|---|---|---|---|
| D1 | **Tamper-proof deal record.** Every memo, proof, payment and dispute event is chained; each side can download a signed deal receipt with a QR anyone can check | Our records become evidence, not a claim | SHA-256 hash chain in Postgres plus Ed25519 signatures. No new vendor | Harish (table), Adhi (API) | Recommended | Next |
| D2 | **Verified audience instead of self-reported numbers.** The creator connects Instagram or YouTube; the Passport says "Verified by Instagram, as of <date>" | First-party numbers beat AI estimates | Instagram Graph API (Business/Creator accounts, `instagram_manage_insights`, creator's consent); YouTube Analytics API. **Apply for YouTube's Creator Partnerships API now**: invite-only, and Qoruz already has it in India | Both | Recommended | Next |
| D3 | **Proof that checks itself, then the results.** Links re-checked on days 1, 7 and 30 (D-024), then real reach on the actual post | Deal, delivery, payment and result, end to end; nobody holds all four | Job runner plus the same platform APIs. Signed photos (C2PA) are not ready: iPhones don't sign photos yet | Both | Proposed (D-024) | Next |
| D4 | **ID verified without holding anyone's Aadhaar** | Reelax hands out phone numbers; we verify and expose nothing | DigiLocker with masked Aadhaar and PAN, through a provider | Both | Blocked (validation pack) | Later |
| D5 | **Tamil voice everywhere** (A9) | Tamil as the interface | Sarvam, Bhashini | Adhi | Recommended | Next |
| D6 | **AI that helps both sides**: briefs for a bakery owner, pitches for a creator, every memo explained in plain Tamil. It shows the records it used and asks before acting | Every competitor's agent serves only the brand | Claude plus Sarvam, provider-agnostic (section 5.4) | Adhi | Recommended | Next |
| D7 | **Always the best model**: a Tamil test set scores every new model; we switch on the scores | Models change monthly; loyalty to one brand would leave us behind | Our own evaluation suite | Adhi | Recommended | Next |
| D8 | **Login with no code to type** (A5) | Faster, cheaper, SIM-swap resistant | Silent network authentication, WhatsApp code, SMS fallback, passkeys | Both (security) | Recommended | Next |
| D9 | **Works offline** (A6) | Built for patchy 4G | PowerSync | Both | Recommended | Later |
| D10 | **Deal status on the lock screen** (A3) | Nobody in this space does it | Live Activities, Live Updates | Frontend | Recommended | Later |
| D11 | **WhatsApp only where it counts** (D-022): alerts plus two one-tap replies | Tier 2 and 3 creators live in WhatsApp | WhatsApp Flows. About ₹0.115 per utility message; **from 1 October 2026 service replies are billed too**, so keep message counts low | Both | Decided (D-022) | Next |
| D12 | **Usable from inside ChatGPT and Claude** (W5) | Shopify and Square do this; nobody in the Indian creator space does | MCP Apps, built on existing endpoints such as `/me/attention` | Adhi | Recommended | Later |
| D13 | **A Passport that opens instantly** (A10, W1) | Shared on WhatsApp, scanned at a shop | App Clip, fast Next.js page | Frontend | Recommended | Later |
| D14 | **Truly native feel on each platform, tablets included** | What users expect from each phone | Liquid Glass on iOS (`@callstack/liquid-glass`, native APIs), Material 3 Expressive on Android; Android 17 requires large-screen support | Frontend | Recommended | Later |
| D15 | **DPDP-ready before the deadlines** | A selling point for brands; penalties go up to ₹250 crore | Consent-manager rules from **13 November 2026**; full compliance by **13 May 2027**. Details from the validation pack | Both | Blocked (validation pack) | Now |
| D16 | **Nothing we don't want**: no internet-wide creator database, no moving money, no star reviews, no fake-follower scores built without the creator's consent | Focus, and our constraints | — | — | Decided in spirit (constraint 1, D-034) | — |

---

## 4. Technology, layer by layer: what we run and what is current

Versions checked on 22 September 2026 with `pip index versions` and the projects' own release notes.

### 4.1 Backend runtime and libraries (API track; each change needs dependency approval, `CLAUDE.md` section 5)

| Item | We run | Current best | Why move | Status | When |
|---|---|---|---|---|---|
| Python | 3.12 | **3.14** (the standard build) | Faster, newer language features. **Not the free-threaded 3.14t yet:** libraries such as orjson silently turn the GIL back on | Recommended | Now, after the library upgrade |
| Packaging | pip + `requirements.txt` | **uv + `uv.lock`** | The same dependency graph everywhere; 10 to 100 times faster installs. Changes `CLAUDE.md` section 4 commands and CI, so both founders | Recommended | Now, with Python 3.14 |
| uvicorn | 0.30.6 | **0.53.0** | Two years of fixes | Recommended | Now |
| SQLAlchemy | 2.0.35 | **2.0.54**; **2.1** once released (rc2 now; native `uuidv7()` in batched inserts) | Fixes; 2.1 later | Recommended | Now; 2.1 Watch |
| Alembic | 1.13.2 | **1.20.0** | Fixes | Recommended | Now |
| psycopg | 3.2.1 | **3.3.6** | Fixes | Recommended | Now |
| pgvector (Python library) | 0.3.4 | **0.5.0** | halfvec and newer types | Recommended | Now |
| redis (Python client) | 5.0.8 | **8.1.0** | Current client | Recommended | Now |
| pydantic-settings | 2.5.2 | **2.15.0** | Fixes | Recommended | Now |
| slowapi | 0.1.9 | **0.1.10** | Fixes | Recommended | Now |
| httpx | 0.27.2 | **httpx2 2.13.0** | httpx is unmaintained; Starlette's test client warns until httpx2 is installed | Recommended | Now |
| coverage | unpinned | **7.16.1**, pinned | Carried debt: local and CI branch counts can differ | Recommended | Now |
| FastAPI, Starlette, PyJWT, pytest, ruff, mypy, pytest-cov | current | — | Already on the newest releases | — | — |

`alembic`, `sqlalchemy`, `psycopg` and `pgvector` are database libraries: Erode Harish reviews those upgrades on the PR.

### 4.2 Database and infrastructure (Data track and infrastructure; both founders)

| Item | We run | Current best | Why move | Status | When |
|---|---|---|---|---|---|
| PostgreSQL | **16.15** (`pgvector/pgvector:pg16`) | **18** now; **19** after its release and first minor update | 18: asynchronous I/O (up to 2 to 3 times faster reads), native `uuidv7()`, statistics kept across upgrades. 19 (beta since June): online `REPACK CONCURRENTLY`, parallel autovacuum | Recommended | Next |
| Primary keys | UUIDv4 (`gen_random_uuid()`) | **UUIDv7** for new tables | Time-ordered keys keep indexes compact and fast. Existing tables stay as they are | Recommended | Next, with Postgres 18 |
| Docker images | floating tags (`pg16`, `7-alpine`) | **Exact version tags** | The same database everywhere, and upgrades are visible in review | Recommended | Next |
| pgvector extension | not enabled yet; the image ships 0.8.6 | **Pin 0.8.2 or newer everywhere**, including hosting | CVE-2026-3172 (CVSS 8.1) affects 0.6.0 to 0.8.1. Also halfvec (half the memory) and iterative scans for city and niche filters | Recommended | Next, before matching |
| Embedding model | not chosen | Chosen by a **Tamil retrieval test**; candidates Qwen3-Embedding, gte-multilingual, Krutrim Vyakyarth. Stays on the approved SentenceTransformers + pgvector | Matching quality in Tamil | Recommended | Next (Phase D) |
| Cache and limits store | Redis 7 | **Valkey 9** (BSD licence, Linux Foundation, less memory), or Redis 8 (AGPL) | Open licence, faster; drop-in for our use | Recommended | Next |
| Background jobs | none | **DBOS**: durable jobs and workflows stored in Postgres, run inside our app, no new server. Alternatives: Procrastinate, Hatchet | Unblocks reminders, proof re-checks, WhatsApp retries. Fits the scale posture (no brokers) | Recommended | Next (job-runner decision) |
| Hosting | none | An India region: AWS Mumbai or Hyderabad support Postgres 18 with pgvector (RDS and Aurora). Compare with GCP and Azure before deciding | Latency for Tamil Nadu users | Recommended | Next (hosting decision) |

### 4.3 Frontend (Later; re-check every version when the frontend starts)

| Item | Current best today | Notes |
|---|---|---|
| Stack | **Proposed (D-046, option A): React Native with Expo for Android and iOS, Next.js for the website, TypeScript everywhere, one shared core** | The shared core holds the API client generated from `docs/api/openapi.json`, design tokens, Tamil and English text, and business rules |
| Website | **Next.js 16** (Cache Components, partial pre-rendering, Turbopack, React Compiler), React 19.2 | Expo's own web server rendering is still alpha, so Next.js runs the website |
| Apps | **Expo SDK 56** (React Native 0.85, React 19.2, New Architecture only, Hermes v1), Expo Router | `expo-widgets` for widgets and Live Activities; share extension; tus uploads |
| Offline | **PowerSync** | The only sync engine with first-class offline and React Native support |
| Design | Liquid Glass on iOS, Material 3 Expressive on Android, one token source | Performance, accessibility and Tamil rules are already in `docs/standards/frontend.md`; add iOS devices to its budgets |
| Deep links | Universal Links and App Links, plus a deferred deep-link provider | Section 2.3 |

### 4.4 AI

- **Provider-agnostic from day one.** Features call our own interface, never a vendor directly, so the best model can be swapped in without rewriting features.
- **Today's options:** Claude (Fable 5.1, Opus 5, Sonnet 5, Haiku 4.5) for reasoning and drafting; Sarvam (Saaras v3, Bulbul v3) for Tamil speech; Bhashini as a free fallback; Apple Foundation Models and Gemini Nano on the phone.
- **The Tamil test set decides** (D7). Scores are recorded and re-run monthly.
- **Rules that do not bend:** no personal data in embeddings (constraint 2); external calls retry with backoff and never block a request (`CLAUDE.md` section 3); the AI asks before acting; `ANTHROPIC_API_KEY` stays unused until an AI feature is approved.

---

## 5. Roadmap

### Now (backend, this week and next)

1. **Library upgrades (4.1)** on a branch, after a trial run of the full suite on the new versions. Needs dependency approval; `requirements.txt` is shared, so Erode Harish is told first.
2. **Python 3.14 and uv**, on a branch of its own. Needs both founders: it changes the commands in `CLAUDE.md` section 4, CI and both laptops.
3. **Validation pack**: DPDP retention and deletion, ASCI, GST/TDS. It now blocks the store launch (section 7).
4. **Erode Harish's review of PR #13**, so work reaches `main`.

### Next (backend, once each decision is made)

| Item | Needs |
|---|---|
| Postgres 18, exact image tags, UUIDv7 for new tables, pgvector pinned | Both founders; Data track |
| Valkey | Both founders; infrastructure |
| DBOS job runner, then proof re-checks (D3) and WhatsApp alerts (D11) | Job-runner decision; WhatsApp provider decision |
| Tamper-proof deal record (D1) and receipt check (W4) | A table (Data track) and a decision |
| Login without typing a code (D8), and real code delivery | Login provider decision (security) |
| Instagram and YouTube connections (D2); apply for YouTube's Creator Partnerships API | Both founders; consent and PII review |
| AI interface, Tamil test set, first AI features (D5 to D7) | AI provider decision |
| Device tokens for push (A4) | Data track table |
| Hosting in an India region | Hosting decision |
| Rate card (decision 1 of the rate card proposal) | Both founders |

### Later (frontend phase, D-004)

Everything in sections 2 and 4.3: the website, both apps, app-only and web-only features, deep links, offline, widgets, voice, App Clip.

### Watch (re-check monthly)

| Item | Adopt when |
|---|---|
| PostgreSQL 19 | Released, and its first minor update is out |
| SQLAlchemy 2.1 | Released as final |
| Free-threaded Python (3.14t, then 3.15) | Our dependencies support it without re-enabling the GIL |
| Expo web server rendering | Out of alpha; then reconsider one codebase for the website too |
| Gemini Nano on budget Android phones | Shipping on the phones Tamil Nadu creators actually use |
| C2PA signed photos on iPhone and mid-range Android | Enough phones sign captures to make it useful for proof |
| UPI links that open a UPI app with a personal UPI ID filled in | Tested on real phones with GPay, PhonePe and Paytm; NPCI rules changed in February 2026 |
| A new AI model | It beats the current one on our Tamil test set |

---

## 6. Decisions needed

| Decision | Who decides |
|---|---|
| D-046: three platforms, both roles on each, and the stack (option A) | Both founders |
| One role per phone number, or both roles with a switch | Both founders |
| Library upgrades in section 4.1 | Adhi; Erode Harish reviews the database libraries |
| Python 3.14 and uv | Both founders |
| Postgres 18, exact image tags, UUIDv7 for new tables | Both founders |
| Valkey or Redis 8 | Both founders |
| Job runner (DBOS recommended) | Both founders |
| Hosting | Both founders |
| Login provider: silent network authentication, WhatsApp, SMS | Both founders |
| AI provider and Tamil speech provider | Both founders |
| Instagram and YouTube connections | Both founders |
| Offline sync (PowerSync) and deferred deep links | Both founders, at the frontend phase |
| Rate card decision 1 | Both founders |

---

## 7. Warnings

- **Neither app can go into the stores without account deletion inside the app.** Apple requires it (App Store Review Guideline 5.1.1(v)); Google Play requires it in the app **and** through a web link (enforced since April 2024). Deactivating an account does not count. Ours waits on the validation pack, which makes the validation pack a launch blocker.
- **Nobody can log in outside a developer's laptop yet.** No SMS or WhatsApp provider is chosen, so login codes cannot be delivered (the fake sender refuses outside local and test).
- **WhatsApp:** service replies inside the 24-hour window are billed from **1 October 2026**.
- **DPDP:** consent-manager rules from **13 November 2026**; everything else by **13 May 2027**.
- **pgvector:** never deploy 0.6.0 to 0.8.1 (CVE-2026-3172). Pin the version everywhere.
- **"Pay via UPI" with a creator's UPI ID filled in is unconfirmed.** It would keep money moving directly from brand to creator (constraint 1 holds), but whether UPI apps accept such links for personal UPI IDs has to be tested on real phones before it is proposed.

---

## 8. What changes elsewhere once D-046 is decided

- `CLAUDE.md` section 1: the platform line.
- `docs/standards/frontend.md`: platforms, iOS devices in the performance budgets, the app size budget, and the web/app split.
- `docs/FRONTEND_BLUEPRINT_MAPPING.md`: screens for both roles on all three platforms.
- `docs/COMPETITIVE_LANDSCAPE.md`: point section 6 at section 3 of this plan.

---

## 9. Keeping it current

- **Monthly review:**
  - Latest release of every dependency (`pip index versions`, later `npm outdated`).
  - Security advisories (`pip-audit` already runs in CI).
  - The Tamil model test set.
  - The Watch list.
  - Then update the "last checked" date at the top of this file.
- **Dependabot alerts and secret scanning** stay on (`docs/standards/security.md` section 8).
- **Any upgrade still goes through its approval gate.** "Current" never skips review.

---

## Sources

Market and competitors: [AI agents in influencer marketing 2026](https://influencermarketinghub.com/best-ai-agents-for-influencer-marketing/) · [Reelax AI vetting](https://theprint.in/ani-press-releases/reelax-influencer-marketing-platform-is-using-ai-and-automation-to-fix-indias-influencer-marketing-bottlenecks/3016922/) · [YouTube Creator Partnerships](https://blog.youtube/news-and-events/youtube-creator-partnerships-newfronts-2026/) · [YouTube Creator Partnerships API in India via Qoruz](https://www.netinfluencer.com/youtube-creator-partnerships-api-comes-to-india-through-qoruz-integration/) · [Regional creators in India](https://www.deccanchronicle.com/amp/business/indias-influencer-marketing-boom-industry-nears-5000-crore-as-regional-creators-rise-1970876)

Web and app: [Web-to-app benchmarks 2026](https://www.businessofapps.com/data/web-to-app-benchmarks/) · [Apps vs mobile websites](https://www.mobiloud.com/blog/mobile-apps-vs-mobile-websites) · [App download and uninstall statistics](https://meetanshi.com/blog/mobile-app-download-statistics/) · [Google Play app size](https://support.google.com/googleplay/android-developer/answer/9859372?hl=en) · [Google on interstitials](https://developers.google.com/search/docs/appearance/avoid-intrusive-interstitials) · [Firebase Dynamic Links FAQ](https://firebase.google.com/support/dynamic-links-faq) · [PWA limits on iOS](https://www.magicbell.com/blog/pwa-ios-limitations-safari-support-complete-guide) · [App Clips and Instant Apps in 2026](https://www.dualmedia.fr/en/app-clips-instant-apps/) · [Generative engine optimisation](https://aisearch.similarweb.com/blog/what-is-geo/)

Mobile and web technology: [Expo SDK 56 and React Native 0.85](https://medium.com/@dinesh.kachhot/the-react-native-ecosystem-in-mid-2026-expo-sdk-56-react-native-0-85-and-react-19-2-59919e4d76c5) · [Expo widgets and Live Activities](https://expo.dev/blog/home-screen-widgets-and-live-activities-in-expo) · [expo-share-intent](https://www.npmjs.com/package/expo-share-intent) · [Expo video uploads](https://expo.dev/blog/faster-more-reliable-video-uploads-with-expo-modules) · [Expo Router server rendering](https://docs.expo.dev/router/web/server-rendering/) · [Next.js 16](https://nextjs.org/blog/next-16) · [Android 16 Live Updates](https://www.androidauthority.com/android-16-live-notifications-3518375/) · [Android 17](https://android-developers.googleblog.com/2026/06/Android-17.html) · [Liquid Glass in React Native](https://www.callstack.com/blog/how-to-use-liquid-glass-in-react-native) · [Offline-first React Native 2026](https://procedure.tech/blogs/react-native-offline-first/)

AI: [Apple Foundation Models: any LLM provider (WWDC26)](https://developer.apple.com/videos/play/wwdc2026/339/) · [Android AI at Google I/O 2026](https://android-developers.googleblog.com/2026/05/android-ai-intelligence-system.html) · [Sarvam Tamil speech to text](https://www.sarvam.ai/apis/speech-to-text/tamil) · [Sarvam text to speech](https://www.sarvam.ai/text-to-speech) · [Bhashini](https://en.wikipedia.org/wiki/Bhashini) · [September 2026 model releases](https://www.digitalapplied.com/blog/ai-model-releases-september-2026-tracker) · [MCP in 2026](https://truthifi.com/education/state-of-mcp-2026-ai-agents-custom-connectors) · [Open-source embedding models 2026](https://www.bentoml.com/blog/a-guide-to-open-source-embedding-models)

India rails and rules: [Silent network authentication](https://otpless.com/products/silent-network-auth) · [Passkeys in India](https://www.corbado.com/blog/passkeys-india-overview) · [Instagram Graph API 2026](https://elfsight.com/blog/instagram-graph-api-complete-developer-guide-for-2026/) · [WhatsApp pricing from 1 October 2026](https://www.courier.com/blog/whatsapp-pricing-changes-october-2026) · [DPDP Rules timeline](https://www.sansalegal.com/post/dpdp-act-2023-and-rules-2025-phased-implementation-timeline-and-business-compliance-deadlines) · [DigiLocker KYC](https://www.befisc.com/fintechsherlock/digilocker-kyc-verification-india/) · [UPI Collect limited from 28 February 2026](https://www.stackumbrella.com/technology/upi-collect-being-limited-from-feb-28-2026-what-it-means-for-google-pay-and-phonepe-users-11176663) · [Apple account deletion](https://developer.apple.com/news/?id=12m75xbj) · [Google Play account deletion](https://support.google.com/googleplay/android-developer/answer/13327111?hl=en) · [C2PA adoption 2026](https://editorsweblog.org/2026/04/12/c2pa-adoption-tracker-platforms-content-credentials-2026)

Backend and database: [PostgreSQL 18](https://postgresql.org/about/news/postgresql-18-released-3142/) · [PostgreSQL 19 Beta 1](https://www.postgresql.org/about/news/postgresql-19-beta-1-released-3313/) · [pgvector indexes 2026](https://www.dbi-services.com/blog/pgvector-a-guide-for-dba-part-2-indexes-update-march-2026/) · [CVE-2026-3172](https://www.sentinelone.com/vulnerability-database/cve-2026-3172/) · [Valkey vs Redis 2026](https://betterstack.com/community/comparisons/redis-vs-valkey/) · [SQLAlchemy 2.1](https://www.sqlalchemy.org/docs/21/changelog/migration_21.html) · [httpx2 in Starlette](https://github.com/Kludex/starlette/pull/3291) · [FastAPI free-threaded support](https://github.com/fastapi/fastapi/pull/15149) · [uv](https://github.com/astral-sh/uv) · [DBOS](https://github.com/dbos-inc/dbos-transact-py) · [Amazon RDS PostgreSQL 18](https://aws.amazon.com/about-aws/whats-new/2025/11/amazon-rds-postgresql-major-version-18/)
