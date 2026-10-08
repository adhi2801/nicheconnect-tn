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

**Section 3 holds 14 items. Section 4 holds 8 that wait on someone outside the code.** Item 1, Python 3.14 and uv, was built on 1 October (D-072); item 2, error tracking with Sentry, on 4 October (D-074). Also built on 4 October, from the website wireframes' backend requests: one list of a party's payments with totals (D-075), and each deal's stage with whose move it is, plus a per-campaign summary with Complete (D-076). Items 19 and 22 were built on 8 October: typical response times (D-077) and city figures for public pages (D-078). Items 18 and 21, notification preferences and invite attribution, were built on 8 October (D-079, D-080), from `docs/PROPOSAL_NOTIFICATION_PREFERENCES_AND_ATTRIBUTION.md`. Section 5 lists what the founders declined or deferred.

## 3. Left to build: no outside wait, a decision first

Each needs the approval its gate names (`CLAUDE.md` section 5) before it is built.

### 3.1 Locked decisions never built

| # | Item | Why it matters before the frontend | Gate |
|---|---|---|---|
| 3 | **Tracing: OpenTelemetry** in the app (D-047); where traces go waits on hosting | Shows which endpoint is slow in production, against the p95 budgets | Dependency |
| 4 | **The name: Colyv** (decided by Adhi on 23 September, never recorded or applied) | It changes `ERROR_TYPE_BASE`, a public contract every client reads, and the database name. Renaming after a frontend exists breaks it | A decision entry, and owning the domain |

### 3.2 Built for launch quality

| # | Item | Why | Gate |
|---|---|---|---|
| 5 | **A repeatable load test** | p95 is measured with one user; launch has many (`docs/PLATFORM_AND_TECH_PLAN.md` 4.5) | Dependency |
| 6 | **The validation pack's backend mechanisms, behind switches**: account deletion's machinery, retention as settings with no invented values | App stores reject apps without in-app deletion; building the mechanism now means the answers only fill it in (constraint 6: the values are never guessed) | Security, database |
| 7 | **Results from proof: the test set run** (D-070 step 2) | Chooses the reading model by measurement | Founders' screenshots and an API key |

### 3.3 What the frontend needs from us

From `docs/PLATFORM_AND_TECH_PLAN.md` section 2.7 and the platform plan:

| # | Item | Why | Gate |
|---|---|---|---|
| 8 | **One role per phone number, or both with a switch** | Decides the account tables before any client is built around them (D-046's open question) | Both founders; database; security |
| 9 | **Device tokens for push**, recording each token's kind (Android, iPhone, Live Activity) | Push is how the app earns its install (A4); the frontend cannot register without it | Database |
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

| # | Item | Why | Gate |
|---|---|---|---|

### 3.6 From go to market (`docs/GO_TO_MARKET.md`)

| # | Item | Why | Gate |
|---|---|---|---|

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
