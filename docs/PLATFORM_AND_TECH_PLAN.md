# Platform and technology plan

**What this is:** one place for what we build on each platform, how we stand apart from every competitor, and which technology every layer should use, with what starts now and what comes later. Written 22 September 2026 by Adhi's session from web research done that day. Sources are listed at the end.

**Last checked against current releases: 22 September 2026**, in two passes: the whole plan in the morning, then two deeper passes the same day: the website/app split (section 2), and every technology layer again, including tooling, testing, observability and the CI supply chain (section 4). Sections 3, 5, 6 and 7 were brought up to date with them. Re-check monthly (section 9). In this field a plan older than a month is already behind.

**Nothing here overrides `CLAUDE.md`.** Every item still goes through its approval gate. The constraints hold throughout: we never hold or move money, no personal data in embeddings, and compliance details come from the validation pack, never from research like this.

**Status words used below**

| Word | Meaning |
|---|---|
| **Decided** | Recorded in `docs/DECISIONS.md` |
| **Proposed** | A founder's direction or a written proposal, waiting for the approval it needs |
| **Recommended** | Claude's recommendation; nobody has decided yet |
| **Blocked** | Waiting on the validation pack or another decision |
| **Locked** | Chosen as what we use (D-047). Still built through its approval gate, on its own branch |

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

*Deepened the same day (22 September 2026) after Adhi asked for more research on how the two should differ: "if both have all features, people will not download the app".*

### 2.0 What the evidence says

| Finding | What it means for us |
|---|---|
| Apps keep people about 1.6 times better than the mobile web (32% against 20% at 90 days) and convert 2 to 4 times better. People spend about 94% of their phone time inside apps | Regular use happens in the app, so the app deserves real effort |
| 56% of apps are uninstalled within 7 days, mostly to free storage. Every extra 6 MB of download costs about 1% of installs | The app must stay small and earn its place in the first week |
| **Myntra shut its website in May 2015 to go app-only. Sales fell about 10%, and it relaunched the website on 1 June 2016.** People wanted to compare on a big screen, and first-time users trusted the website more | Never force the app. Anything you can see in the app you can also see on the website |
| Google ranks mobile pages lower when a full-screen "install the app" wall hides the content | A wall would also damage W1, the way new people find us |
| India is 92 to 95% Android; iPhone is about 7.5% (July 2026) | App-only features are built for Android first. iPhone gets them too, but Android sets the order |
| Upwork: the desktop is for heavy work, the phone app for quick replies. Instagram: creators handle brand deals in the app (Partnership Messages), while brands work in a desktop hub (Meta Creator Marketing Hub, worldwide since 16 September 2026) | The biggest marketplaces already split the work by device. We copy the split, not their features |

### 2.1 The rule

**The website is the front door and the desk. The app is the pocket. Each one also plugs into the AI assistant that lives on that device.**

| | Website | App |
|---|---|---|
| Its job | Being found, and desk work: bulk, side by side, on a big screen | In-the-moment work: capture, alerts, voice, offline, instant login |
| Used most by | Brands at a desk; anyone arriving from a link or a search | Creators all day; brand owners on the move |
| AI assistant it plugs into | Browser agents (Gemini in Chrome, through WebMCP) and ChatGPT or Claude (through MCP Apps) | The phone's own assistant: Gemini on Android (understands Tamil), Siri on iPhone |
| AI that runs on the device | Chrome's built-in Gemini Nano, on computers with a strong enough graphics card | Gemini Nano on recent flagship Android phones; Apple's on-device model on iPhone |

**Where a new feature goes: four questions, in order.**

1. Does it need something only a phone can do (camera, share sheet, lock screen, SIM, fingerprint, working offline)? → **App.**
2. Is it done in bulk, side by side, or read closely on a big screen? → **Website** (the app still shows the result).
3. Must anyone reach it from a link or a search, without an account? → **Website** (the app opens the same link when installed).
4. Otherwise → **both**, in the shape that suits each device (section 2.4).

"Only" is about *doing* a task. Everyone can *see* everything on both.

### 2.2 Only in the app

✅ only possible in an app · ◐ possible on the web, but only done properly in the app

| # | Feature | Why it matters | Technology | When |
|---|---|---|---|---|
| A1 | ✅ **Share a post from Instagram straight into NicheConnect as proof** | Proof in two taps, no copying links | Share extension (`expo-share-intent`) | Later |
| A2 | ✅ **Share the UPI receipt; the reference fills itself in; the payment is marked sent** | "Mark paid" becomes one tap after paying. We still never touch the money | On-device text recognition reads the UTR. **Needs testing** across UPI apps' receipt formats | Later |
| A3 | ✅ **Deal status on the lock screen and home screen**: "₹12,000 due to you, 2 days" | Nobody in this space has it | iOS Live Activities, Android Live Updates (Android 16 QPR1 and later), `expo-widgets` | Later |
| A4 | ✅ **Alerts that arrive.** On iPhone, web notifications only work once a site is added to the home screen | The app is the real-time channel; WhatsApp is the fallback for everyone | Push through FCM/APNs; backend stores device tokens (Data track) | Next (backend), Later (app) |
| A5 | ✅ **Login with no code to type**: the carrier confirms the SIM, then Face ID or fingerprint | Two-second login, safe from SIM-swap | Silent network authentication (Jio and Vi today through OTPless; Airtel in talks), then passkeys | Next (decision), Later (app) |
| A6 | ✅ **Works offline**: read memos, draft pitches, queue proof on patchy 4G | iOS web cannot sync in the background | PowerSync (local SQLite synced with Postgres) plus our retry-safe API (D-040) | Later |
| A7 | ✅ **Private AI on the phone**: proofread a pitch or summarise a memo without internet | Nothing leaves the phone | Apple Foundation Models (iOS 27: AFM 3, and any provider can plug in through its `LanguageModel` protocol), Gemini Nano on Android. **Two limits: most budget Android phones lack Gemini Nano, and Apple has not announced Tamil for Apple Intelligence. The cloud path stays the main one, and on-device AI is English-first for now** | Later |
| A8 | ✅ **Uploads that survive app kills and bad networks**, compressed on the phone (D-024) | No lost work | Resumable (tus) background upload | Later |
| A9 | ◐ **Speak in Tamil or Tanglish**: pitches, briefs and replies by voice; memos read aloud | Tamil as the interface, not a filter | Sarvam Saaras v3 (speech to text, code-mixing), Bulbul V4 (July 2026: Tamil voices with emotion and emphasis); Bhashini as a free fallback | Next (backend), Later (app) |
| A10 | ✅ **Scan a shop's QR and apply at once on iPhone** | Offline to online in Tamil Nadu towns | App Clip. Android Instant Apps shut down in December 2025, so Android opens the website | Later |
| A11 | ✅ **Ask the phone's assistant**: "Gemini, has Chennai Bakes paid me?", "what's my next deadline?" The answer comes from our data, with a link into the app | Nobody in this space answers inside the phone's assistant. **Android first, because Gemini understands Tamil.** On iPhone, Siri's new AI speaks English and a few other languages in India today; Tamil is not announced | Android AppFunctions (Android 17; apps become tools Gemini can call; Gemini integration in private preview, early-access programme open). App Intents on iOS 27 (now the only way into Siri; SiriKit is being retired). Both call our existing API, such as `/me/attention` | Watch; Later |
| A12 | ✅ **Act on an alert without opening the app**: approve a draft, accept a memo change, confirm "payment received" | One tap from the lock screen | Notification actions, Live Updates, Live Activities | Later |
| A13 | ✅ **Home-screen widget: "what needs me today"**, and money due | Both roles see it at a glance | `expo-widgets`; Jetpack Glance on Android; reads `/me/attention` | Later |
| A14 | ◐ **Share an Instagram Insights screenshot; the numbers fill themselves in**, labelled "from the creator's screenshot" | For creators who can't or won't connect their account (Instagram's API needs a Business or Creator account). A screenshot can be edited, so it always ranks below "Verified by Instagram" (D2) | On-device text recognition through the share sheet | Later |
| A15 | ◐ **Confirm big steps with a fingerprint or Face ID**: accepting a memo, marking a payment sent | Hard to fake, one second | Passkey user verification. **Security gate** | Later |
| A16 | ◐ **Free, instant alerts for new campaigns in my city** | A push costs nothing; each WhatsApp utility message costs about ₹0.115, and service replies are billed too from 1 October 2026. Uses the city on the creator's profile, **never GPS tracking** | Push (A4). Campaigns have no city today: **needs a column (Data track) and a decision** | Next (decision), Later |

### 2.3 Only on the website

| # | Feature | Why it matters | Technology, or what it needs | When |
|---|---|---|---|---|
| W1 | **Public Creator Passports, and pages like "food creators in Madurai"**, fast and indexed | How new people find us. Google's AI Mode only cites pages that rank in Google, and tables of facts are among the most cited formats | Server-rendered pages from the existing Passport API | Later (pages); the Passport API already exists |
| W2 | **The brand desk**: compare 50 applicants side by side, a campaign builder with preview, bulk "mark paid" from a bank CSV (D-043), reports | Desk work belongs on a desk | Existing endpoints | Later |
| W3 | **Start without installing**: a first application or a first campaign from a WhatsApp link | No friction first; the app afterwards | Existing endpoints | Later |
| W4 | **Deal receipt check**: anyone scans a receipt's QR and verifies it in a browser, with no account | Trust that works outside our platform (see D1) | The signed deal record (D1) and a public check page | Next (backend), Later (page) |
| W5 | **AI agents and agencies**: run NicheConnect from inside ChatGPT or Claude; later a public API | A new way in | MCP Apps, which now work inside both (ChatGPT calls them plugins since July 2026) | Later |
| W6 | **Account deletion link and privacy rights page** | Google Play requires the web link (section 7) | A web page on the existing account endpoints | Blocked (validation pack) |
| W7 | **A website AI agents can use properly**: a brand's browser agent (such as Gemini in Chrome's auto browse) creates a campaign or shortlists applicants through tools we declare, instead of guessing where to click | We would be the first creator marketplace in India ready for browser agents. Expedia, Booking.com, Shopify and Etsy are trying it | WebMCP: an origin trial in Chrome 149 (from May 2026); Chrome and Edge support expected in the second half of 2026. It calls the same API underneath | Watch; Later |
| W8 | **Private AI on the brand's computer**: draft or tidy a brief without it leaving the machine | Privacy that brands can see | Chrome's Prompt API (stable in Chrome 148) with Gemini Nano. **Only on computers with a 4 GB graphics card and about 22 GB of free disk, and not in Chrome on phones**, so the cloud path stays the main one | Later |
| W9 | **Embeds**: a "Work with me" card creators put in their link-in-bio, and a "Creators we've worked with" strip for a brand's own website | Every embed links back to a Passport, which feeds W1 | Public Passport data only; the consent rules (D-036) still apply | Later |
| W10 | **Draft review desk**: the brand watches a draft reel and pins comments to exact seconds; the creator answers on the phone | Reviewing video is desk work; creators live on their phones | A decision on storing draft videos (cost; retention from the validation pack) | Recommended; Later |
| W11 | **Team seats for brands and agencies**: owner, marketer, accounts person; the accounts person marks payments sent | Real businesses have more than one person | Today one phone number is one account (D-014). **New tables (Data track), a security review, both founders** | Recommended; Next (decision) |
| W12 | **Exports for accountants**: deal receipts as PDF, payments as a spreadsheet | Brands close their books on a computer | GST and TDS fields come only from the validation pack | Blocked (validation pack) |

### 2.4 The same feature, shaped for each device

| Feature | In the app | On the website |
|---|---|---|
| Log in | SIM check, then fingerprint or Face ID (A5) | Passkey (Chrome now shows passwords and passkeys in one sign-in prompt), WhatsApp or SMS code as fallback |
| Mark a payment sent | Share the UPI receipt; the reference fills itself in (A2) | Upload the bank CSV and mark many at once (D-043) |
| Proof of a post | Share it from Instagram (A1) | Paste the link |
| Alerts | Push, lock screen, widget, act from the alert (A3, A4, A12, A13) | WhatsApp for the events that matter (D-022), and email |
| Tamil | Speak and listen (A9) | Type in Tamil or Tanglish; memos read aloud |
| AI | On the phone where it can run, plus the phone's assistant (A7, A11) | On the computer where it can run, plus browser agents and ChatGPT or Claude (W5, W7, W8) |
| Creator Passport | Show its QR at a shop or event; App Clip on iPhone (A10) | A fast public page found by search and AI search (W1), and embeds (W9) |
| Applicants | Quick yes, no or shortlist on the move | Compare 50 side by side (W2) |

### 2.5 Worth installing, never walled

The app earns its install from what a phone does better. Nothing is taken away from the website to force it.

**Recommended (both founders decide):**

- People with the app get the phone-only features in section 2.2. People on the website get every piece of data and every action, without those conveniences.
- People without the app get WhatsApp alerts only for the events that matter (D-022), because each message costs money. That makes the app the natural home for alerts, without punishing anyone.

**Recommended against:**

| Idea | Why not |
|---|---|
| A full-screen "install the app" wall | Myntra's lesson, and Google ranks such pages lower |
| New campaigns shown to app users first | It penalises creators whose phones are too full for another app, shrinks brands' applicant pool, and fairness is what we sell |
| App-only prices or discounts | We never touch the money (constraint 1), so there is nothing to discount |

### 2.6 The bridge between them

- **Offer the app at the right moment, never with a wall:** a small, dismissible banner (Safari Smart App Banner, or our own small bar), shown after something the app does better. Examples: after an application is sent ("get told the moment they reply"), or after a memo is accepted ("see your payment clock on your lock screen").
- **Don't offer the app to someone who has it.** On Android, Chrome can check (`getInstalledRelatedApps`), and the banner becomes "Open in the app".
- **The app opens on the exact thing the person was looking at**, even straight after install ("deferred deep linking"). Firebase Dynamic Links shut down on 25 August 2025, so this needs a provider: AppsFlyer OneLink, Branch, Airbridge, ChottuLink (free up to 25,000 monthly users) or self-hosted. **Decision later.**
- **App size budget (Recommended): under 30 MB download on Android**, tracked every release. Android App Bundles, Hermes bytecode, and heavy assets fetched only when needed.

### 2.7 What this asks of the backend, before any frontend

| Item | Why | Owner | Needs |
|---|---|---|---|
| **Login codes sent by SMS use Android's SMS Retriever format (with the app's hash) and the web one-time-code line** (`@<our domain> #123456`) | **Android 17 holds back ordinary SMS messages containing a code for three hours** from apps that target it. Only these formats fill in by themselves, on the app and on the website | Adhi | Part of the login provider decision; the domain is not chosen yet |
| **Device tokens record their kind**: Android, iPhone, iPhone Live Activity | Live Activities get their own push tokens (A3, A4) | Erode Harish | The device tokens table (A4) and its decision |
| **One API behind every assistant** | App Intents, AppFunctions, WebMCP and MCP all call our existing endpoints, so there is nothing separate to build per assistant. Agents will need their own tokens with limited permissions | Adhi | Security gate, when the first assistant feature is approved |

---

## 3. How we stand clear of every competitor

The market in September 2026: discovery is free inside Instagram and YouTube. Paid platforms race on AI agents that work for brands (GRIN, Upfluence, Passionfroot, Agentio, TikTok Symphony) and on AI fake-follower screening (Reelax). **Their AI works for the brand, speaks English first, and estimates. Nobody owns the truth of the deal, Tamil as the product's language, or working well on a ₹10,000 phone.** The full competitor list is in `docs/COMPETITIVE_LANDSCAPE.md`.

**New since that list (16 September 2026):** Meta merged Creator Marketplace and Partnership Ads Hub into one **Meta Creator Marketing Hub**, now worldwide. It adds content permissions with expiry dates, brand–creator messaging and a Messaging API, and brings Facebook creators in. Meta is moving towards the deal (usage rights), but it still keeps no record of delivery or payment. Watch it at every monthly review.

| # | Differentiator | Why nobody else can match it | Technology | Owner | Status | When |
|---|---|---|---|---|---|---|
| D1 | **Tamper-proof deal record.** Every memo, proof, payment and dispute event is chained; each side can download a signed deal receipt with a QR anyone can check | Our records become evidence, not a claim | SHA-256 hash chain in Postgres plus Ed25519 signatures. No new vendor | Harish (table), Adhi (API) | Recommended | Next |
| D2 | **Verified audience instead of self-reported numbers.** The creator connects Instagram or YouTube; the Passport says "Verified by Instagram, as of <date>" | First-party numbers beat AI estimates | Instagram Graph API (Business/Creator accounts, `instagram_manage_insights`, creator's consent); YouTube Analytics API. **Apply for YouTube's Creator Partnerships API now**: invite-only, and Qoruz already has it in India | Both | Recommended | Next |
| D3 | **Proof that checks itself, then the results.** Links re-checked on days 1, 7 and 30 (D-024), then real reach on the actual post | Deal, delivery, payment and result, end to end; nobody holds all four | Job runner plus the same platform APIs. Signed photos (C2PA) are not ready: iPhones don't sign photos yet | Both | Proposed (D-024) | Next |
| D4 | **ID verified without holding anyone's Aadhaar** | Reelax hands out phone numbers; we verify and expose nothing | DigiLocker with masked Aadhaar and PAN, through a provider | Both | Blocked (validation pack) | Later |
| D5 | **Tamil voice everywhere** (A9) | Tamil as the interface | Sarvam, Bhashini | Adhi | Recommended | Next |
| D6 | **AI that helps both sides**: briefs for a bakery owner, pitches for a creator, every memo explained in plain Tamil. It shows the records it used and asks before acting | Every competitor's agent serves only the brand | Claude plus Sarvam, provider-agnostic (section 4.4) | Adhi | Recommended | Next |
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
| D17 | **Answers inside the phone's assistant** (A11): ask Gemini, in Tamil, whether you've been paid | Nobody in this space has done it; Android 17 has only just made it possible | Android AppFunctions, then App Intents on iPhone | Frontend; Adhi (API) | Recommended | Watch; Later |
| D18 | **A website AI agents can use** (W7) | We would be first in the Indian creator space | WebMCP, on the same API | Frontend; Adhi (API) | Recommended | Watch; Later |

---

## 4. Technology, layer by layer: what we run and what is current

Versions checked on 22 September 2026 with `pip index versions` and the projects' own release notes. A second pass the same day covered every layer again (Adhi: "backend, frontend, database, everything"), and added the tooling, testing, observability and supply-chain layers in section 4.5.

**How to read "best" here:** the newest release is not automatically the best. The best option is the one that is current, maintained and proven for our workload. Where the newest option is still beta, or a benchmark win disappears on an API that waits on the database, the table says so. It goes on the Watch list rather than straight into the code.

### 4.0 The baseline: what we use (D-047)

Locked by both founders on 22 September 2026 (D-047; Erode Harish's approval relayed by Adhi). A baseline item changes only through the upgrade rule in section 9. "Locked" means chosen, not installed: each item is still built on its own branch, through its approval gate.

| Layer | What we use | Status |
|---|---|---|
| Backend libraries | The "current best" versions in 4.1, including httpx2 | **Locked** (Erode Harish reviews the database libraries on the PR) |
| Backend tools | mypy (strict), ruff, pytest, uvicorn | **Locked** (kept; ty, Pyrefly and Granian on the Watch list) |
| API fuzz testing | Schemathesis 4.x | **Locked** (Erode Harish told first: `requirements.txt` is shared) |
| CI supply chain | Current action versions, pinned to commit SHAs, and zizmor | **Locked** (Adhi's track: `.github/workflows/`) |
| Errors and traces | Sentry for errors (already in `docs/standards/backend.md`); OpenTelemetry for traces | **Locked**; where traces go waits on hosting |
| Python and packaging | Python 3.14; uv | **Locked** |
| Database | PostgreSQL 18 (19 after its first minor update); UUIDv7 for new tables; exact image tags; pgvector 0.8.2 or newer | **Locked** |
| Search | Hybrid Tamil search inside Postgres: built-in `tamil` and `english` stemmers, `pg_trgm`, pgvector | **Locked**; built after a test with real Tamil queries |
| Migration safety | Squawk | **Locked** |
| Cache and rate limits | Valkey 9.1.2 or newer | **Locked**; **built** 23 September (D-048) |
| Background jobs | DBOS | **Locked**; installed with the first background job |
| AI | Pydantic AI v2 as our interface; Claude (Opus 5 as the default) and Sarvam for Tamil speech; each model chosen by the Tamil test set, run with promptfoo | **Locked**; installed with the first approved AI feature |
| Frontend | The stack in 4.3: Expo SDK 57, Next.js 16.3.6 or newer, TypeScript 7, Expo UI, Tailwind v4 with shadcn/ui, NativeWind, PowerSync, Playwright, Maestro | **Locked**; every version re-checked when the frontend starts. D-046 (platforms and roles) is separate |
| Not locked yet | Hosting, where traces go, the login provider, the lint tool (Biome or Oxlint), the API client generator (Hey API or Orval), the Tamil fonts (chosen by testing) | Open |

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
| httpx | 0.27.2 | **httpx2 2.13.0** | httpx is unmaintained; Starlette's test client warns until httpx2 is installed. Anthropic's Python SDK 1.x is also built on httpx2 | Recommended | Now |
| coverage | unpinned | **7.16.1**, pinned | Carried debt: local and CI branch counts can differ | Recommended | Now |
| FastAPI, Starlette, PyJWT, pytest, ruff, mypy, pytest-cov | current | — | Already on the newest releases | — | — |
| Type checker | mypy (strict, D-037) | **mypy stays.** Watch **ty** (Astral, 10 to 60 times faster, still beta; Astral is now part of OpenAI) and **Pyrefly** (Meta, closer to the typing rules today) | Neither has reached 1.0; strict mypy already gates CI | — | Watch |
| Web server | uvicorn | **uvicorn stays** (upgrade above). **Granian** (written in Rust) wins raw benchmarks, but for an API that waits on the database the gain is often within 10% | Measure with our own load test before switching | — | Watch |
| AI framework | none | **Pydantic AI v2** (23 June 2026) as our provider-agnostic AI layer (section 4.4), or a thin interface of our own | Typed, from the team behind Pydantic, which FastAPI already runs on | Recommended | Next (with the AI provider decision) |

`alembic`, `sqlalchemy`, `psycopg` and `pgvector` are database libraries: Erode Harish reviews those upgrades on the PR.

### 4.2 Database and infrastructure (Data track and infrastructure; both founders)

| Item | We run | Current best | Why move | Status | When |
|---|---|---|---|---|---|
| PostgreSQL | **16.15** (`pgvector/pgvector:pg16`; the newest 16.x) | **18** now (18.6 is its newest minor); **19** after release and its first minor update. 19 Beta 4 is due 24 September; the final release is targeted for the end of October 2026 | 18: asynchronous I/O (up to 2 to 3 times faster reads), native `uuidv7()`, statistics kept across upgrades. 19: online `REPACK CONCURRENTLY`, parallel autovacuum | Recommended | Next |
| Primary keys | UUIDv4 (`gen_random_uuid()`) | **UUIDv7** for new tables | Time-ordered keys keep indexes compact and fast. Existing tables stay as they are | Recommended | Next, with Postgres 18 |
| Docker images | floating tags (`pg16`, `7-alpine`) | **Exact version tags** | The same database everywhere, and upgrades are visible in review | Recommended | Next |
| pgvector extension | not enabled yet; the image ships 0.8.6 | **Pin 0.8.2 or newer everywhere**, including hosting | CVE-2026-3172 (CVSS 8.1) affects 0.6.0 to 0.8.1. Also halfvec (half the memory) and iterative scans for city and niche filters | Recommended | Next, before matching |
| Vector index engine | — | **pgvector** at our scale (far below 10 million vectors). VectorChord inserts and queries faster at large scale | Nothing to gain yet; revisit if matching grows | — | Watch |
| Embedding model | not chosen | Chosen by a **Tamil retrieval test**; candidates Qwen3-Embedding, gte-multilingual, Krutrim Vyakyarth. Stays on the approved SentenceTransformers + pgvector | Matching quality in Tamil | Recommended | Next (Phase D) |
| **Search in Tamil** | none | **Hybrid search inside Postgres, with no new service:** Postgres's built-in `tamil` and `english` stemmers for words, `pg_trgm` for spelling slips and Tanglish typed in English letters, and pgvector for meaning. **ParadeDB `pg_search`** (BM25 ranking, ICU tokenizer) only if ranking quality needs it | Brands must find "Madurai food creator" whether they type it in Tamil, English or Tanglish. Competitors filter by language; we would search in it | Recommended | Next (after a test with real Tamil queries) |
| Migration safety | Alembic; CI checks every downgrade | **Add Squawk**: lints the SQL of each migration for table locks and downtime before it merges (works with Alembic's offline SQL) | Catches the migration that would lock a busy table in production | Recommended | Next (Data track) |
| Cache and limits store | **Valkey 9.1.2** (`valkey/valkey:9.1.2-alpine`, exact tag) | Current | Open licence, faster; it was a drop-in, and nothing in the application changed | **Built** (D-048, 23 September) | Done |
| Background jobs | none | **DBOS**: durable jobs and workflows stored in Postgres, run inside our app, no new server. Alternatives: Procrastinate, Hatchet | Unblocks reminders, proof re-checks, WhatsApp retries. Fits the scale posture (no brokers) | Recommended | Next (job-runner decision) |
| Hosting | none | An India region. **AWS Mumbai or Hyderabad** run Postgres 18 with pgvector (RDS and Aurora); **Supabase** has a Mumbai region; **Neon has no India region**. Compare with GCP and Azure before deciding | Latency for Tamil Nadu users | Recommended | Next (hosting decision) |
| Edge and files | none | A CDN with a **Chennai** point of presence (Cloudflare has one) for the website, Passport pages and images | Pages and photos load from Chennai, not Mumbai or Singapore | Recommended | Later (with the website) |

### 4.3 Frontend (Later; re-check every version when the frontend starts)

| Item | Current best today | Notes |
|---|---|---|
| Stack | **Proposed (D-046, option A): React Native with Expo for Android and iOS, Next.js for the website, TypeScript everywhere, one shared core** | The shared core holds the API client generated from `docs/api/openapi.json`, design tokens, Tamil and English text, and business rules |
| Language | **TypeScript 7.0** (8 July 2026): the compiler rewritten in Go, builds 8 to 12 times faster | Its programmatic API arrives in 7.1, so some tools may lag for a while |
| Website | **Next.js 16.3** (Cache Components, partial pre-rendering, Turbopack, React Compiler), React 19.2. **16.3.6 or newer only:** a critical security release came out on 22 September 2026 | Expo's own web server rendering is still alpha, so Next.js runs the website |
| Apps | **Expo SDK 57** (released 30 June 2026: React Native 0.86, React 19.2, New Architecture only, Hermes v1, no breaking changes from SDK 56), Expo Router | `expo-widgets` for widgets and Live Activities (stable since SDK 56); share extension; tus uploads. Expo is moving to small, non-breaking releases between the big SDKs |
| Native look | **Expo UI** (stable since SDK 56): real SwiftUI on iPhone and real Jetpack Compose on Android, from one import | This is how we get genuine Liquid Glass and Material 3 Expressive (D14), not imitations of them |
| Styling and components | Website: **Tailwind CSS v4** with **shadcn/ui** (new projects now built on Base UI). Apps: **NativeWind** (Tailwind classes for React Native) | The same class names and design tokens on both |
| API client | Generated from `docs/api/openapi.json`: **Hey API (`openapi-ts`)** with its TanStack Query plugin, or **Orval** (hooks and mocks built in) | The clients can never drift from what the backend really answers (the contract tests already guard that side) |
| Offline | **PowerSync** | The only sync engine with first-class offline and React Native support |
| Lint and format | **Biome** (lint and format in one tool) or **Oxlint** (the fastest linter) | Both are many times faster than ESLint; pick one at the frontend start |
| Testing | **Playwright** for the website; **Maestro** for the apps (works with Expo and EAS builds) | Detox runs each test faster but is harder to set up |
| Tamil fonts | Candidates: **Noto Sans Tamil UI** (made for app and web interfaces), **Anek Tamil** (variable), **Hind Madurai** (made for screens). Chosen by testing with Tamil readers on budget phones | `docs/standards/frontend.md` already requires full Tamil glyph support |
| Design | Liquid Glass on iOS, Material 3 Expressive on Android, one token source | Performance, accessibility and Tamil rules are already in `docs/standards/frontend.md`; add iOS devices to its budgets |
| Performance | The budgets in `docs/standards/frontend.md` section 3, for example a usable screen within 2.5 s of a cold start on a mid-range Android; the app download under 30 MB (section 2.6) | Measured by tools on real budget phones, never estimated |
| Deep links | Universal Links and App Links, plus a deferred deep-link provider | Section 2.6 |
| Assistants | Android AppFunctions (Jetpack library, alpha) and App Intents on iOS 27 | Section 2.2, A11 |

### 4.4 AI

- **Provider-agnostic from day one.** Features call our own interface, never a vendor directly, so the best model can be swapped in without rewriting features. **Recommended: Pydantic AI v2 as that interface.** It has Anthropic, Google and OpenAI built in, durable runs, and OpenTelemetry tracing (section 4.5). The alternative is a thin interface of our own.
- **Claude today** (price per million tokens, in / out): **Fable 5.1** ($10 / $50) for the hardest reasoning; **Opus 5** ($5 / $25) as the quality default; **Sonnet 5** ($2 / $10) for high volume; **Haiku 4.5** ($1 / $5) for simple, fast tasks. 1 million tokens of context (Haiku 200,000).
- **Claude features that fit our product:**
  - **Structured outputs:** answers are checked against a schema, so memo explanations and draft briefs come back as valid data, never loose text.
  - **Citations:** the AI shows exactly which records it used, which D6 promises.
  - **Prompt caching:** repeated instructions cost about 90% less.
  - **Batch API:** half price for overnight work.
  - **Effort levels:** less thinking spent on simple tasks.
  - **MCP support:** D12.
- **Tamil-first candidates for the test set:**
  - **Sarvam 105B** (open weights, Apache 2.0, February 2026). Sarvam's own reports say it wins 90% of pairwise comparisons on Indian-language benchmarks. That is their claim; our test set checks it.
  - **Sarvam speech:** Saaras v3 speech to text, Saaras V4 for several speakers at once, **Bulbul V4** voices since 30 July 2026.
  - **Bhashini** as a free fallback.
- **On devices:**
  - **Phones:** Apple Foundation Models (AFM 3 on iOS 27; no Tamil announced) and Gemini Nano 4 on recent flagship Android phones (preview).
  - **Computers:** Chrome's Prompt API on capable machines.
- **Reading text in pictures:** Google ML Kit's on-device text recognition reads Latin, Devanagari, Chinese, Japanese and Korean script, **not Tamil**.
  - A2 works on the phone, because UPI references are digits.
  - A14 works on the phone only while Instagram's screen is in English. A Tamil-language screen needs a cloud reader, tested first.
- **The Tamil test set decides** (D7). Scores are recorded and re-run monthly.
  - **Recommended tool: promptfoo** (open source, runs in CI; OpenAI bought it in early 2026, and the command-line tool stays open source).
  - It scores every candidate model on our Tamil tasks.
  - It attacks our prompts with prompt-injection and personal-data-leak tests before anything ships.
- **Rules that do not bend:** no personal data in embeddings (constraint 2); external calls retry with backoff and never block a request (`CLAUDE.md` section 3); the AI asks before acting; `ANTHROPIC_API_KEY` stays unused until an AI feature is approved.

### 4.5 Quality, security and operations (every layer)

| Item | Today | Current best | Why | Status | When |
|---|---|---|---|---|---|
| **API fuzz testing** | hand-written pytest suite and contract tests | **Schemathesis 4.x**: generates thousands of unusual requests from our OpenAPI document and flags every 500 or contract mismatch | Finds the bugs hand-written tests miss. It enforces "no unhandled exception reaches a user" (`CLAUDE.md` section 7) | Recommended (dependency) | Now |
| **CI supply chain** | actions pinned by tag: `actions/checkout@v4`, `actions/setup-python@v5` | **Move to the current majors (v7 of both), pin every action to a commit SHA, and add zizmor** to audit the workflows | In March 2025 a hijacked tag (tj-actions) hit 23,000 repositories; those pinned to a SHA were safe | Recommended (CI change) | Now |
| **Errors in production** | none yet | **Sentry** with personal-data scrubbing, already chosen in `docs/standards/backend.md` | — | Decided in the standard | Next (at first deploy) |
| **Traces and metrics** | Python logging | **OpenTelemetry** in the app (vendor-neutral), sent to one backend: SigNoz (open source, can run in India), Grafana Cloud, Logfire, or Sentry's own tracing | Shows which endpoint is slow and why, in production, against the p95 budgets. No personal data in traces (`docs/standards/security.md`) | Recommended | Next (with hosting) |
| **Load testing** | p95 measured locally with seeded data | Keep. Add a repeatable load test before launch | Proves the budgets hold under many users, not just one | Recommended | Next |

---

## 5. Roadmap

### Now (backend, this week and next)

1. **Library upgrades (4.1)** on a branch, after a trial run of the full suite on the new versions. Needs dependency approval; `requirements.txt` is shared, so Erode Harish is told first.
2. **Python 3.14 and uv**, on a branch of its own. Needs both founders: it changes the commands in `CLAUDE.md` section 4, CI and both laptops.
3. **Validation pack**: DPDP retention and deletion, ASCI, GST/TDS. It now blocks the store launch (section 7).
4. **Erode Harish's review of PR #13**, so work reaches `main`.
5. **Schemathesis fuzz tests (4.5)** against our OpenAPI document. Needs dependency approval.
6. **CI hardening (4.5)**: current action versions pinned to commit SHAs, plus zizmor. Locked (D-047); Adhi's track.

### Next (backend, once each decision is made)

| Item | Needs |
|---|---|
| Postgres 18, exact image tags, UUIDv7 for new tables, pgvector pinned | Both founders; Data track |
| Valkey | Both founders; infrastructure |
| DBOS job runner, then proof re-checks (D3) and WhatsApp alerts (D11) | Job-runner decision; WhatsApp provider decision |
| Tamper-proof deal record (D1) and receipt check (W4) | A table (Data track) and a decision |
| Login without typing a code (D8), and real code delivery. SMS codes in the formats Android 17 and browsers fill in by themselves (section 2.7) | Login provider decision (security) |
| Instagram and YouTube connections (D2); apply for YouTube's Creator Partnerships API | Both founders; consent and PII review |
| AI interface (Pydantic AI v2 recommended), Tamil test set run with promptfoo, first AI features (D5 to D7) | AI provider decision |
| Tamil search test, then hybrid search in Postgres (4.2) | Data track; a decision |
| Squawk migration lint in CI (4.2) | Data track (Erode Harish); a CI change |
| OpenTelemetry traces and a place to send them (4.5) | Hosting decision; both founders |
| Device tokens for push (A4), recording each token's kind, including iPhone Live Activity tokens (section 2.7) | Data track table |
| A city on campaigns, for free city alerts (A16) | A column (Data track) and a decision |
| Hosting in an India region | Hosting decision |
| Rate card (decision 1 of the rate card proposal) | Both founders |

### Later (frontend phase, D-004)

Everything in sections 2 and 4.3: the website, both apps, app-only and web-only features, deep links, offline, widgets, voice, App Clip.

### Watch (re-check monthly)

| Item | Adopt when |
|---|---|
| PostgreSQL 19 | Released (final targeted for the end of October 2026), and its first minor update is out |
| SQLAlchemy 2.1 | Released as final |
| Free-threaded Python (3.14t, then 3.15) | Our dependencies support it without re-enabling the GIL |
| Expo web server rendering | Out of alpha; then reconsider one codebase for the website too |
| Gemini Nano on budget Android phones | Shipping on the phones Tamil Nadu creators actually use |
| C2PA signed photos on iPhone and mid-range Android | Enough phones sign captures to make it useful for proof |
| UPI links that open a UPI app with a personal UPI ID filled in | Tested on real phones with GPay, PhonePe and Paytm; NPCI rules changed in February 2026 |
| A new AI model | It beats the current one on our Tamil test set |
| Gemini calling apps through AppFunctions (A11) | Out of private preview; join the early-access programme when the app exists |
| Siri's new AI in Tamil (A11 on iPhone) | Apple announces Tamil |
| WebMCP (W7) | Stable in Chrome and Edge, not only an origin trial |
| Meta Creator Marketing Hub | Any sign it starts recording delivery or payment (section 3) |
| ty or Pyrefly instead of mypy | 1.0 release, and it passes our strict settings |
| Granian instead of uvicorn | Our own load test shows a real gain |
| VectorChord instead of pgvector | Matching grows past what pgvector serves within budget |
| ParadeDB `pg_search` | The Tamil search test shows Postgres's built-in ranking is not good enough |

---

## 6. Decisions needed

The technology baseline (section 4.0) was decided on 22 September 2026 as D-047, so its items are no longer listed here.

| Decision | Who decides |
|---|---|
| D-046: three platforms, both roles on each, and the stack (option A) | Both founders |
| One role per phone number, or both roles with a switch | Both founders |
| Hosting | Both founders |
| Login provider: silent network authentication, Truecaller one-tap (free; Truecaller receives usage data, so it needs a privacy review), WhatsApp, SMS | Both founders |
| Instagram and YouTube connections | Both founders |
| Deferred deep-link provider | Both founders, at the frontend phase |
| Rate card decision 1 | Both founders |
| The "worth installing, never walled" rules (section 2.5) | Both founders |
| A city on campaigns, for city alerts (A16) | Both founders; Data track |
| Team seats for brands and agencies (W11) | Both founders; Data track; security review |
| Storing draft videos for the review desk (W10) | Both founders, after the validation pack |
| Where traces go: SigNoz, Grafana Cloud, Logfire or Sentry | Both founders, with hosting |

---

## 7. Warnings

- **Neither app can go into the stores without account deletion inside the app.** Apple requires it (App Store Review Guideline 5.1.1(v)); Google Play requires it in the app **and** through a web link (enforced since April 2024). Deactivating an account does not count. Ours waits on the validation pack, which makes the validation pack a launch blocker.
- **Nobody can log in outside a developer's laptop yet.** No SMS or WhatsApp provider is chosen, so login codes cannot be delivered (the fake sender refuses outside local and test).
- **WhatsApp:** service replies inside the 24-hour window are billed from **1 October 2026**.
- **DPDP:** consent-manager rules from **13 November 2026**; everything else by **13 May 2027**.
- **pgvector:** never deploy 0.6.0 to 0.8.1 (CVE-2026-3172). Pin the version everywhere.
- **Android 17 holds back ordinary SMS messages containing a code for three hours** from apps that target it. Login codes must use the SMS Retriever format (and the web one-time-code line) or they will not fill in by themselves (section 2.7). Choose the SMS provider with this in mind.
- **Next.js:** use 16.3.6 or newer (critical security release, 22 September 2026) when the website starts.
- **"Pay via UPI" with a creator's UPI ID filled in is unconfirmed.** It would keep money moving directly from brand to creator (constraint 1 holds), but whether UPI apps accept such links for personal UPI IDs has to be tested on real phones before it is proposed.

---

## 8. What changes elsewhere once D-046 is decided

- `CLAUDE.md` section 1: the platform line.
- `docs/standards/frontend.md`: platforms, iOS devices in the performance budgets, the app size budget, and the web/app split.
- `docs/FRONTEND_BLUEPRINT_MAPPING.md`: screens for both roles on all three platforms.
- `docs/COMPETITIVE_LANDSCAPE.md`: point section 6 at section 3 of this plan.

---

## 9. Keeping it current

**The upgrade rule (D-047).** Something new replaces a baseline item (section 4.0) when all four hold:

1. **Stable:** not a beta, release candidate or origin trial.
2. **Maintained:** active releases and security fixes.
3. **Measurably better for us:** on our own tests, benchmarks or Tamil test set it is faster, safer, cheaper, or better for users. A benchmark on someone else's app does not count.
4. **Inside the constraints** of `CLAUDE.md` section 2.

**Security fixes don't wait for the monthly review.** They are applied as soon as they pass the tests.

**How an upgrade is done:**
- On its own branch, with the full suite green.
- With before-and-after numbers when speed or cost is the reason.
- Through a pull request the other founder reviews.
- Afterwards, update this file's row and its "last checked" date, and write a decision entry whenever a baseline item changes.

Anything better that appears becomes a DECISION NEEDED, never a silent change. Anything not ready yet goes on the Watch list (section 5) with the condition that would make us adopt it.

- **Every working session:** before building in a layer, check that layer's rows against current releases.
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

Market and competitors: [AI agents in influencer marketing 2026](https://influencermarketinghub.com/best-ai-agents-for-influencer-marketing/) · [Reelax AI vetting](https://theprint.in/ani-press-releases/reelax-influencer-marketing-platform-is-using-ai-and-automation-to-fix-indias-influencer-marketing-bottlenecks/3016922/) · [YouTube Creator Partnerships](https://blog.youtube/news-and-events/youtube-creator-partnerships-newfronts-2026/) · [YouTube Creator Partnerships API in India via Qoruz](https://www.netinfluencer.com/youtube-creator-partnerships-api-comes-to-india-through-qoruz-integration/) · [Regional creators in India](https://www.deccanchronicle.com/amp/business/indias-influencer-marketing-boom-industry-nears-5000-crore-as-regional-creators-rise-1970876) · [Meta Creator Marketing Hub (MediaPost, 16 September 2026)](https://www.mediapost.com/publications/article/418022/meta-launches-creator-marketing-hub-live-video-ad.html) · [Meta Creator Marketing Hub (Marketing Dive)](https://www.marketingdive.com/news/meta-streamlines-creator-brand-tie-ups-with-new-marketing-hub/830593/) · [Instagram partnership messages](https://help.instagram.com/1421295241646809/)

Web and app: [Web-to-app benchmarks 2026](https://www.businessofapps.com/data/web-to-app-benchmarks/) · [Apps vs mobile websites](https://www.mobiloud.com/blog/mobile-apps-vs-mobile-websites) · [App download and uninstall statistics](https://meetanshi.com/blog/mobile-app-download-statistics/) · [Google Play app size](https://support.google.com/googleplay/android-developer/answer/9859372?hl=en) · [Google on interstitials](https://developers.google.com/search/docs/appearance/avoid-intrusive-interstitials) · [Firebase Dynamic Links FAQ](https://firebase.google.com/support/dynamic-links-faq) · [PWA limits on iOS](https://www.magicbell.com/blog/pwa-ios-limitations-safari-support-complete-guide) · [App Clips and Instant Apps in 2026](https://www.dualmedia.fr/en/app-clips-instant-apps/) · [Generative engine optimisation](https://aisearch.similarweb.com/blog/what-is-geo/) · [Myntra relaunches its website (Business Standard)](https://www.business-standard.com/article/companies/myntra-s-app-only-dream-is-dead-to-relaunch-desktop-website-on-june-1-116050301169_1.html) · [Myntra (Wikipedia)](https://en.wikipedia.org/wiki/Myntra) · [Upwork mobile app](https://www.upwork.com/i/mobile) · [India mobile OS share (Statcounter)](https://gs.statcounter.com/vendor-market-share/mobile/india) · [India smartphone share Q1 2026 (Counterpoint)](https://counterpointresearch.com/en/insights/india-smartphone-market-q1-2026) · [Get Installed Related Apps API](https://wicg.github.io/get-installed-related-apps/EXPLAINER.html) · [Deep link providers after Firebase](https://www.airbridge.io/en/blog/firebase-dynamic-links-alternatives) · [ChottuLink](https://chottulink.com/blog/firebase-dynamic-links-shut-down-5-best-alternatives-for-2026/)

Mobile and web technology: [Expo SDK 56 and React Native 0.85](https://medium.com/@dinesh.kachhot/the-react-native-ecosystem-in-mid-2026-expo-sdk-56-react-native-0-85-and-react-19-2-59919e4d76c5) · [Expo widgets and Live Activities](https://expo.dev/blog/home-screen-widgets-and-live-activities-in-expo) · [expo-share-intent](https://www.npmjs.com/package/expo-share-intent) · [Expo video uploads](https://expo.dev/blog/faster-more-reliable-video-uploads-with-expo-modules) · [Expo Router server rendering](https://docs.expo.dev/router/web/server-rendering/) · [Next.js 16](https://nextjs.org/blog/next-16) · [Android 16 Live Updates](https://www.androidauthority.com/android-16-live-notifications-3518375/) · [Android 17](https://android-developers.googleblog.com/2026/06/Android-17.html) · [Liquid Glass in React Native](https://www.callstack.com/blog/how-to-use-liquid-glass-in-react-native) · [Offline-first React Native 2026](https://procedure.tech/blogs/react-native-offline-first/) · [Expo SDK 57](https://expo.dev/changelog/sdk-57) · [Next.js security release, 22 September 2026](https://nextjs.org/blog/upcoming-nextjs-security-release-september-22-2026) · [17 things for Android developers at Google I/O 2026](https://android-developers.googleblog.com/2026/05/17-things-android-developers-google-io.html) · [Android AppFunctions](https://android-developers.googleblog.com/2026/02/the-intelligent-os-making-ai-agents.html) · [Android Live Updates](https://developer.android.com/develop/ui/views/notifications/live-update) · [Android 17 behaviour changes (SMS codes)](https://developer.android.com/about/versions/17/behavior-changes-17) · [Apple's new intelligence frameworks (WWDC26)](https://www.apple.com/newsroom/2026/06/apple-aids-app-development-with-new-intelligence-frameworks-and-advanced-tools/) · [App Intents for Siri (WWDC26)](https://developer.apple.com/videos/play/wwdc2026/343/) · [WebMCP](https://developer.chrome.com/docs/ai/webmcp) · [Chrome at Google I/O 2026](https://developer.chrome.com/blog/chrome-at-io26?hl=en) · [PWA push on iOS in 2026](https://www.magicbell.com/blog/pwa-ios-limitations-safari-support-complete-guide)

AI: [Apple Foundation Models: any LLM provider (WWDC26)](https://developer.apple.com/videos/play/wwdc2026/339/) · [Android AI at Google I/O 2026](https://android-developers.googleblog.com/2026/05/android-ai-intelligence-system.html) · [Sarvam Tamil speech to text](https://www.sarvam.ai/apis/speech-to-text/tamil) · [Sarvam text to speech](https://www.sarvam.ai/text-to-speech) · [Bhashini](https://en.wikipedia.org/wiki/Bhashini) · [September 2026 model releases](https://www.digitalapplied.com/blog/ai-model-releases-september-2026-tracker) · [MCP in 2026](https://truthifi.com/education/state-of-mcp-2026-ai-agents-custom-connectors) · [Open-source embedding models 2026](https://www.bentoml.com/blog/a-guide-to-open-source-embedding-models) · [Chrome Prompt API](https://developer.chrome.com/docs/ai/prompt-api) · [Gemini Nano hardware in Chrome](https://github.com/Ar9av/gemini-nano-chrome) · [Siri AI languages in iOS 27.2](https://9to5mac.com/2026/09/16/ios-27-2-expands-siri-ai-to-these-new-languages/) · [iOS 27 in India](https://www.business-standard.com/technology/tech-news/ios-27-siri-ai-apple-intelligence-features-iphone-india-126091500419_1.html) · [Gemini in Indian languages](https://blog.google/intl/en-in/company-news/technology/gemini-in-india-now-on-mobile-multilingual-and-more-powerful-for-your-everyday-tasks/) · [Sarvam models](https://www.sarvam.ai/models) · [Bulbul V4](https://www.explainx.ai/blog/sarvam-bulbul-v4-tts-emotion-voice-july-2026) · [MCP Apps](https://blog.modelcontextprotocol.io/posts/2026-01-26-mcp-apps/) · [ChatGPT plugins changelog](https://developers.openai.com/plugins/changelog)

India rails and rules: [Silent network authentication](https://otpless.com/products/silent-network-auth) · [Passkeys in India](https://www.corbado.com/blog/passkeys-india-overview) · [Instagram Graph API 2026](https://elfsight.com/blog/instagram-graph-api-complete-developer-guide-for-2026/) · [WhatsApp pricing from 1 October 2026](https://www.courier.com/blog/whatsapp-pricing-changes-october-2026) · [DPDP Rules timeline](https://www.sansalegal.com/post/dpdp-act-2023-and-rules-2025-phased-implementation-timeline-and-business-compliance-deadlines) · [DigiLocker KYC](https://www.befisc.com/fintechsherlock/digilocker-kyc-verification-india/) · [UPI Collect limited from 28 February 2026](https://www.stackumbrella.com/technology/upi-collect-being-limited-from-feb-28-2026-what-it-means-for-google-pay-and-phonepe-users-11176663) · [Apple account deletion](https://developer.apple.com/news/?id=12m75xbj) · [Google Play account deletion](https://support.google.com/googleplay/android-developer/answer/13327111?hl=en) · [C2PA adoption 2026](https://editorsweblog.org/2026/04/12/c2pa-adoption-tracker-platforms-content-credentials-2026)

Backend and database: [PostgreSQL 18](https://postgresql.org/about/news/postgresql-18-released-3142/) · [PostgreSQL 19 Beta 1](https://www.postgresql.org/about/news/postgresql-19-beta-1-released-3313/) · [pgvector indexes 2026](https://www.dbi-services.com/blog/pgvector-a-guide-for-dba-part-2-indexes-update-march-2026/) · [CVE-2026-3172](https://www.sentinelone.com/vulnerability-database/cve-2026-3172/) · [Valkey vs Redis 2026](https://betterstack.com/community/comparisons/redis-vs-valkey/) · [SQLAlchemy 2.1](https://www.sqlalchemy.org/docs/21/changelog/migration_21.html) · [httpx2 in Starlette](https://github.com/Kludex/starlette/pull/3291) · [FastAPI free-threaded support](https://github.com/fastapi/fastapi/pull/15149) · [uv](https://github.com/astral-sh/uv) · [DBOS](https://github.com/dbos-inc/dbos-transact-py) · [Amazon RDS PostgreSQL 18](https://aws.amazon.com/about-aws/whats-new/2025/11/amazon-rds-postgresql-major-version-18/)

Every layer, second pass: [ty](https://github.com/astral-sh/ty) · [Python type checkers compared](https://sinon.github.io/future-python-type-checkers/) · [Python servers in 2026, Gunicorn to Granian](https://www.deployhq.com/blog/python-application-servers-wsgi-vs-asgi-guide) · [Pydantic AI v2](https://pydantic.dev/articles/pydantic-ai-v2) · [Pydantic releases](https://github.com/pydantic/pydantic/releases) · [Schemathesis](https://schemathesis.readthedocs.io/) · [Logfire for FastAPI](https://pydantic.dev/logfire/fastapi) · [Sentry alternatives (SigNoz)](https://signoz.io/comparisons/sentry-alternatives/) · [Postgres dictionaries (Snowball stemmers)](https://www.postgresql.org/docs/current/textsearch-dictionaries.html) · [Postgres Snowball source, Tamil included](https://github.com/postgres/postgres/blob/master/src/backend/snowball/dict_snowball.c) · [ParadeDB](https://github.com/paradedb/paradedb) · [Squawk](https://squawkhq.com/) · [PostgreSQL 18.6 and 19 Beta 3](https://www.postgresql.org/about/news/postgresql-186-1711-1615-1519-1424-and-19-beta-3-released-3365/) · [PostgreSQL 19 release date](https://layerbase.com/blog/when-will-postgres-19-be-released) · [Valkey 9.1](https://valkey.io/blog/valkey-9-1-delivers-improvements-in-security-performance-and-more/) · [Valkey releases](https://valkey.io/download/releases/) · [Amazon ElastiCache Valkey 9.1](https://aws.amazon.com/about-aws/whats-new/2026/06/amazon-elasticache-valkey-9-1/) · [VectorChord vs pgvector](https://docs.vectorchord.ai/faqs/comparison-pgvector.html) · [Neon vs Supabase 2026](https://www.kunalganglani.com/blog/neon-vs-supabase-2026) · [Postgres hosting reviewed](https://nearbase.dev/blog/best-postgres-hosting/) · [Cloudflare Chennai](https://community.cloudflare.com/t/maa-chennai-on-2026-05-21/927284) · [TypeScript 7.0](https://devblogs.microsoft.com/typescript/announcing-typescript-7-0/) · [TypeScript 7 released (InfoQ)](https://www.infoq.com/news/2026/08/typescript-7-released/) · [Expo UI stable](https://expo.dev/blog/expo-ui-stable-sdk-56) · [Expo widgets and Live Activities stable](https://expo.dev/blog/ios-widgets-and-live-activities-in-expo) · [shadcn/ui changelog](https://ui.shadcn.com/docs/changelog/2026-05-shadcn-eject) · [Tailwind v4 and shadcn/ui](https://ui.shadcn.com/docs/tailwind-v4) · [React Native styling in 2026](https://medium.com/react-native-journal/nativewind-vs-tamagui-vs-unistyles-which-styling-library-should-you-use-in-2026-cf4f4d78b76f) · [OpenAPI code generators compared](https://dev.to/nyaomaru/which-openapi-codegen-should-you-choose-openapi-typescript-vs-hey-api-vs-orval-vs-kubb-100p) · [Hey API TanStack Query plugin](https://heyapi.dev/openapi-ts/plugins/tanstack-query) · [ESLint, Biome and Oxlint](https://www.pkgpulse.com/guides/biome-vs-eslint-vs-oxlint-2026) · [Maestro and Detox](https://www.getpanto.ai/blog/detox-vs-maestro) · [Maestro with React Native](https://docs.maestro.dev/get-started/supported-platform/react-native) · [Noto Sans Tamil UI](https://notofonts.github.io/noto-docs/specimen/NotoSansTamilUI/) · [Anek Tamil](https://fonts.adobe.com/fonts/anek-tamil-variable) · [Sarvam 30B and 105B](https://www.sarvam.ai/blogs/sarvam-30b-105b) · [Sarvam 105B analysis](https://artificialanalysis.ai/models/sarvam-105b) · [LLM evaluation tools 2026](https://majesticlabs.dev/blog/202608/13-llm-evaluation-tools-compared-aug-2026) · [Braintrust vs promptfoo](https://www.braintrust.dev/articles/braintrust-vs-promptfoo) · [ML Kit text recognition languages](https://developers.google.com/ml-kit/vision/text-recognition/v2/languages) · [Truecaller verification SDK](https://namoid.in/blog/truecaller-verification-sdk-integration) · [actions/checkout releases](https://github.com/actions/checkout/releases) · [actions/setup-python releases](https://github.com/actions/setup-python/releases) · [GitHub Actions hardening (Wiz)](https://www.wiz.io/blog/github-actions-security-guide) · [Pinning actions by SHA](https://pydevtools.com/handbook/how-to/how-to-pin-github-actions-by-sha-for-python-projects/)
