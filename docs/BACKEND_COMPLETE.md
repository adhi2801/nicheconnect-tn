# The backend's finish line

**Written 1 October 2026, from the code on `main` (`d3a5829`), not from memory.**

Frontend **code** starts only when the backend is complete (D-004, amended by D-053). Until today nothing defined "complete", so nobody could say how far away it was. This file is that definition, and the list of everything between here and it.

---

## 1. What "complete" means

The backend is complete when **every item in section 3 is built and tested to the standards in `docs/standards/`, or deferred past launch by a recorded decision**. Items blocked from outside (section 4) count once their backend part is built behind a switch, so the outside answer only turns it on.

Three things it does **not** mean:

- **Not "live".** Going live needs the AWS account and the founder steps in `infra/README.md`; that runs alongside the frontend.
- **Not "nothing more will ever be built".** Features after launch are normal. Complete means a frontend can be built against a contract that will not move under it.
- **Not "every idea built".** An item is in section 3 because launch quality or the frontend needs it. Novelties that are not needed for launch live in `docs/COMPETITIVE_LANDSCAPE.md` section 6, and ideas in `docs/PRODUCT_BACKLOG.md`. The founders can defer any section 3 item past launch by a recorded decision.

## 2. Where we are

Built and tested on `main`: Phases A, B and D of the backlog, C1 to C4, E3 and E4 (`docs/PRODUCT_BACKLOG.md`); creator search, the admin side, results read from proof (D-070, switched off), the deal record with its daily outside timestamp, proof files, and AWS described as code. **1,973 tests, 98.44% coverage**, API fuzzing, migration and image scanning in CI.

**Section 3 holds 20 items, plus 17 in 3.8, approved by Adhi on 8 October ("approve all"; 20 were approved, and 45, 42 and 32 are built), plus 32 from the 2026 research (3.11, approved 12 October, D-097), plus 3 from the legal standard (3.9; 53 to 56 were built the same day, D-086) and 2 from the trust and safety standard and the survival playbook (3.10; 57 to 60 built the same day, 63 the next), all of 10 October. Section 4 holds 8 that wait on someone outside the code.** Item 1, Python 3.14 and uv, was built on 1 October (D-072); item 5, the load test, on 12 October (D-092), with property and mutation testing beside it (D-090, D-091), and 5a, overload answered with a quick 503 instead of a freeze, the same day (D-093); item 3, tracing, the same day too (D-094), its destination still waiting on hosting (section 4); and item 9, phones registered for push (D-095), ready for the sender E1 waits on; item 2, error tracking with Sentry, on 4 October (D-074). Also built on 4 October, from the website wireframes' backend requests: one list of a party's payments with totals (D-075), and each deal's stage with whose move it is, plus a per-campaign summary with Complete (D-076). Items 19 and 22 were built on 8 October: typical response times (D-077) and city figures for public pages (D-078). Items 18 and 21, notification preferences and invite attribution, were built on 8 October (D-079, D-080), from `docs/decided/PROPOSAL_NOTIFICATION_PREFERENCES_AND_ATTRIBUTION.md`. Also on 8 October: every list now has a query-count test, and the security items owed before launch were built (D-082): secret scanning in CI, the image's SBOM, Dependabot, `SECURITY.md`, `security.txt` and the incident plan. On 10 October those were checked again against the bar. The incident plan's rotation steps were corrected: OpenTofu would have written a leaked generated key back, and the Valkey password and the nightly task were missing. A test now ties the plan to the secrets `infra/` defines. The money-words check now also scans commit messages and files not yet tracked. CI checks that private vulnerability reporting is on. Four more lists got query-count tests: a creator's applications, the dispute timeline, the deal record and the data export. Section 5 lists what the founders declined or deferred.

## 3. Left to build: no outside wait, a decision first

Each needs the approval its gate names (`CLAUDE.md` section 5) before it is built.

### 3.1 Locked decisions never built

| # | Item | Why it matters before the frontend | Gate |
|---|---|---|---|
| 4 | **The name: Colyv** (decided by Adhi on 23 September, never recorded or applied) | It changes `ERROR_TYPE_BASE`, a public contract every client reads, and the database name. Renaming after a frontend exists breaks it | A decision entry, and owning the domain |

### 3.2 Built for launch quality

| # | Item | Why | Gate |
|---|---|---|---|
| 6 | **The validation pack's backend mechanisms, behind switches**: account deletion's machinery, retention as settings with no invented values | App stores reject apps without in-app deletion; building the mechanism now means the answers only fill it in (constraint 6: the values are never guessed) | Security, database |
| 7 | **Results from proof: the test set run** (D-070 step 2) | Chooses the reading model by measurement | Founders' screenshots and an API key |

### 3.3 What the frontend needs from us

From `docs/PLATFORM_AND_TECH_PLAN.md` section 2.7 and the platform plan:

| # | Item | Why | Gate |
|---|---|---|---|
| 8 | **One role per phone number, or both with a switch** | Decides the account tables before any client is built around them (D-046's open question) | Both founders; database; security |
| 10 | **Login codes in the formats phones fill in by themselves** (Android SMS Retriever with the app's hash; the web one-time-code line) | Android 17 holds back ordinary code messages for three hours | The domain (item 4) and the login provider |
| 11 | **Scoped tokens for assistants and agents** (App Intents, AppFunctions, WebMCP, MCP) | Every assistant calls our API; each needs its own token with limited permissions | Security |
| 13 | **Team seats for brands and agencies** (W11) | Real businesses have more than one person; changes the account model, so it belongs before the frontend | Both founders; database; security |

### 3.4 Backlog items still open

| # | Item | Gate |
|---|---|---|
| 14 | **E5**: city leaderboards, festival campaign templates, creator collectives | A design decision |
| 15 | **E9**: public read API and webhooks for agencies | A design decision; security |
| 16 | **Competitive gap: fake-follower screening** (`docs/COMPETITIVE_LANDSCAPE.md` section 4), built from observed reach on real deals rather than bought data | After results from proof has real data; a decision |
| 17 | **Competitive gap: structured deal notes** that join the deal record, in place of chat | A product decision |

### 3.5 From psychology and trust (`docs/PSYCHOLOGY_AND_TRUST.md`)

All built: notification preferences (18, D-079) and typical response times (19, D-077).

### 3.6 From go to market (`docs/GO_TO_MARKET.md`)

All built: invite and source attribution (21, D-080) and city figures (22, D-078).

### 3.7 From the website wireframes (4 October, `docs/standards/ux.md` section 7)

Built already from the same list: deal stage and campaign summary (D-076), the payments list (D-075), and on 12 October items 24, 25 and 28: a decline's date, the creator's change request, and the brand's first answer to an application (D-089). Still open:

| # | Item | Why | Gate |
|---|---|---|---|
| 23 | **The pilot join list**: a waitlist endpoint for the landing page's Join form | The form has nowhere to send; consent wording is the validation pack's | Database; DPDP consent text |
| 26 | **Deliverables as a list**, one row per deliverable, on campaigns and memos | The deal pass tracks each deliverable; also step 2 of fair-rate guidance (D-056) | A product decision; database |
| 27 | **Draft first**: a creator sends a draft, the brand approves it, then it is posted | Proposed in the wireframes; changes the proof flow and its clock (D-025) | A product decision; database |

### 3.8 From the billion-dollar gap research (8 October, `docs/BILLION_DOLLAR_GAP.md`)

**Approved by Adhi on 8 October** ("approve all, build them all in the best order"). Items that need an outside answer (a platform review, a provider account, the validation pack, a both-founder decision) are built as far as that answer allows; evidence, fit with our rules, and size are in the research file.

| # | Item | Gate |
|---|---|---|
| 29 | Connected Instagram and YouTube accounts: numbers from the platform | Security, database, dependency; Meta App Review and Google verification first |
| 30 | Results fetched from the platform at proof time | After 29 |
| 31 | Audience authenticity signals from real data (replaces 16's plan) | After 29 |
| 33 | The barter tax tracker against the ₹20,000 TDS line | Validation pack wording |
| 35 | Aadhaar eSign on the deal memo, optional | Legal; dependency |
| 36 | Verified business from GST | Dependency, security |
| 37 | A usage-rights ledger, with Meta partnership-ad permissions | Database |
| 38 | Sales from commission deals: tracked links, codes, a Shopify app | Founders; dependency; database |
| 39 | Content pre-check against the memo and ASCI rules, flags only | Validation pack (ASCI) |
| 40 | A campaign brief from a few sentences | |
| 41 | An MCP server for brands' and creators' own AI assistants | Security; after 11 |
| 43 | Campaign alerts for creators | Database |
| 44 | Counter-offers on quotes | Database |
| 46 | An agency workspace | Founders, security, database |
| 48 | Readiness for ISO 27001 or SOC 2 | Founders |
| 49 | A public status page and service levels | Infrastructure |

Built from 3.8:

- 8 October: 45, creator availability (D-083).
- 10 October: 32, the UPI pay link (D-085). It is built and tested, and stays off until the validation pack supplies the consent notice. It also needs trying on real phones.
- 10 October: 42, work together again (D-084). It was built as brand invitations to a campaign, with repeats as one kind of invitation. Item 42's "nothing new stored" proved wrong: a memo needs an accepted application, so a brand needed a way to start one.
- 12 October: 47, the campaign report (D-088): JSON and a spreadsheet, worked out from the records, with each deal's latest seal. A PDF is left to the clients; a server-made one would be a dependency request.

### 3.9 From the legal standard (10 October, `docs/standards/legal.md`)

| # | Item | Gate |
|---|---|---|
| 50 | A public page listing, in order, what ranks creators in search and matches. It changes with the ranking code (E-Commerce Rules 5(3)) | Copy; **Confirm** we are a marketplace entity |
| 51 | The grievance clocks in the report queue: acknowledge within 24 hours, resolve within 7 days, unlawful content within 36 hours (IT Rules as amended 2026) | Security |
| 52 | Taking down one item of content within 3 hours of an order, without suspending the account | Security, database |

### 3.10 From the trust and safety standard (10 October, `docs/standards/trust-and-safety.md`)

| # | Item | Gate |
|---|---|---|
| 61 | Pairs of accounts sharing a device or network at sign-up, flagged to the admin. (The other half, counting different counterparties on records, was built 10 October.) Needs storing sign-up addresses, which is personal data | **Founders and lawyer first** (`legal.md` 3.1); security, database |
| 62 | The login-code message says we never ask for it | MSG91 template, founders |

Item 34, payment confirmation from bank statements, was researched and set aside: Account Aggregator data goes only to regulated financial entities.

### 3.11 Beyond the 63: the best of 2026 (12 October, D-097)

Approved by Adhi on 12 October: "I need them in the best way possible". Each was checked against what TikTok One, Meta's Creator Marketplace, YouTube Creator Partnerships, Upwork, CreatorIQ, GRIN, Aspire, Traackr and India's own platforms ship in 2026. None moves money (constraint 1).

**Built means all eight steps of `CLAUDE.md` section 6**, never a thin version for the sake of the list. Each item gets its own research, proposal and approval before any code. One that cannot yet be done properly waits, and says why.

**Discovery**

| # | Item | Who has it; how ours goes further | Gate |
|---|---|---|---|
| 64 | Creator search in plain words ("café creators in Coimbatore, 5k to 20k followers, free in November") | TikTok One's Creator AI Search; ours explains every result and counts only real records | Dependency (AI) |
| 65 | "More like the creators who delivered for you" | Meta's Similar Creators; ours ranks by delivered and paid records, not ad clicks | Matching |
| 66 | Saved creator lists across campaigns, shared with a brand's team | Every enterprise tool | Database |
| 67 | Creators who already mention the brand | Meta; from connected accounts, with consent | After 29 |

**Workflow**

| # | Item | Who has it; how ours goes further | Gate |
|---|---|---|---|
| 68 | Barter product tracking: the courier's tracking number and the creator's "received", sealed in the deal record; we never hold the address | GRIN, Traackr, Statusphere; ours is evidence | Database |
| 69 | Every agreed posting date as a calendar file both sides can add | Rare | None · **Built 14 October (D-102)**: `GET /api/v1/deal-memos/{id}/calendar.ics` |
| 70 | A content library: every approved post per brand, with its usage-rights expiry and seal | TikTok's Content Suite, CreatorIQ | Database |
| 71 | Spark Ads and partnership-ad codes, with their expiry | Insense; joins item 37 | With 37 |
| 72 | Talent managers acting for several creators, every action named and revocable | Agencies; common in India | Both founders, security |
| 73 | A pitch helper: suggestions before a creator sends, never sent for them | Upwork's Uma for proposals | Dependency (AI) |

**Trust**

| # | Item | Who has it; how ours goes further | Gate |
|---|---|---|---|
| 74 | Verified brand domain: a brand proves it owns its website by email or DNS | Rare on creator marketplaces; stops fake brands, the top scam (`trust-and-safety.md` section 2) | Security |
| 75 | Lookalike brand names flagged at sign-up | Rare | Security |
| 76 | Verified person, through a licensed DigiLocker provider, keeping only "verified" | Upwork's ID and video check | Legal, dependency |
| 77 | Feedback revealed only when both sides have answered (novelty 7) | Airbnb; no retaliation | A product decision |
| 78 | Brand-safety flags on a creator's recent public posts, flags never verdicts | CreatorIQ's SafeIQ | After 29; legal (defamation) |

**Accounts and security**

| # | Item | Who has it; why | Gate |
|---|---|---|---|
| 79 | Passkeys beside phone codes | Google, Apple, GitHub; phishing-proof, no SMS cost | Security |
| 80 | Changing one's phone number safely | WhatsApp, banks; a lost SIM must not mean a lost account | Security |
| 81 | Where you are logged in: every session, and logging out of one | Google, WhatsApp | Security |
| 82 | A second check before risky changes (UPI ID, phone number, deleting the account) | Banks, Upwork | Security |

**Growth and data: our own novelties, numbered**

| # | Item | Why only we can | Gate |
|---|---|---|---|
| 83 | Claimed against actual on the Passport (novelty 1) | Only we hold both the claim and sealed results | After results data |
| 84 | A free quarterly city rate report from anonymous figures (novelty 4) | We hold asking and agreed prices | Copy |
| 85 | Search-engine-ready public pages: a sitemap and structured data | Reach from Google and AI search | None |
| 86 | A creator's results against the city and niche median | From sealed results, not bought data | After results data |
| 87 | A brand's median days to pay, from the records | Answers TikTok's One Pay without holding money | Payment logic |

**Running it**

| # | Item | Why | Gate |
|---|---|---|---|
| 88 | Autoscaling on requests per container | One container holds about 400 people (D-093) | Infrastructure |
| 89 | A trace collector sending to X-Ray in Mumbai | Tracing has nowhere to go yet (D-094) | Infrastructure |
| 90 | An automated monthly backup-restore test | `database.md` section 8 | Infrastructure |
| 91 | Synthetic journey checks in production | Breakage found before users find it | Infrastructure |
| 92 | Gradual rollout of new features by share of accounts | How large services ship safely | Architecture |
| 93 | Working down the 186 surviving mutants, area by area (D-091) | Testing that keeps growing | None |
| 94 | A load test against staging, from another machine, at 1,000+ people | Today's figures are from a laptop | Infrastructure |
| 95 | A weekly slow-query report (`pg_stat_statements`) | `database.md` section 8, not yet used | Infrastructure |
| 96 | Untangle the deal domain: its 6 mutually importing pairs, by moving cross-cutting views (deal stage, campaign summary and report, payment attention) into a reporting layer (phase 2 of D-099) | Phase 1 left them as one layer that may import across itself | Architecture |

Deliberately not on the list: paying creators directly (TikTok's One Pay; constraint 1; item 87 is our answer), a database of every creator on the internet, and bought fake-follower scores (items 31 and 83 use real results).

### 3.12 Found by raising the standards (14 October, D-098)

Found by reading the code against `docs/standards/database.md` (its section 10) `docs/standards/security.md` (its section 11) and `docs/standards/trust-and-safety.md` (its section 7). Adhi approved 97 (option A), 98, 99 and 102 on 14 October ("make all these perfect and go with A"), and they were **built the same day** (D-100). 100 and 101 stay proposed, each needing its gate's approval.

| # | Item | Why | Gate |
|---|---|---|---|
| 97 | Two database roles: a migration role that owns the tables, and an app role granted only row reads and writes, each with its own secret | Today the app connects as the owner, which can switch off the deal record's seals (`database.md` gap 1). Before launch | Infrastructure, Security · **Built 14 October (D-100)** |
| 98 | Index the three unindexed foreign keys, `CONCURRENTLY`, with a CI step proving the refusing downgrades still refuse | `database.md` gaps 2 and 6 | Database, Infrastructure · **Built 14 October (D-100)** |
| 99 | Seal dispute events with the deal record's append-only trigger | `database.md` gap 3 | Database · **Built 14 October (D-100)** |
| 100 | One test that walks every route taking an object id, creates the object as one account and calls it as another, expecting 404 unless the route is public by design | 65 routes take an id, and nothing checks mechanically that each refuses a stranger (`security.md` gap 6) | None (tests only) · **Built 14 October (D-102)** |
| 101 | A second factor for the admin role | An admin session today is one phone (`security.md` gap 5) | Security |
| 102 | A reporter sees each report they made and its outcome, and is notified when one is resolved | Nothing tells a reporter today (`trust-and-safety.md` gap 1); with item 51's clocks it answers the IT Rules' acknowledge-and-resolve duty | Security · **Built 14 October (D-100)** |

## 4. Blocked from outside the code

| Item | Waiting on |
|---|---|
| E1 notifications delivered (beyond login codes), then E2 WhatsApp actions and C5 usage-rights reminders | Meta business verification, which needs the company |
| E6 invoices and yearly statements | Validation pack: GST, TDS |
| E7 disclosure check | Validation pack: ASCI |
| E8 account deletion, and retention periods | Validation pack: DPDP |
| DPDP consent-manager rules, in force 13 November 2026 | Validation pack |
| Switching on results from proof | Validation pack: may a creator's insights go to a processor |
| Going live | The AWS account and the founder steps in `infra/README.md` |
| Where traces go (D-094) | Hosting: X-Ray's OTLP endpoint in Mumbai needs signed requests, so a collector beside the app (infrastructure decision); or another backend |
| Real login codes | The MSG91 account |

## 5. Declined or deferred past launch

| Was | Item | Decision |
|---|---|---|
| 12 | The public receipt check | **Declined** (D-071): a deal is private between the brand and the creator. Each party can still check its own record from the export (`docs/DEAL_RECORD_VERIFY.md`) |
| 20 | Milestones from real records | **After launch** (D-071): they mean nothing until real deals exist |

## 6. Keeping this file true

- Updated in the same pull request as any work that moves an item. An item leaves section 3 only when it is built and tested, or deferred by a recorded decision.
- Re-checked against the code whenever `docs/PRODUCT_BACKLOG.md` is.
- When section 3 is empty, the backend is complete, and D-004's gate on frontend code opens.
