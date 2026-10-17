# The backend's finish line

**For:** the founders, to see how far the backend is from complete, and `/assign-task`, which reads it. **Written 1 October 2026; section 2 last measured on 14 October 2026**, from the code and CI on `main`, not from memory.

**Keeping count:** an item stays in its table when built, marked **Built** with its date and decision, so progress can be counted from this file alone. Items built before 14 October were taken out of the tables instead; section 2 names them.

Frontend **code** starts only when the backend is complete (D-004, amended by D-053). Until today nothing defined "complete", so nobody could say how far away it was. This file is that definition, and the list of everything between here and it.

---

## 1. What "complete" means

The backend is complete when **every item in section 3 is built and tested to the standards in `docs/standards/`, or deferred past launch by a recorded decision**. Items blocked from outside (section 4) count once their backend part is built behind a switch, so the outside answer only turns it on.

Three things it does **not** mean:

- **Not "live".** Going live needs the AWS account and the founder steps in `infra/README.md`; that runs alongside the frontend.
- **Not "nothing more will ever be built".** Features after launch are normal. Complete means a frontend can be built against a contract that will not move under it.
- **Not "every idea built".** An item is in section 3 because launch quality or the frontend needs it. Novelties that are not needed for launch live in `docs/COMPETITIVE_LANDSCAPE.md` section 6, and ideas in `docs/PRODUCT_BACKLOG.md`. The founders can defer any section 3 item past launch by a recorded decision.

## 2. Where we are

**Measured on 14 October 2026:** 2,985 tests; coverage 98.55% counting branches when last measured that day, before its last three changes, with CI holding the floors on every run (`docs/standards/testing.md` section 7); CI green on `main` (`d6a86b8`, every job): the secret scan, the module layers, migration linting and round trip, the release step, the suite run as the app's own login and then the owner's tests, coverage, API fuzzing, the dependency and image scans, and the infrastructure check.

**Open in section 3: 62 items** (68 on 14 October; item 51 built on 15 October, items 52 and 101 on 16 October, items 74, 82 and 80 on 17 October). 24 wait on something outside the code or on Erode Harish: the name and domain (4, 10), the Meta app (29 to 31, 67, 78), the validation pack (33, 39), the lawyer or CA (35, 50, 76), the MSG91 template (62), results data (83, 86), founders' decisions (7, 8, 13, 38, 41, 46, 48, 61, 72). **38 need only an approval**, among them account safety (79, 81), look-alike brand names (75), counter-offers (44), campaign alerts (43) and a brand's days to pay (87). Section 4 holds the 9 that wait on someone outside.

**Built and tested on `main`:**
- before 1 October: Phases A, B and D of the backlog, C1 to C4, E3 and E4 (`docs/PRODUCT_BACKLOG.md`), creator search, the admin side, results read from proof (D-070, switched off), the deal record with its daily outside timestamp, proof files, and AWS described as code;
- 1 to 12 October, taken out of the tables: items 1 (Python 3.14 and uv, D-072), 2 (error tracking, D-074), 3 (tracing, D-094), 5 and 5a (the load test and overload shedding, D-092, D-093), 9 (phones registered for push, D-095), 18 and 21 (notification preferences, invite attribution, D-079, D-080), 19 and 22 (response times, city figures, D-077, D-078), 24, 25 and 28 (decline and reply dates, D-089), 32, 42 and 45, 47 (the campaign report, D-088), 53 to 60 and 63 (the legal and trust-and-safety items, D-086), the payments list, deal stages and campaign summaries (D-075, D-076), property, mutation and load testing (D-090 to D-092), and the module layers (D-099);
- 14 October, marked in the tables: items 97, 98, 99 and 102 (the app's own database login, every foreign key indexed, dispute events sealed, reporters told the outcome; D-100), 100 (every route refuses a stranger) and 69 (deal dates as a calendar file; D-102), and structured JSON logs (D-102).
- 15 October, marked in the tables: item 51 (the IT Rules' clocks on the report queue; D-103).
- 16 October, marked in the tables: item 52 (taking down one item within 3 hours of a legal order; D-104) and item 101 (a second factor for admins; D-105).
- 17 October, marked in the tables: item 74 (a brand proves it controls its website's domain; D-106), item 82 (a second check before risky changes, and a new UPI ID's 24-hour wait; D-107) and item 80 (changing one's phone number, with a code from each number and a 72-hour wait; D-108).

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
| 51 | The grievance clocks in the report queue: acknowledge within 24 hours, resolve within 7 days, unlawful content within 36 hours, intimate content and impersonation within 2 hours (IT Rules as amended 2026) | Security · **Built 15 October (D-103)**: deadlines on every report, the queue by deadline, `GET /api/v1/admin/reports/clocks`, admins warned every 5 minutes. Sentry's alert rule in production is a founder step (`infra/README.md` step 9) |
| 52 | Taking down one item of content within 3 hours of an order, without suspending the account | Security, database · **Built 16 October (D-104)**: `POST /api/v1/admin/takedowns` withholds one creator, brand or campaign (451 to everyone else, out of every list, the owner told and still seeing it), measured against the 3-hour clock, its text preserved; `GET /api/v1/me/takedowns` for the owner. Who watches for orders at night, and the lawyer's Confirm items, are outside the code (`legal.md` section 3.3) |

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
| 74 | Verified brand domain: a brand proves it owns its website by email or DNS | Rare on creator marketplaces; stops fake brands, the top scam (`trust-and-safety.md` section 2) | Security · **Built 17 October (D-106)**, by DNS TXT record: `POST /api/v1/brands/me/domain` and `.../check`; two resolvers must agree; re-checked daily, lapsing after 3 absent days; creators see the domain, since when and its registration date on every campaign and the payment record. Email proof waits on item 4 |
| 75 | Lookalike brand names flagged at sign-up | Rare | Security |
| 76 | Verified person, through a licensed DigiLocker provider, keeping only "verified" | Upwork's ID and video check | Legal, dependency |
| 77 | Feedback revealed only when both sides have answered (novelty 7) | Airbnb; no retaliation | A product decision |
| 78 | Brand-safety flags on a creator's recent public posts, flags never verdicts | CreatorIQ's SafeIQ | After 29; legal (defamation) |

**Accounts and security**

| # | Item | Who has it; why | Gate |
|---|---|---|---|
| 79 | Passkeys beside phone codes | Google, Apple, GitHub; phishing-proof, no SMS cost | Security |
| 80 | Changing one's phone number safely | WhatsApp, banks; a lost SIM must not mean a lost account | Security · **Built 17 October (D-108)**: `POST /api/v1/me/phone-change` with a step-up code from the current number (bound to the new one) and a login code from the new number; the new number takes over 72 hours later, by a job that ends every session, and the old number is let go. Until then the old number logs in, the owner is told, and `DELETE /api/v1/me/phone-change` cancels with no code; login refuses a new account on the waiting number. Since 18 October (D-109) the change needs a login at least a week old, which a SIM swapper never has. A lost old number still needs the admins (no written procedure yet), and a self-service path waits on E1 |
| 81 | Where you are logged in: every session, and logging out of one | Google, WhatsApp | Security |
| 82 | A second check before risky changes (UPI ID, phone number, deleting the account) | Banks, Upwork | Security · **Built 17 October (D-107)**: `POST /api/v1/me/step-up` sends a code good for one change, once, for 5 minutes (a UPI ID: that exact ID), counted with login codes; setting a UPI ID, the export and logging out everywhere need it in `Step-Up-Code`; admins use their authenticator. A new UPI ID waits 24 hours before brands see it, with an alert and a cancel (`DELETE /api/v1/creators/me/upi/waiting`). Changing the phone number (80, D-108) uses `change_phone`; deleting the account names its action when built. Since 18 October (D-109) replacing a UPI ID in effect needs a login at least a week old |

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
| 101 | A second factor for the admin role | An admin session was one phone (`security.md` section 1) | Security · **Built 16 October (D-105)**: `POST /api/v1/auth/admin/login` takes the phone code and an authenticator app's code together; set up only with a founder's one-time ticket (`scripts/make_admin.py --second-factor`); admin sessions 1 hour idle, 12 hours at most; every admin told of every admin sign-in. Passkeys follow with item 79. |
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
