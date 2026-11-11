# The backend's finish line

**For:** the founders, to see how far the backend is from complete, and `/assign-task`, which reads it. **Written 1 October 2026; section 2 last measured on 14 October 2026**, from the code and CI on `main`, not from memory.

**Keeping count:** an item stays in its table when built, marked **Built** with its date and decision, so progress can be counted from this file alone. Items built before 14 October were taken out of the tables at first; on 27 October all 26 were put back, marked the same way, so every item ever listed is in a table.

The website and the apps are built beside the backend since 28 October 2026 (D-141, reversing D-053's wait); this file is the backend's definition of complete, and the list of everything between here and it. Its counterpart for the frontend is `docs/FRONTEND_COMPLETE.md`.

---

## 1. What "complete" means

The backend is complete when **every item in section 3 is built and tested to the standards in `docs/standards/`, or deferred past launch by a recorded decision**. Items blocked from outside (section 4) count once their backend part is built behind a switch, so the outside answer only turns it on.

Three things it does **not** mean:

- **Not "live".** Going live needs the AWS account and the founder steps in `infra/README.md`; that runs alongside the frontend.
- **Not "nothing more will ever be built".** Features after launch are normal. Complete means a frontend can be built against a contract that will not move under it.
- **Not "every idea built".** An item is in section 3 because launch quality or the frontend needs it. Novelties that are not needed for launch live in `docs/COMPETITIVE_LANDSCAPE.md` section 6, and ideas in `docs/PRODUCT_BACKLOG.md`. The founders can defer any section 3 item past launch by a recorded decision.

## 2. Where we are

**Measured on 14 October 2026:** 2,985 tests; coverage 98.55% counting branches when last measured that day, before its last three changes, with CI holding the floors on every run (`docs/standards/testing.md` section 7); CI green on `main` (`d6a86b8`, every job): the secret scan, the module layers, migration linting and round trip, the release step, the suite run as the app's own login and then the owner's tests, coverage, API fuzzing, the dependency and image scans, and the infrastructure check.

**Counted on 6 November 2026:** 5,879 tests in 284 files (`pytest --collect-only`); coverage 98% counting branches on the full local run that day.

**144 items listed: 61 built, 83 open**, counted from the tables on 6 November: items 103 and 104 added by D-167, items 105 to 143 by the world-bar pass and the research (section 3.13). **Added on 11 November 2026:** items 145 to 148 (D-185, operations), all open, so 148 items are listed; the built and open split was not recounted that day. **Built capabilities audited against the world bar: 0 of 32** (section 2a). The counts below are as of 5 November, before section 3.13.

**All 102 items listed on 5 November: 61 built, 41 open** (39 in section 3, items 12 and 20 in section 4).

**Open in section 3: 39 items** (68 on 14 October; item 51 built on 15 October, items 52 and 101 on 16 October, items 74, 82 and 80 on 17 October, item 79 on 18 October, items 81, 75 and 85 on 24 October, items 6, 44 and 8 on 25 October, items 26, 17, 66, 43, 68, 70, 65 and 77 on 26 October, item 11 on 27 October, item 27 on 29 October, items 13 and 40 on 4 November (40 built switched off, as 29 is), items 64 and 92 on 5 November, item 29 built switched off the same day (section 1: its outside part only turns it on), and item 87 found built since 20 September). 21 wait on something outside the code or on Erode Harish: the name and domain (4, 10), the Meta app (30, 31, 67, 78), the validation pack (33, 39), the lawyer or CA (35, 50, 76), the MSG91 template (62), results data (83, 86), founders' decisions (7, 38, 41, 46, 48, 61, 72). **18 need only an approval**. Section 4 holds the 8 that wait on someone outside, and item 29, built switched off.

**Built and tested on `main`:**
- before 1 October: Phases A, B and D of the backlog, C1 to C4, E3 and E4 (`docs/PRODUCT_BACKLOG.md`), creator search, the admin side, results read from proof (D-070, switched off), the deal record with its daily outside timestamp, proof files, and AWS described as code;
- 1 to 12 October, marked in the tables since 27 October: items 1 (Python 3.14 and uv, D-072), 2 (error tracking, D-074), 3 (tracing, D-094), 5 and 5a (the load test and overload shedding, D-092, D-093), 9 (phones registered for push, D-095), 18 and 21 (notification preferences, invite attribution, D-079, D-080), 19 and 22 (response times, city figures, D-077, D-078), 24, 25 and 28 (decline and reply dates, D-089), 32, 42 and 45, 47 (the campaign report, D-088), 53 to 60 and 63 (the legal and trust-and-safety items, D-086), the payments list, deal stages and campaign summaries (D-075, D-076), property, mutation and load testing (D-090 to D-092), and the module layers (D-099);
- 14 October, marked in the tables: items 97, 98, 99 and 102 (the app's own database login, every foreign key indexed, dispute events sealed, reporters told the outcome; D-100), 100 (every route refuses a stranger) and 69 (deal dates as a calendar file; D-102), and structured JSON logs (D-102).
- 15 October, marked in the tables: item 51 (the IT Rules' clocks on the report queue; D-103).
- 16 October, marked in the tables: item 52 (taking down one item within 3 hours of a legal order; D-104) and item 101 (a second factor for admins; D-105).
- 18 October, marked in the tables: item 79 (passkeys, off until the domain exists; D-113).
- 24 October, marked in the tables: item 81 (where you are logged in; D-114), with two weaknesses its reading found, fixed: a refresh at the moment of a logout outlived it, and every logout left the last access token working for up to 15 minutes.
- 18 October: the three weaknesses item 80's report named, fixed: a login at least a week old before changing the phone number or a UPI ID in effect (D-109), a lost current number (D-110), and the data export built in the background, downloaded once (D-111), whose failed builds now retry and then tell the owner, with one code per export (D-112).
- 17 October, marked in the tables: item 74 (a brand proves it controls its website's domain; D-106), item 82 (a second check before risky changes, and a new UPI ID's 24-hour wait; D-107) and item 80 (changing one's phone number, with a code from each number and a 72-hour wait; D-108).

## 2a. Everything built, capability by capability, against the world bar

Added 6 November 2026 (Adhi: "102 is less ... all of them world class in every aspect"). The tables in section 3 hold what was listed from 1 October on; most of what was built before that (Phases A to D of the backlog) was never itemised, so this section lists **every built capability once**, 32 of them, behind the contract's 225 operations in 33 groups (`docs/api/openapi.json`, counted 6 November). Each names the strongest published practice it is to be audited against. **An audit** reads the capability's code and tests against that benchmark and the standards' section 0, fixes what falls short in the same change, and records the result here. **Audited so far: 10 of 32** (C1 to C4, 6 November, whose one gap, item 144, was built on 7 November; C5 to C10, 7 and 8 November). Next: C11, applications. Audits run one capability per change, most-used first.

| # | Capability | Audited against | Audit |
|---|---|---|---|
| C1 | Login by phone code, access and refresh tokens, rotation | OWASP ASVS 5.0 authentication and session chapters; NIST SP 800-63B | **Audited 6 November 2026.** Holds: 6-digit codes from `secrets`, stored as a keyed HMAC and compared in constant time; 5 minutes, one use, 5 tries a code and 10 a phone per 10 minutes, sends capped 3 per 10 minutes and 10 a day, all under a per-phone lock; an admin's number answered exactly as a wrong code; HS256 pinned with a key id and every claim required, 15-minute access tokens; 256-bit refresh tokens stored hashed, rotated under a row lock, a reused one ending its whole family; suspension and an admin's second factor checked again at every refresh. **One gap, closed 7 November:** a brand's or creator's session had no absolute lifetime (each refresh granted 30 more days), where ASVS 5.0 7.3.2 (Level 2) asks for one and NIST SP 800-63B-4 sets one that SHALL exist and SHOULD be at most 30 days at AAL1: item 144, built as 30 days (D-174) |
| C2 | Where you are logged in: sessions, devices, logging out one (item 81) | ASVS session management; Google's account device page | **Audited 6 November 2026; holds.** Every request checks its session is live, so ending one takes effect at once, not at token expiry (ASVS 7.4.1); another account's session id reads exactly as one that never existed; ending any session but your own needs a step-up code and tells the owner (7.4.3, 7.5); the lock taken by every ending stops a refresh at the same moment outliving it; a phone-number change ends every session (7.4.2); the 30-day refresh window is the inactivity timeout, documented (D-008, 7.3.1), and since D-174 a login also ends 30 days after it was proven (item 144, shared with C1) |
| C3 | Risky changes: step-up codes, phone change, UPI ID wait (items 80, 82) | NIST 800-63B reauthentication; banks' cooling-off practice | **Audited 6 November 2026; holds.** A step-up code is bound by a keyed HMAC to one action and its exact new value, so it cannot be spent on another change; once, for 5 minutes, under the phone's lock; it shares the login code's send and guess caps, so it buys no extra tries; each action limited to the roles allowed it; a passkey may stand in, bound the same way (ASVS 5.0 re-authentication before sensitive changes). The cooling-off waits (24 hours for a new UPI ID, 72 for a new number, 7 days without the current one) match banks' practice for payee and number changes |
| C4 | Passkeys (item 79) | FIDO Alliance and W3C WebAuthn Level 3; NIST phishing-resistant authenticators | **Audited 6 November 2026; holds.** Yubico's maintained `fido2` (2.2.1); user verification and discoverable keys required; answers accepted only for our RP ID and listed origins; each challenge once, for 5 minutes, bound to its purpose and, for a change, an HMAC of its value; a key whose counter goes back is refused (WebAuthn Level 3, 6.1.1); no attestation asked, right for a consumer service. Off until the domain exists (item 4) |
| C5 | The admin API, its log and second factor (item 101) | ASVS Level 3 for administrative functions; least privilege | **Audited 7 November 2026; one gap, fixed.** Holds: a separate role login never makes; every admin route 404s for anyone else, so none can be found by probing; two factors in one request, the TOTP secret encrypted and bound to the account, each step once under a row lock, ten refusals lock it, set up only by script with no recovery path (ASVS 5.0 6.4.3, 6.4.4); 1 hour idle and 12 hours overall (7.3.1, 7.3.2); every admin told of every admin sign-in; every look at an account and every act logged with a reason in a table the database keeps append-only. Least privilege: one admin role, held only by the two founders (D-061); finer roles wait for a third admin. **The gap:** the test that every admin route is invisible to others named 8 of the 16 by hand, so takedowns, the founders' numbers, look-alike names and sign-ups were never shown hidden, and no route was tried with an admin's one-factor token. It now walks every route that depends on the admin guard, tries each with a one-factor admin token too, and fails on any route under `/api/v1/admin` without the guard |
| C6 | Brand and creator profiles | Data minimisation (DPDP Act section 6; `legal.md`); Stripe-style resource design | **Audited 7 November 2026; two gaps, fixed.** Holds: a date of birth is checked and never stored, only that the person confirmed they are an adult (D-086); a brand's email and any phone number appear only in the owner's own reads and an admin's logged ones; handles cleaned and unique; a change touches only the fields sent; publishing the Passport is its own action, its time the record of consent (D-036). **The gaps:** null sent for a field that always holds a value (a name, a handle, a city, a package's price: 19 fields in four schemas) reached the database's NOT NULL and answered 500, as the deal memo's had until its review; and a campaign change was not checked as a whole, so lowering the maximum below the minimum, or making a paid campaign barter, broke the database's budget checks, 500 again. Now one check refuses such nulls in every change schema (`app/core/partial_update.py`), a test holds every `*Update` schema to its table, and a campaign change is checked on the campaign as it would be after it (`campaigns/budget.py`), answering 422 with the rule's code. Each seen failing without its fix |
| C7 | The Creator Passport, its consent, and the media kit | LinkedIn's public-profile controls; schema.org ProfilePage (item 85) | **Audited 7 November 2026; two gaps, fixed.** Holds: nobody is public until they publish (D-036), a consent read in one place; a hand-listed set of fields, never a model dump, no contact details and no account id; an unknown handle, an unpublished Passport and a suspended account all read the same 404, so trying handles teaches nothing; a takedown answers 451 and is never cached; prices only after their own consent (D-055); channels as links, never our copy of a count (D-042); the media kit closed to other creators without even confirming an id. **The gaps:** a brand the creator had blocked, or that had blocked them, still read the creator's media kit, private prices included, where Instagram and LinkedIn close a profile to a blocked account; now it reads as a creator that does not exist, for the brand's team too (D-175). And `If-None-Match` was compared as an exact string, so behind a proxy that marks tags weak while compressing no 304 was ever sent; now compared as RFC 9110 says, in one helper for all four public reads. Each seen failing without its fix |
| C8 | Rate cards and their consent | Collabstr's visible rates, with our consent rule | **Audited 8 November 2026; one gap, fixed.** Holds: prices are private until the creator publishes them, a consent separate from the Passport, its first date kept and taken back at once with no argument (D-055); ten packages, counted under the creator's lock so simultaneous adds cannot pass it; prices in paise, positive, one currency; a channel's link must belong to its platform, its figures dated by our clock and shown as the creator's own claim; another creator's package is 404. Collabstr shows rates to anyone; ours show only by consent, and the media kit to brands. **The gap:** changing a package or saving a channel's figures never moved its `updated_at` (stamped once, by the database's clock), so the Passport's last change, which search engines read through the sitemap (item 85), missed every price and figure change. Now every write stamps both from the injected clock; seen failing without it |
| C9 | Availability (booked until) | Calendly and Upwork availability | **Audited 8 November 2026; holds.** One date, the last Tamil Nadu day not taking work (D-083), where Upwork has an availability badge and Calendly whole calendars: enough to stop applications and invitations going nowhere, without a calendar to keep. Worked out on read, so a passed date needs no job; bounded from today to a year; informs and never blocks (D-024's line); kept off the public Passport, whose consent predates it, and so rightly leaves the Passport's last change alone; in the export |
| C10 | Campaigns: create, edit, discover, alerts, festival templates (items 14, 40) | Aspire's and Collabstr's posting flows; Baymard's list rules | **Audited 8 November 2026; three gaps, fixed.** Holds: a draft is its brand's alone and reads as not found to anyone else; an open campaign's fields locked once creators can apply; every status move locked and checked; discovery keyset-paginated, filtered by an allow-list, never showing a suspended, withheld or blocked brand; alerts capped at 20 a Tamil Nadu day per creator. **The gaps:** a change was checked against a row it had not locked, so two changes at once, each fine alone, broke the budget's CHECK together (a 500) and one racing a publish could change a field an open campaign keeps; a suspended brand's open campaign, gone from discovery (D-061), was still read by id; and so was a brand's campaign by a creator blocked either way (D-175). Now a change locks the campaign first (its race with a second change tested; that it also orders a change against a publish cannot be shown by any final state, so is not claimed, D-177), and a read by id works suspension and blocks out in the campaign's own query: 6 queries cold, as before (measured both ways). Each seen failing without its fix |
| C11 | Applications, invitations, counter-offers, repeat deals | Upwork's proposals and offers | Owed |
| C12 | Matching, creator search, plain-words search, "like my best", saved lists (items 64, 65, 66, 103) | Offline ranking evaluation (NDCG on held-out outcomes); Fiverr's dynamic matching | Owed |
| C13 | Deal memos, terms versions, drafts and their images (item 27) | Upwork's contracts and milestones; plain-language contract practice | Owed |
| C14 | The sealed deal record and its daily outside timestamp | Certificate Transparency (RFC 9162): append-only, independently verifiable logs | Owed |
| C15 | Proof files and results from proof | AWS S3 security best practice; content-cleaning pipelines | Owed |
| C16 | Payment status, bulk mark-paid, reliability records, UPI pay link (item 87) | Upwork's client payment verification; NPCI's UPI deep-link format | Owed |
| C17 | Disputes | Airbnb's resolution centre; online dispute resolution practice | Owed |
| C18 | Notifications, preferences, quiet hours, the attention list | Apple's and Google's notification guidelines | Owed |
| C19 | Blocking, reports and their clocks, takedowns (items 51, 52, 59, 102) | The IT Rules' clocks, and the Trust & Safety Professional Association's practice | Owed |
| C20 | The data export and account deletion (item 6) | GDPR articles 15, 17 and 20 as the strictest model; DPDP rights | Owed |
| C21 | Team seats and handing a brand over (item 13) | GitHub's and Slack's organisation roles | Owed |
| C22 | Verified brand domains and look-alike names (items 74, 75) | Google Search Console's DNS verification; Unicode UTS #39 | Owed |
| C23 | Feedback revealed only when both answered (item 77) | Airbnb's simultaneous review reveal | Owed |
| C24 | City figures and fair-rate guidance (item 22) | k-anonymity as practised by salary-data companies | Owed |
| C25 | Gradual rollout (item 92) | Percentage rollouts as practised by LaunchDarkly and Google | Owed |
| C26 | Public pages and what search engines may read (item 85) | Google Search Central's guidance | Owed |
| C27 | Rate limits and overload shedding (items 5, 5a) | Stripe's published rate limiters; Google SRE, "Handling overload" | Owed |
| C28 | Errors, the contract, its snapshot and generated types | RFC 9457; Stripe's API design (`research/BACKEND_RESEARCH_2026.md` section 1) | Owed |
| C29 | Background jobs on DBOS | Durable execution (`research/BACKEND_RESEARCH_2026.md` section 4.2) | Owed |
| C30 | Error tracking, tracing, structured logs (items 2, 3) | OpenTelemetry's stable conventions; Google SRE monitoring | Owed |
| C31 | Embeddings and hybrid retrieval (D-167, D-173) | Retrieval evaluation (recall and NDCG on labelled pairs) | Owed |
| C32 | Infrastructure as code and the image (D-062, D-063) | AWS Well-Architected's six pillars; SLSA | Owed |

## 3. Left to build: no outside wait, a decision first

Each needs the approval its gate names (`CLAUDE.md` section 5) before it is built.

### 3.1 Locked decisions never built

| # | Item | Why it matters before the frontend | Gate |
|---|---|---|---|
| 1 | **Python 3.14 and uv** (D-047 locked them; we still run 3.12 and pip) | The baseline is "locked", but not true; every later upgrade starts from the wrong place | Infrastructure, CI (both commands change) · **Built 1 October (D-072)** |
| 2 | **Error tracking: Sentry**, with personal data scrubbed (D-047; `docs/standards/backend.md` section 9) | No production error is seen today. A frontend's errors must trace back to the request behind them | Dependency · **Built 4 October (D-074)** |
| 3 | **Tracing: OpenTelemetry** in the app (D-047); where traces go waits on hosting | Shows which endpoint is slow in production, against the p95 budgets | Dependency · **Built 12 October (D-094)** |
| 4 | **The name: Colyv** (decided by Adhi on 23 September, never recorded or applied) | It changes `ERROR_TYPE_BASE`, a public contract every client reads, and the database name. Renaming after a frontend exists breaks it | A decision entry, and owning the domain |

### 3.2 Built for launch quality

| # | Item | Why | Gate |
|---|---|---|---|
| 5 | **A repeatable load test** | p95 is measured with one user; launch has many (`docs/PLATFORM_AND_TECH_PLAN.md` 4.5) | Dependency · **Built 12 October (D-092)** |
| 5a | **Shed overload fast, and never wedge** (found by the load test, item 5, built 12 October, D-092). At 400 people one process ran out of database connections: requests waited 30 s, failed with a 500, and the process stopped answering until restarted (`docs/PERFORMANCE.md`). Answer 503 with `Retry-After` within a second or two when busy, and recover on its own | A web or app user meets a hang and an error instead of "busy, try again", and one busy container takes itself out | Infrastructure, architecture · **Built 12 October (D-093)** |
| 6 | **The validation pack's backend mechanisms, behind switches**: account deletion's machinery, retention as settings with no invented values | App stores reject apps without in-app deletion; building the mechanism now means the answers only fill it in (constraint 6: the values are never guessed) | Security, database · **Built 25 October (D-122)**: `POST /api/v1/me/deletion` with a step-up code for `delete_account`, refused while a deal is unfinished; it takes effect 30 days later, the owner told, first on the attention list, and able to cancel with no code (`DELETE`); then a job erases what no law asks us to keep and empties the account, brand and creator, the number let go and the other side keeping each deal with "someone who left". What is kept sits under seven `RETENTION_<KIND>_DAYS` settings, all unset; every table is placed by `app/modules/me/account_deletion_registry.py`. **Still owed:** deleting each kept kind when its period ends, a new item once the validation pack gives the periods |
| 7 | **Results from proof: the test set run** (D-070 step 2) | Chooses the reading model by measurement | Founders' screenshots and an API key |

### 3.3 What the frontend needs from us

From `docs/PLATFORM_AND_TECH_PLAN.md` section 2.7 and the platform plan:

| # | Item | Why | Gate |
|---|---|---|---|
| 8 | **One role per phone number, or both with a switch** | Decides the account tables before any client is built around them (D-046's open question) | Both founders; database; security · **Built 25 October (D-126)**: a number may hold a brand and a creator account of one person, each exactly as before; signing in as the other side makes it; the two never deal with each other; a phone change moves both |
| 9 | **Device tokens for push**, recording each token's kind (Android, iPhone, Live Activity) | Push is how the app earns its install (A4); the frontend cannot register without it | Database · **Built 12 October (D-095)** |
| 10 | **Login codes in the formats phones fill in by themselves** (Android SMS Retriever with the app's hash; the web one-time-code line) | Android 17 holds back ordinary code messages for three hours | The domain (item 4) and the login provider |
| 11 | **Scoped tokens for assistants and agents** (App Intents, AppFunctions, WebMCP, MCP) | Every assistant calls our API; each needs its own token with limited permissions | Security · **Built 27 October (D-138)**: `/api/v1/me/agent-tokens`, a named `nct_` token with chosen scopes (`deals:read`, `campaigns:read`, `applications:write`, `notes:write`, `alerts:write`) for 1 to 90 days, made with a step-up code for exactly its scopes, the owner told by a notice nobody can mute, shown once and kept only as an HMAC; every route closed to tokens unless listed in `auth/agent_scopes.py`, a deal's terms and stage but never a payment's details, a dispute's content, the phone number, account control or an admin's; revoked one by one, by logging out everywhere, a phone change or suspension, erased with the account; the account's own rate limits. **Still owed:** item 41's MCP server, on OAuth 2.1 |
| 13 | **Team seats for brands and agencies** (W11) | Real businesses have more than one person; changes the account model, so it belongs before the frontend | Both founders; database; security · **Built 4 November (D-148), not reviewed by Erode Harish**: owner, admin, campaign manager and finance; invites keep only a keyed hash of the number and send it nothing; one access check (`auth.brand_access`, `auth.brand_acts`) decides every brand route, denied by default, walked with every role; the deal record seals the member who acted and its reads name them; creators told of a member's act see their first name; each member hears the notices of the work their role does; a brand's blocks are the brand's; the owner hands the brand to a member with a code, from a login a week old (D-150; `docs/decided/PROPOSAL_TEAM_SEATS.md`), and every creator with a deal still open is told, in a notice nobody can mute (D-151) |

### 3.4 Backlog items still open

| # | Item | Gate |
|---|---|---|
| 14 | **E5**: city leaderboards, festival campaign templates, creator collectives | A design decision · **Piece 1 built 5 November (D-161): festival campaign templates**: `GET /api/v1/campaign-templates`, public, 16 festivals and seasons of every faith and none (D-165), each with its next dates (the Tamil Nadu Government's notified holidays, Drik Panchang, Easter by its rule; `dates_confirmed`, `depends_on_moon`), ordered only by the day to publish by in Tamil Nadu time; each prefills a campaign, structured deliverables and the paid-partnership label included, that the create route accepts once the brand adds its cities and budget; cached to Tamil Nadu midnight with an ETag. **Owed:** the dates for each new year when the Government notifies them (a test fails on the real calendar until they are added); the copy shown to Tamil brand owners and creators (TAMIL_DESIGN_ROOTS rule 4). Leaderboards and collectives still need a design decision (trust-and-safety.md: ranking people) |
| 15 | **E9**: public read API and webhooks for agencies | A design decision; security |
| 16 | **Competitive gap: fake-follower screening** (`docs/COMPETITIVE_LANDSCAPE.md` section 4), built from observed reach on real deals rather than bought data | After results from proof has real data; a decision |
| 17 | **Competitive gap: structured deal notes** that join the deal record, in place of chat | A product decision · **Built 26 October (D-128)**: `POST /api/v1/deal-memos/{memo_id}/notes` from the memo being sent until the deal ends; each note sealed onto the deal record by its fingerprint, the table append-only, `notes_unchanged` on the record |

### 3.5 From psychology and trust (`docs/PSYCHOLOGY_AND_TRUST.md`)

| # | Item | Why | Gate |
|---|---|---|---|
| 18 | **Notification preferences** (approved, D-071): quiet hours, a daily digest, a choice per event | No nagging (one of the 13 banned dark patterns); urgent deal events still arrive at once | Database; a decision · **Built 8 October (D-079)** |
| 19 | **Typical response times from real data** (approved, D-071; shown only from 5 examples) ("brands usually reply within N days") | Known waiting lowers anxiety; computed from existing timestamps, never invented | A decision on thresholds · **Built 8 October (D-077)** |

### 3.6 From go to market (`docs/GO_TO_MARKET.md`)

| # | Item | Why | Gate |
|---|---|---|---|
| 21 | **Invite and source attribution** (approved, D-071): who invited whom, where a sign-up came from | Measures every channel and growth loop; rewards a creator who brings a brand | Database; privacy · **Built 8 October (D-080)** |
| 22 | **City and niche aggregates for public pages** (approved, D-071: backend now, published once a city has the data): counts and medians only, behind thresholds | City pages and the quarterly rate summary, cited by search and AI search | A decision; privacy; D-036 consent and D-056 thresholds · **Built 8 October (D-078)** |

### 3.7 From the website wireframes (4 October, `docs/standards/ux.md` section 7)

Built already from the same list: deal stage and campaign summary (D-076), the payments list (D-075), and on 12 October items 24, 25 and 28: a decline's date, the creator's change request, and the brand's first answer to an application (D-089). Still open:

| # | Item | Why | Gate |
|---|---|---|---|
| 23 | **The pilot join list**: a waitlist endpoint for the landing page's Join form | The form has nowhere to send; consent wording is the validation pack's | Database; DPDP consent text |
| 24 | **The date a memo was declined** | The deal pass shows when each step happened; a decline has no date today | Database (one column) · **Built 12 October (D-089)** |
| 25 | **The creator's message with a change request** on a memo | The memo editor's banner shows what the creator asked for; it is not stored | Database (one column) · **Built 12 October (D-089)** |
| 26 | **Deliverables as a list**, one row per deliverable, on campaigns and memos | The deal pass tracks each deliverable; also step 2 of fair-rate guidance (D-056) | A product decision; database · **Built 26 October (D-127)**: `deliverable_items` on campaigns and memos (platform, format, quantity, note; at most 10), the campaign's pre-filling the memo's, sealed with the terms from terms version 2 while every earlier seal stays version 1. **Still owed:** proof per deliverable, a proposal of its own |
| 27 | **Draft first**: a creator sends a draft, the brand approves it, then it is posted | Proposed in the wireframes; changes the proof flow and its clock (D-025) | A product decision; database · **Piece 1 built 27 October (D-140)**: `draft_review` sealed as a memo term from terms version 3; drafts at `/api/v1/deal-memos/{memo_id}/drafts`, approved by the brand or by the clock (never sooner than 2 whole days), changes asked with a reason; every calendar day the brand holds a draft shown in time, its answer day included and each date once, moves the creator's due date, shown as `work_due_on` on the deal and the campaign report and used by the to-do list and the calendar, while the brand's days on a draft shown late extend only the 14-day "not delivered" limit; proof waits for an approved draft and names it on the record; the stage, attention list, export and deletion know drafts. **Piece 2 built 29 October (D-144)**: up to 10 images on a draft (JPEG, PNG or WebP, 10 MB each) through proof's cleaned upload pipeline (D-065): `POST .../drafts/uploads` for the signed form, `file_ids` when showing the draft, each image's fingerprint sealed with the draft and its cleaning sealed as `draft_file_cleaned`, both sides opening only the cleaned copy at `GET .../drafts/{draft_id}/files`; a draft's images are never read for results and never reused as proof; nothing is approved, by the brand or the clock, before every image is cleaned or refused (`images_ready_at`); each upload is marked for proof or for a draft, and both share one hourly limit. Videos stay links. **Item 27 is built.** |
| 28 | **When a brand first answered an application** | Needed to measure how fast brands reply (D-077 could not) | Database (one column) · **Built 12 October (D-089)** |

### 3.8 From the billion-dollar gap research (8 October, `docs/BILLION_DOLLAR_GAP.md`)

**Approved by Adhi on 8 October** ("approve all, build them all in the best order"). Items that need an outside answer (a platform review, a provider account, the validation pack, a both-founder decision) are built as far as that answer allows; evidence, fit with our rules, and size are in the research file.

| # | Item | Gate |
|---|---|---|
| 29 | Connected Instagram and YouTube accounts: numbers from the platform | Security, database, dependency; Meta App Review and Google verification first · **Built 26 October (D-134, D-135), switched off**: connecting from the creator's own session (`state` once, PKCE for Google), tokens sealed under `PLATFORM_TOKEN_KEY`, one channel to one creator, disconnecting, Meta's deletion and deauthorize callbacks, the export and erasure; a daily job renewing tokens and reading the counts, expiring and telling the creator when a platform refuses; the platform's count beside the stated one in search and the media kit, and on the public Passport only that the creator controls the account. Waits only on Meta App Review, Google verification and the connect notice to switch on |
| 30 | Results fetched from the platform at proof time | After 29 |
| 31 | Audience authenticity signals from real data (replaces 16's plan) | After 29 |
| 32 | A UPI pay link on every payment; the money never passes through us | A founder decision on storing UPI IDs · **Built 10 October (D-085)** |
| 33 | The barter tax tracker against the ₹20,000 TDS line | Validation pack wording |
| 35 | Aadhaar eSign on the deal memo, optional | Legal; dependency |
| 36 | Verified business from GST | Dependency, security |
| 37 | A usage-rights ledger, with Meta partnership-ad permissions | Database |
| 38 | Sales from commission deals: tracked links, codes, a Shopify app | Founders; dependency; database |
| 39 | Content pre-check against the memo and ASCI rules, flags only | Validation pack (ASCI) |
| 40 | A campaign brief from a few sentences | · **Built 4 November (D-156), switched off** until the validation pack confirms a brand's words may go to a processor outside India: `POST /api/v1/brief-drafts` stores the words and a job drafts them with Claude out of the request, within a daily ceiling; only what the words support is filled in; kept a week (`docs/decided/PROPOSAL_BRIEF_DRAFTS.md`) |
| 41 | An MCP server for brands' and creators' own AI assistants | Security; after 11 |
| 42 | Work together again in one tap | **Built 10 October (D-084)** |
| 43 | Campaign alerts for creators | Database · **Built 26 October (D-130)**: `/api/v1/me/campaign-alerts`, at most 5 a creator, each any mix of a city, a niche, a type and a least budget; publishing queues the campaign in an outbox (`campaign_alert_send`) and a job every minute records a mutable `campaign_alert` notice for each creator whose alert fits, at most 20 a Tamil Nadu day, never across a block, from a suspended, deleted or withheld party, or to the brand's own other side. In the app only until push delivery exists (E1) |
| 44 | Counter-offers on quotes | Database · **Built 25 October (D-123)**: either side of a waiting application names a figure at `POST /api/v1/applications/{id}/offers`; the other accepts, declines or counters; at most 3 each, one open at a time, none once agreed; the application cannot be accepted while one waits; an agreed figure pre-fills the memo's fee and is shown beside a different one |
| 45 | Creator availability | Database · **Built 8 October (D-083)** |
| 46 | An agency workspace | Founders, security, database |
| 47 | A campaign report a brand can hand to its boss | **Built 12 October (D-088)** |
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
| 53 | Logs kept 180 days in India (CERT-In); today 30 | **Infrastructure decision** · **Built 10 October (D-086)** |
| 54 | Adults only: a declared date of birth at sign-up (contract law, DPDP section 9) | **Founders decide**; database · **Built 10 October (D-086)** |
| 55 | A CI check that fails on a dependency licence not approved (GPL, AGPL) | CI decision · **Built 10 October (D-086)** |
| 56 | CI checks the OpenTofu files (`tofu fmt` and `tofu validate`); nothing checks them today | CI decision · **Built 10 October (D-086)** |

### 3.10 From the trust and safety standard (10 October, `docs/standards/trust-and-safety.md`)

| # | Item | Gate |
|---|---|---|
| 57 | Proof and dispute-evidence links only from a published list of hosts; today any https address passes, so a "proof" link can be a phishing page | Security · **Built 10 October (D-086)** |
| 58 | Daily ceilings per account on everything that reaches another person: invitations per brand, applications per creator, reports, disputes, search | Security · **Built 10 October (commit d9e898b; no decision entry of its own)** |
| 59 | Block, both ways: a creator blocks a brand, a brand blocks a creator; no more contact, and out of each other's discovery | Security, database · **Built 10 October (commit e9e7ddd; no decision entry of its own)** |
| 60 | Flags on free text: requests for money in text a creator reads, and contact details before a deal is agreed. Flagged, not hidden: there is no in-app chat yet to talk through instead (D-086) | Security · **Built 10 October (D-086)** |
| 61 | Pairs of accounts sharing a device or network at sign-up, flagged to the admin. (The other half, counting different counterparties on records, was built 10 October.) Needs storing sign-up addresses, which is personal data | **Founders and lawyer first** (`legal.md` 3.1); security, database |
| 62 | The login-code message says we never ask for it | MSG91 template, founders |
| 63 | The founders' weekly numbers (`docs/SURVIVAL_PLAYBOOK.md` section 4) as an admin view: campaign fill rate, application success, time to first application, repeat rate, paid on time, active brands and creators | Security (admin only) · **Built 10 October (D-087)** |

Item 34, payment confirmation from bank statements, was researched and set aside: Account Aggregator data goes only to regulated financial entities.

### 3.11 Beyond the 63: the best of 2026 (12 October, D-097)

Approved by Adhi on 12 October: "I need them in the best way possible". Each was checked against what TikTok One, Meta's Creator Marketplace, YouTube Creator Partnerships, Upwork, CreatorIQ, GRIN, Aspire, Traackr and India's own platforms ship in 2026. None moves money (constraint 1).

**Built means all eight steps of `CLAUDE.md` section 6**, never a thin version for the sake of the list. Each item gets its own research, proposal and approval before any code. One that cannot yet be done properly waits, and says why.

**Discovery**

| # | Item | Who has it; how ours goes further | Gate |
|---|---|---|---|
| 64 | Creator search in plain words ("café creators in Coimbatore, 5k to 20k followers, free in November") | TikTok One's Creator AI Search; ours explains every result and counts only real records | · **Built 5 November (D-158), with no dependency**: `GET /api/v1/creators/search-reading` reads the words by fixed rules into search's own filters, each naming the words it came from; places as the creators a brand could find spelled them, and Tamil Nadu's districts; what it cannot read comes back unread with the reason, never guessed. **Not yet**: "free in November" (search checks one day; a range of days is a follow-up), and a place written two ways is searched under the one most creators used (`docs/decided/PROPOSAL_SEARCH_WORDS.md`) |
| 65 | "More like the creators who delivered for you" | Meta's Similar Creators; ours ranks by delivered and paid records, not ad clicks | Matching · **Built 26 October (D-133)**: `GET /api/v1/creators/like-my-best`, closeness to the creators who finished a deal with the brand, each result naming its nearest and carrying its delivery record; search's rules and ceiling |
| 66 | Saved creator lists across campaigns, shared with a brand's team | Every enterprise tool | Database · **Built 26 October (D-129)**: `/api/v1/creator-lists`, at most 50 private lists of 200 creators per brand, each creator shown with search's facts and their delivery record, only while the brand could find them in search; sharing with a team waits on item 13 |
| 67 | Creators who already mention the brand | Meta; from connected accounts, with consent | After 29 |

**Workflow**

| # | Item | Who has it; how ours goes further | Gate |
|---|---|---|---|
| 68 | Barter product tracking: the courier's tracking number and the creator's "received", sealed in the deal record; we never hold the address | GRIN, Traackr, Statusphere; ours is evidence | Database · **Built 26 October (D-131)**: `PUT /api/v1/deal-memos/{memo_id}/shipment` (the brand, on an agreed barter deal, correctable until arrival), `POST .../shipment/received` (the creator, once), each sealed as `product_shipped` or `product_received`; `shipment_unchanged` on the record |
| 69 | Every agreed posting date as a calendar file both sides can add | Rare | None · **Built 14 October (D-102)**: `GET /api/v1/deal-memos/{id}/calendar.ics` |
| 70 | A content library: every approved post per brand, with its usage-rights expiry and seal | TikTok's Content Suite, CreatorIQ | Database · **Built 26 October (D-132)**, with no new table: `GET /api/v1/brands/me/content`, each approved post with the days its accepted memo states and the day they end, counted from the Tamil Nadu day of approval, filterable by `rights_state`; approval by the clock settled on read. Item 37's partnership-ad permissions remain |
| 71 | Spark Ads and partnership-ad codes, with their expiry | Insense; joins item 37 | With 37 |
| 72 | Talent managers acting for several creators, every action named and revocable | Agencies; common in India | Both founders, security |
| 73 | A pitch helper: suggestions before a creator sends, never sent for them | Upwork's Uma for proposals | Dependency (AI) |

**Trust**

| # | Item | Who has it; how ours goes further | Gate |
|---|---|---|---|
| 74 | Verified brand domain: a brand proves it owns its website by email or DNS | Rare on creator marketplaces; stops fake brands, the top scam (`trust-and-safety.md` section 2) | Security · **Built 17 October (D-106)**, by DNS TXT record: `POST /api/v1/brands/me/domain` and `.../check`; two resolvers must agree; re-checked daily, lapsing after 3 absent days; creators see the domain, since when and its registration date on every campaign and the payment record. Email proof waits on item 4 |
| 75 | Lookalike brand names flagged at sign-up | Rare | Security · **Built 24 October (D-118), option B**: a name that looks like a protected brand's (a curated list of 17, and every brand here with a verified domain), by Unicode's confusable test (UTS #39 18.0.0), filler words dropped and one slip allowed, or one mixing Latin with Cyrillic or Greek letters, is flagged to creators on its campaigns and payment record and listed for admins (`GET /api/v1/admin/brands/look-alikes`); it cannot publish a campaign until it verifies that brand's domain, or an admin clears that exact name after review (D-119); the brand sees its hold on its own profile |
| 76 | Verified person, through a licensed DigiLocker provider, keeping only "verified" | Upwork's ID and video check | Legal, dependency |
| 77 | Feedback revealed only when both sides have answered (novelty 7) | Airbnb; no retaliation | A product decision · **Built 26 October (D-136)**: three fixed scores and an optional note from each side of a finished deal, once, within 14 days, sealed; hidden from everyone until both answered or the window closed; averages beside the delivery and payment records, null below three answers, with how many partners they rest on |
| 78 | Brand-safety flags on a creator's recent public posts, flags never verdicts | CreatorIQ's SafeIQ | After 29; legal (defamation) |

**Accounts and security**

| # | Item | Who has it; why | Gate |
|---|---|---|---|
| 79 | Passkeys beside phone codes | Google, Apple, GitHub; phishing-proof, no SMS cost | Security · **Built 18 October (D-113), off until the domain exists**: passkey login; once an account has one, only it proves a risky change; optional passkey-only sign-in; a 7-day reset any passkey sign-in cancels. Switching on needs the domain (item 4), three settings and two files on the website. Admins' passkeys wait for their web page |
| 80 | Changing one's phone number safely | WhatsApp, banks; a lost SIM must not mean a lost account | Security · **Built 17 October (D-108)**: `POST /api/v1/me/phone-change` with a step-up code from the current number (bound to the new one) and a login code from the new number; the new number takes over 72 hours later, by a job that ends every session, and the old number is let go. Until then the old number logs in, the owner is told, and `DELETE /api/v1/me/phone-change` cancels with no code; login refuses a new account on the waiting number. Since 18 October (D-109) the change needs a login at least a week old, which a SIM swapper never has. A lost old number moves from a login at least 14 days old (30 until D-174), waiting 7 days, cancelled by any login with it (D-110); admins never move one |
| 81 | Where you are logged in: every session, and logging out of one | Google, WhatsApp | Security · **Built 24 October (D-114)**: `GET /api/v1/me/sessions` lists each live session with what its app said it is, when and how it signed in and when it last renewed; `DELETE /api/v1/me/sessions/{session_id}` ends one at once (another needs a code bound to that session, and the owner is told); every access token carries `sid`, checked on each request, so any logout ends its tokens at once; a new sign-in leads the attention list for 7 days, and an earlier device of the owner's can say "it was me" (D-120). No address or location kept. Since D-116 a phone's push token follows its session: ending the session unregisters the phone |
| 82 | A second check before risky changes (UPI ID, phone number, deleting the account) | Banks, Upwork | Security · **Built 17 October (D-107)**: `POST /api/v1/me/step-up` sends a code good for one change, once, for 5 minutes (a UPI ID: that exact ID), counted with login codes; setting a UPI ID, the export and logging out everywhere need it in `Step-Up-Code`; admins use their authenticator. A new UPI ID waits 24 hours before brands see it, with an alert and a cancel (`DELETE /api/v1/creators/me/upi/waiting`). Changing the phone number (80, D-108) uses `change_phone`; deleting the account (6, D-122) `delete_account`. Since 18 October (D-109) replacing a UPI ID in effect needs a login at least a week old |

**Growth and data: our own novelties, numbered**

| # | Item | Why only we can | Gate |
|---|---|---|---|
| 83 | Claimed against actual on the Passport (novelty 1) | Only we hold both the claim and sealed results | After results data |
| 84 | A free quarterly city rate report from anonymous figures (novelty 4) | We hold asking and agreed prices | Copy |
| 85 | Search-engine-ready public pages: a sitemap and structured data | Reach from Google and AI search | None · **Built 24 October (D-121), switched off**: `GET /api/v1/creators/indexable` feeds the website's sitemap with every Passport anyone may read and when it last changed; each Passport carries schema.org ProfilePage JSON-LD of its published fields; no API answer is indexed itself (`X-Robots-Tag: noindex`). `PASSPORT_INDEXING` turns it on once the publish notice says search engines will show the Passport (legal.md 3.1, Confirm). The pages and sitemap.xml are the website's |
| 86 | A creator's results against the city and niche median | From sealed results, not bought data | After results data |
| 87 | A brand's median days to pay, from the records | Answers TikTok's One Pay without holding money | Payment logic · **Built 20 September (D-027, D-034)**, found on 25 October: `median_days_to_pay` is in the brand payment record (`GET /api/v1/brands/{brand_id}/reliability`), withheld below three deals, and matching shows it to creators beside each campaign. Listed here later without being marked |

**Running it**

| # | Item | Why | Gate |
|---|---|---|---|
| 88 | Autoscaling on requests per container | One container holds about 400 people (D-093) | Infrastructure |
| 89 | A trace collector sending to X-Ray in Mumbai | Tracing has nowhere to go yet (D-094) | Infrastructure |
| 90 | An automated monthly backup-restore test | `database.md` section 8 | Infrastructure |
| 91 | Synthetic journey checks in production | Breakage found before users find it | Infrastructure |
| 92 | Gradual rollout of new features by share of accounts | How large services ship safely | · **Built 5 November (D-160)**: `FEATURE_ROLLOUT` gives a switched-on feature a share; each account's place is a keyed hash, so an account in at 10% stays in at 25% and nobody can choose to be first; `GET /api/v1/me/features` answers per account, a team member as their brand. The brief drafter honours it first; each further feature joins `ROLLOUT_FEATURES` in the change that makes its routes check it |
| 93 | Working down the 186 surviving mutants, area by area (D-091) | Testing that keeps growing | None · 5 November: the nightly run, failing since 30 October on 26 new survivors from Draft first and team seats, back to its 21 accepted, with pure tests for each rule |
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
| 103 | **Matching that learns from deals that worked** (D-167, `docs/decided/PROPOSAL_LEARNED_MATCHING.md`) | Matching ranked in a fixed order that never learned from what brands chose; an outside review named "little ML" a weakness | Matching, database, dependency · **Step 1 built 6 November (D-167)**: both match lists ranked by reciprocal rank fusion of meaning (the embedding) and the exact words of bio and brief, inside the unchanged filter; ties stay ties; words counted once each, so repeating them buys nothing; no measurable cost on the seeded data (`docs/PERFORMANCE.md`); the ranking explained in `docs/RANKING_EXPLAINED.md`. Independently reviewed the same day: eight findings, each fixed or answered; the words stored with each row by the database (D-173), so 1,000 maximum-length campaigns in one pool rank in 89 ms p95, not 533. **Still owed:** step 2 (`match_impressions`), step 3 (the LambdaMART reranker behind its published gate) |
| 104 | **A fair price range for this creator, with its coverage** (D-167, `docs/decided/PROPOSAL_RATE_INTERVALS.md`) | Rate guidance answers for a group and states no uncertainty | Dependency · Approved 6 November; built when a platform passes 200 published rate cards, the training pipeline first |

### 3.13 Found by the world-bar pass and the research (6 November 2026)

Each traces to a benchmark a standard's section 0 does not yet meet, a gap a standard names, or a *Next* in the research of 6 November (`research/BACKEND_RESEARCH_2026.md`, `research/MONEY_AT_SCALE_2026.md`). Items already listed elsewhere (90, 93, 94, 95, 36, 61, 62) are not repeated. Rows marked **(decision)** were proposed in the world-bar pass and are not approved.

**The API contract**

| # | Item | Source | Gate |
|---|---|---|---|
| 105 | A breaking-change check in CI: a contract diff fails on a removed field, a narrowed type or a new required input | `backend.md` section 0; research 1.3 | Infrastructure (CI) |
| 106 | A test that walks every POST and DELETE and fails on one a client cannot safely retry | Research 1.2 (Stripe) | None (tests) |
| 107 | `RateLimit` and `RateLimit-Policy` fields on every limited route, labelled as the IETF draft's **(decision)** | `backend.md` section 0; research 1.4 | A decision |
| 108 | Signed events to brands' and agencies' own systems (Standard Webhooks), each deal event carrying its record's seal | Research 1.6 | Architecture, security; when the first agency asks |

**The database and its connections**

| # | Item | Source | Gate |
|---|---|---|---|
| 109 | PostgreSQL 18's asynchronous reads measured (`worker` against `io_uring`) on the production image before launch | Research 2.1 | Infrastructure |
| 110 | Every composite index read against its queries for PostgreSQL 18's skip scan; indexes merged where one now serves both | Research 2.1 | Database |
| 111 | The vector-index trigger to switch on pgvector's iterative scans with HNSW, so filtered matches are never short | Research 2.2 | Database, with the index |
| 112 | A startup check and a test that processes × containers × (pool + overflow), at the autoscaler's maximum, stays inside the database's capacity | Research 3 | Infrastructure |
| 113 | A connection pooler (PgBouncer 1.25 with prepared statements, or RDS Proxy), chosen by measurement before autoscaling (item 88) | Research 3 | Infrastructure, a decision |
| 114 | Free-text cities checked per element by the database | `database.md` gap 3 | Database |
| 115 | Each *(review only)* rule given a test where practical: nullable columns explained, query plans for new hot queries, a query count per list, concurrency checks | `database.md` gap 4; `testing.md` gap 2 | None (tests) |

**Reliability and observability**

| # | Item | Source | Gate |
|---|---|---|---|
| 116 | Objectives for five journeys (sign in, publish a campaign, apply, agree a deal, mark paid), burn-rate alerts over two windows, and an error budget policy both founders sign. **Approved 11 November (D-185)**: the three alerts are page at 14.4 times over 1 hour (checked over 5 minutes), page at 6 times over 6 hours (30 minutes), ticket at 1 time over 3 days (6 hours); **proof:** the rules in OpenTofu and a test that reads them and fails when a journey has no objective or lacks one of its three alerts, seen failing with one removed. The policy itself is item 145 | `backend.md` section 0 (availability, D-166; burn rate, D-185); research 4.1 | Infrastructure: waits on hosting (items 88, 89) |
| 117 | The 99th percentile as a gate beside p95: 800 ms reads, 1,200 ms writes **(decision)** | `backend.md` section 0 | A decision |
| 118 | A timeout on every background step that calls outside (WhatsApp, the Claude API, S3), so a hung call never holds a worker | Research 4.2 | None |
| 119 | Valkey's per-field expiry where one key holds parts with different lifetimes | Research 4.3 | None |
| 120 | OpenTelemetry's stable database attributes switched on before traces have somewhere to go (item 89) | Research 5 | Infrastructure |
| 121 | Failure on purpose for every dependency the app calls, listed in `testing.md` with its test | `testing.md` section 0 (D-172) | None (tests) |
| 122 | Fuzzing that gates more than server errors, and its nightly long run | `testing.md` section 0 and gap 3 (D-172) | Infrastructure (CI) |

**Security and the supply chain**

| # | Item | Source | Gate |
|---|---|---|---|
| 123 | OWASP ASVS 5.0 mapped chapter by chapter with evidence; Level 2 throughout, Level 3 for login, sessions and the deal record | `security.md` gap 2; research 6 | Security |
| 124 | Signed provenance for every image (SLSA) and signed images | `backend.md` and `security.md` section 0; `security.md` gap 4 | Infrastructure |
| 125 | OpenSSF Scorecard measured and held at 8.0 or above **(decision)** | `security.md` section 0 | A decision |
| 126 | A penetration test before launch, against the ASVS map (item 123), and a rehearsed incident | `security.md` gap 4 | Security; its cost a founders' decision |
| 127 | The open code-scanning alert read and answered | `security.md` gap 1 | A founder signs in to read it |
| 128 | Branch protection on `main` requiring CI's jobs, so no merge passes a failing run | `testing.md` gap 1 | A founder, on GitHub |
| 129 | Admins on passkeys once the domain exists **(decision)** | `security.md` section 0 | A decision |

**Trust and safety**

| # | Item | Source | Gate |
|---|---|---|---|
| 130 | A campaign's title checked for fee requests, as its brief is | `trust-and-safety.md` gap 2 | Security · **Built 8 November** with audit C10's change to the campaign schema, as the gap said |
| 131 | A published report of what went wrong and what we did, from the counts the system keeps | `trust-and-safety.md` section 0 (Upwork) | After launch |
| 132 | The rate of fraud measured, not only its cases | `trust-and-safety.md` section 0 (Airbnb) | After launch |
| 133 | A check on each deal before it is agreed, from records only we hold (days to pay, disputes, delivery record, domain, look-alike name, first deal between the two), shown to both sides as facts, never as a score that refuses anyone | Research 8 | Trust and safety; a product decision |
| 134 | App-store privacy labels generated from the registries the code keeps | `legal.md` section 0 (D-170) | None |

**Earning money** (none of it touching deal money, constraint 1)

| # | Item | Source | Gate |
|---|---|---|---|
| 135 | Plans and what each allows, read by the rollout switch (D-160) | `research/MONEY_AT_SCALE_2026.md` section 5 | Architecture, database; after the pilot names a price |
| 136 | Charging for our plans through a payment provider, for our own fees only | Money section 5 | Dependency, security; the CA |
| 137 | Our invoices for our fees, numbered and sealed | Money section 5 | Validation pack: GST, TDS |
| 138 | The business's numbers on the founders' page: paying brands, revenue per brand, net revenue retention, deal value tracked, time to first deal | Money section 6; `SURVIVAL_PLAYBOOK.md` section 4 | None for what the records hold |
| 139 | An agency workspace: many brands per agency, per-seat plans (with item 72) | Money section 3 | Both founders, security |
| 140 | Creator Pro: what a paying creator gets, with the free tier's promise written first (never ranked by paying, the Passport always whole for free) | Money sections 3 and 7 | A product decision |
| 141 | Verified reputation as a product: a signed export of a creator's or brand's record, and a badge that checks itself against us | Money section 3 | Legal (what we may say about a person), security |
| 142 | Price truth's paid tier, deeper than the free quarterly report (item 84), never showing one person's price | Money section 3 | A decision on the minimum group size |
| 143 | Partner referrals tracked with consent, the money moving only between the partner and the person | Money section 3 | The lawyer and the CA |

**Found by the capability audits (section 2a)**

| # | Item | Source | Gate |
|---|---|---|---|
| 144 | **An absolute lifetime for brand and creator sessions**: a login lasts at most a set time from when it was proven, however often it is refreshed, then a new phone code or passkey | Audit C1; OWASP ASVS 5.0 7.3.2; NIST SP 800-63B-4 | Security · **Built 7 November (D-174)**: 30 days from the login; a lost number moves from a login 14 days old (was 30) |

**Operations at Google's and AWS's bar** (D-185, 11 November 2026; the alerts themselves are item 116)

| # | Item | Source | Gate |
|---|---|---|---|
| 145 | **The error budget policy**, written and signed by both founders: the five journeys and their objectives, how the budget is counted each month, and that a spent budget stops feature work until it is earned back. **Proof:** the signed policy in `docs/`, both names and dates on it. **Erode Harish's signature is still owed** | `backend.md` section 0; D-185 | Both founders |
| 146 | **The on-call rota and the paging tool**: the written rota, no shift over 12 hours; the tool chosen; each month's acknowledgement times (15 minutes from 07:00 to 23:00 Tamil Nadu time, 60 outside) and page counts read into `docs/reports/`, with pages that needed no action turned into tickets or removed within a week. **Proof:** the first month's report after launch, its figures from the tool, not from memory | `backend.md` section 0; `docs/INCIDENT_RESPONSE.md` section 1; D-185 | Dependency and a cost (the paging tool); before launch |
| 147 | **Game days**: the first on staging before launch, then once a quarter, each a row in `docs/INCIDENT_RESPONSE.md` section 7 with its minutes to alert and to recovery against D-168's hour, and its retrospective in `docs/reports/`. **Proof:** a test that reads the table and fails when the newest row is more than 100 days old once launched, seen failing on a table with an old row | `backend.md` section 0; AWS REL12-BP05; D-185 | Infrastructure: staging waits on hosting; the test needs none |
| 148 | **Every postmortem held to the template**: a test over `docs/reports/` that finds each postmortem and fails when it misses one of `docs/POSTMORTEM_TEMPLATE.md`'s headings, when an action has no item number or no date, or when a fix for a cause is due more than 4 weeks after the review (8 for any other action). **Proof:** the test seen failing on a sample postmortem with each fault | `backend.md` section 0; `docs/INCIDENT_RESPONSE.md` section 6; D-185 | None (tests) |

## 4. Blocked from outside the code

| Item | Waiting on |
|---|---|
| E1 notifications delivered (beyond login codes), then E2 WhatsApp actions and C5 usage-rights reminders | Meta business verification, which needs the company |
| E6 invoices and yearly statements | Validation pack: GST, TDS |
| E7 disclosure check | Validation pack: ASCI |
| E8 retention periods (the deletion itself is built: item 6, D-122) | Validation pack: DPDP |
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
- When section 3 is empty and every capability in section 2a is audited, the backend is complete.
