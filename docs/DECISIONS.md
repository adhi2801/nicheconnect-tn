# Decision Log

Append-only record of decisions **explicitly approved by a founder**. Recommendations and assumptions don't belong here. Format and rules: `CLAUDE.md` section 10.

Newest entries at the bottom.

---

## D-001: Modular monolith on FastAPI
- Date: 2026-09-14
- Approved by: Founders
- Context: Choosing the backend shape for a two-person team that has to ship a pilot quickly.
- Options considered: A) Modular monolith (one FastAPI app) · B) Microservices
- Chosen: A
- Reason: One deployable app is simpler to build, test and operate; module boundaries keep a later split possible.
- Consequences / follow-ups: New services need both founders' approval.

## D-002: PostgreSQL + pgvector, Redis, Alembic
- Date: 2026-09-14
- Approved by: Founders
- Context: Data store for relational data and similarity matching.
- Options considered: A) Postgres + pgvector · B) Postgres plus a separate vector database
- Chosen: A, with Redis for cache, limits and jobs, and Alembic for migrations
- Reason: One database for relational data and vectors; fewer moving parts.
- Consequences / follow-ups: Every schema change goes through Alembic.

## D-003: slowapi for rate limiting
- Date: 2026-09-16
- Approved by: Adhi and Erode Harish
- Context: Every public endpoint must be rate limited (CLAUDE.md section 2).
- Options considered: A) slowapi · B) Custom middleware · C) Limit at the hosting proxy only
- Chosen: A, with an in-memory store for now and Redis before deploy
- Reason: FastAPI-native, small, well known.
- Consequences / follow-ups: Switch the storage to Redis before running more than one process.

## D-004: Backend first; UI/UX and frontend after the backend is complete
- Date: 2026-09-16
- Approved by: <founder name>
- Context: The earlier plan assumed a finished brand dashboard prototype to wire up. There isn't one.
- Options considered: A) Build backend and frontend in parallel · B) Complete the backend first, then UI/UX design, web dashboard and mobile app
- Chosen: B
- Reason: A stable, tested API lets the UI be designed against real data and contracts, with no rework.
- Consequences / follow-ups: No frontend code in this repo. The roadmap's dashboard integration moves to after backend completion.

## D-005: Creator table and constraint naming convention
- Date: 2026-09-17
- Approved by: Adhi
- Context: Creator is the next core entity after Brand. docs/standards/database.md section 1 requires an explicit constraint naming convention before more tables are added.
- Options considered: Storing niches and languages as A) `TEXT[]` columns with an allow-list in code and `CHECK` constraints · B) Lookup tables (`niche`, `creator_niche`)
- Chosen: A. New `creator` table: display_name, handle (unique, `^[a-z0-9._]{3,30}$`), city, niches (1–5, GIN index), languages (at least 1), optional bio (max 500 characters). Allowed languages: `en` only. Allowed niches: food, fashion, beauty, tech, travel, fitness, education, entertainment, finance, lifestyle. Naming convention set on `Base.metadata`.
- Reason: Simplest fit for pilot scale; the database enforces the same rules as the app.
- Consequences / follow-ups: No contact details in `creator` (it will feed matching); they go in a separate table when login is decided. Adding a language or niche needs a migration. Brand's email constraint rename to `uq_brand_email` is deferred to the Brand email fix migration.

## D-006: Brand email and name constraints
- Date: 2026-09-17
- Approved by: Adhi
- Context: The brand table predates docs/standards/database.md: unbounded text columns, case-sensitive email uniqueness, and Postgres default constraint names.
- Options considered: A) Store emails lowercase, enforced by a `CHECK`, with the existing unique constraint · B) Unique index on `lower(email)` with emails stored as typed
- Chosen: A. `email` limited to 320 characters and must be lowercase; `name` limited to 150 characters and cannot be blank. Legacy constraint names `brand_pkey` and `brand_email_key` are renamed to `pk_brand` and `uq_brand_email` where they still exist.
- Reason: Matches the standard's "stored lowercase" rule, and Alembic tracks a plain unique constraint cleanly.
- Consequences / follow-ups: The API must lowercase emails before saving. The migration stops if two existing emails differ only in capitals; remove one and rerun. Its downgrade keeps the new constraint names and the lowercased emails.

## D-007: Phone OTP login for brands and creators
- Date: 2026-09-17
- Approved by: Adhi
- Context: Every endpoint needs an authenticated caller and ownership checks (docs/standards/security.md section 1). Creators are mostly on Android phones and use WhatsApp.
- Options considered: A) Phone OTP for both roles · B) Email magic link · C) Both
- Chosen: A. OTP rules as in docs/standards/security.md section 1 (6 digits, 5-minute expiry, single use, stored hashed, 5 attempts, send limits, same response whether or not the account exists).
- Reason: Fits WhatsApp-first mobile users; no passwords to manage.
- Consequences / follow-ups: Sending sits behind an interface with a fake for tests. The provider (SMS or WhatsApp, and which company) is a separate decision. SMS sender-registration (DLT) requirements come from the validation pack.

## D-008: Access token plus rotating refresh token
- Date: 2026-09-17
- Approved by: Adhi
- Context: Sessions must be revocable (logout, log out of all devices).
- Options considered: A) 15-minute access token plus 30-day refresh token, stored hashed and rotated on every use · B) Single long-lived token
- Chosen: A. Reuse of an old refresh token revokes the whole session family. Signing keys come from the environment, at least 256 bits, with a key ID for rotation.
- Reason: Security standard default; a stolen token can be detected and revoked.
- Consequences / follow-ups: Needs a session table (schema approval required). Needs a JWT library (dependency approval required).

## D-009: Synchronous SQLAlchemy
- Date: 2026-09-17
- Approved by: Adhi
- Context: docs/standards/backend.md section 6 requires one choice used everywhere.
- Options considered: A) Sync · B) Async
- Chosen: A. Routes that touch the database are plain `def`, so FastAPI runs them in its thread pool.
- Reason: The existing code is already sync; simpler to write and test; enough for pilot scale.
- Consequences / follow-ups: Moving to async is a scale proposal for docs/ARCHITECTURE_SCALE.md with a measured trigger, not a code change now.

## D-010: Replace python-jose and passlib with PyJWT
- Date: 2026-09-17
- Approved by: Adhi
- Context: D-008 needs a token library. python-jose 3.3.0 has published security flaws (including CVE-2024-33663) and little maintenance; passlib is for passwords, which D-007 does not use. Neither was used in code.
- Options considered: A) PyJWT · B) Keep python-jose · C) authlib · D) Custom token signing
- Chosen: A. `PyJWT==2.14.0` added; `python-jose[cryptography]` and `passlib[bcrypt]` removed. OTP and refresh-token hashing use the Python standard library (`hmac`, `hashlib`).
- Reason: Focused, widely used, actively maintained.
- Consequences / follow-ups: Everyone reinstalls from requirements.txt. A dependency audit in CI (pip-audit) is still a separate decision.

## D-011: Login tables (account, otp_challenge, auth_session)
- Date: 2026-09-17
- Approved by: Adhi
- Context: D-007 and D-008 need storage for phone identities, one-time codes and refresh-token sessions.
- Options considered: Contact details in A) one `account` table linked from `brand` and `creator` · B) separate `creator_contact` and brand phone columns. Phone numbers: A) Indian mobiles only · B) any E.164 number. Roles: A) one role per account · B) one phone owning both a brand and a creator profile.
- Chosen: `account` (phone unique, Indian mobile `+91[6-9]XXXXXXXXX`, role `brand` or `creator`), linked by required unique `brand.account_id` and `creator.account_id` with `ON DELETE RESTRICT`. `otp_challenge` (phone, HMAC code hash, attempts 0–5, expiry, single use; not linked to `account`). `auth_session` (account link with `ON DELETE CASCADE`, token family, SHA-256 token hash, expiry, used and revoked times). One role per account. New setting `OTP_HASH_KEY`, separate from the token signing key.
- Reason: Keeps phone numbers out of the creator profile (non-negotiable 2), gives one login path for both roles, and matches docs/standards/security.md section 1.
- Consequences / follow-ups: Three migrations, one per table. Brand rows without an account block the first migration; only test data exists. Retention of codes and expired sessions waits for the DPDP guidance in the validation pack. The sending provider is a separate decision. Access token lifetime moves from 60 to 15 minutes in config.

## D-012: Problem Details errors, request IDs and settings hardening
- Date: 2026-09-17
- Approved by: Adhi
- Context: docs/standards/backend.md sections 3, 8 and 9 require one error shape, a request ID on every response, and settings that refuse unsafe values, before the first real endpoint.
- Options considered: A) Build the shared error handling, request IDs, settings wiring and CI values now · B) Build the OTP endpoints first and add these later
- Chosen: A. `app/core/errors.py` (RFC 9457 Problem Details, `DomainError` base, handlers for 422, 429 with `Retry-After`, 404/405 and 500). `app/core/request_id.py` (reuses a safe `X-Request-ID`, otherwise generates one). Settings require 32+ character keys, reject placeholders and identical keys, and cap access tokens at 15 minutes. Database pool size, overflow and a 5-second statement timeout come from settings. CI gets test-only `REDIS_URL`, `SECRET_KEY` and `OTP_HASH_KEY`.
- Reason: Every endpoint after this is consistent from the start; retrofitting later costs more.
- Consequences / follow-ups: Every developer's `.env` needs `OTP_HASH_KEY` and real keys (see `.env.example`). The rate-limit handler must stay synchronous (slowapi limitation; covered by a test). `alembic/env.py` still reads `DATABASE_URL` directly; move it to settings in a later change.

## D-013: OTP login flow and token format
- Date: 2026-09-17
- Approved by: Adhi
- Context: First real feature on top of D-007, D-008 and D-011.
- Options considered: Sending the code: A) FastAPI `BackgroundTasks` · B) Adopt a job runner (RQ, ARQ or Celery) now
- Chosen: A. `POST /api/v1/auth/otp/request` returns 202 with the same body whether or not the number is registered; limits 3 per 10 minutes and 10 per day per phone, and 3 per 10 minutes per IP. `POST /api/v1/auth/otp/verify` returns access and refresh tokens; wrong, expired, used or missing codes all return 400 `otp_invalid`; a code dies after 5 wrong attempts; a new phone creates an account with the given role; a role different from the existing account returns 409 `role_mismatch`; limit 10 per 10 minutes per phone and IP. Access tokens are HS256 JWTs signed with `SECRET_KEY`, with a key ID header and `sub`, `role`, `iat`, `exp`, `jti` claims. Refresh tokens are 32 random bytes, stored only as SHA-256. Sending goes through an `OtpSender` interface with a fake for development and tests.
- Reason: No new dependency; enough for pilot scale; one generic error gives attackers nothing.
- Consequences / follow-ups: A crash between the response and the send loses that message (the user can request again). Job runner and real sending provider remain separate decisions.

## D-014: Profiles are tied to their account's role in the database
- Date: 2026-09-18
- Approved by: Adhi
- Context: The automated review on PR #5 found that `brand.account_id` could point at a creator-role account (and the reverse), that one account could own both profiles, and that `account.role` could change while a profile existed.
- Options considered: A) Composite foreign key: unique `(id, role)` on `account`, a fixed `account_role` column on each profile, and `(account_id, account_role)` referencing `account(id, role)` · B) Check it in the service layer only · C) Database triggers
- Chosen: A.
- Reason: docs/standards/database.md section 3 requires the database to enforce rules it can. B leaves the hole open to bugs, scripts and manual queries; C is harder to read, test and migrate.
- Consequences / follow-ups: One extra fixed-value column per profile table. `account.role` cannot be changed while a profile exists; a role change means deleting the profile first, which is a product decision when it comes up. Both profile tables are empty, so the migration fills nothing.

## D-015: Money is stored as whole paise
- Date: 2026-09-18
- Approved by: Adhi
- Context: The campaign budget is the first money field; docs/standards/database.md requires one choice for the whole schema.
- Options considered: A) `BIGINT` paise, exposed as `{"amount_paise": 1500000, "currency": "INR"}` · B) `NUMERIC(12,2)` rupees
- Chosen: A.
- Reason: No rounding errors; simple sums and comparisons; matches how UPI references and payment memos work. Floats are never used for money.
- Consequences / follow-ups: Every money column from now on is `BIGINT` paise with an explicit currency. Clients divide by 100 for display. Currency is `INR` only until a decision says otherwise.

## D-016: Campaigns and applications live in a new campaigns module
- Date: 2026-09-18
- Approved by: Adhi and Erode Harish (Erode confirmed on 2026-09-19, as CLAUDE.md section 3 requires both founders for architecture)
- Context: `campaign` and `application` fit none of the approved modules (auth, matching, deal_memo, payment_status, notifications).
- Options considered: A) New `app/modules/campaigns/` holding campaign and application · B) Put them in `deal_memo` · C) Two new modules
- Chosen: A. The campaign table: brand owner, title, description, type (paid, barter, commission, local_business), budget range in paise, cities, niches, deliverables, optional closing date, status (draft, open, closed, cancelled).
- Reason: "A brand asks, creators apply" is one job; `deal_memo` takes over once a deal is agreed. Applications never exist without a campaign, so they do not need their own module.
- Consequences / follow-ups: CLAUDE.md section 3's module list needs updating once Erode confirms. Shared vocabulary (niches, languages) moves to `app/core/taxonomy.py` so the two modules do not import each other's models.

## D-017: Drop the unused GIN indexes on campaign
- Date: 2026-09-19
- Approved by: Adhi
- Context: Measured with 20,000 campaigns and 40,000 applications. `EXPLAIN` shows the discovery queries use the partial index `ix_campaign_open_created_at` and filter rows; the GIN indexes on `niches` and `cities` are never chosen, because the query orders by `created_at` and takes 21 rows. The filtered query runs in 0.5 ms without them. GIN is chosen only for count-style queries with no ordering or limit.
- Options considered: A) Drop both GIN indexes now · B) Keep them for Phase D matching and faceted counts
- Chosen: A.
- Reason: docs/standards/database.md section 5: no index without a query that uses it. Unused indexes slow every write and take space.
- Consequences / follow-ups: If matching or category counters need them later, they come back in the migration for that feature, with fresh `EXPLAIN` evidence. Measurements recorded in the 2026-09-19 report.

## D-018: Per-phone limit on wrong code guesses
- Date: 2026-09-19
- Approved by: Adhi
- Context: docs/standards/security.md section 4 asks for 10 verify attempts per 10 minutes per phone. Only the per-IP limit (slowapi) and the per-code limit (5 attempts) existed, so an attacker spread across IPs could make 15 guesses per 10 minutes against one number. Flagged by the automated review on PR #7.
- Options considered: A) Count wrong guesses across all of a phone's codes in a 10-minute window, in the database · B) A Redis counter keyed by phone · C) Leave it to the per-code limit
- Chosen: A. `verify_otp` refuses with 429 `otp_verify_limit_reached` and an exact `Retry-After` once 10 wrong guesses land in the window.
- Reason: No new storage or dependency; the count is already recorded on each challenge. Guessing is the risk the standard is protecting against, and this caps it.
- Consequences / follow-ups: The count covers guesses against real codes. Attempts for a phone with no code at all are not counted, since there is nothing to guess. Per-IP limits still apply and move to Redis with D-003.

## D-019: CI checks that migrations undo and redo
- Date: 2026-09-19
- Approved by: Adhi
- Context: docs/standards/testing.md gate 4 requires CI to run `upgrade head`, `downgrade base`, `upgrade head` on a fresh database. CI only ran `upgrade head`, so a broken downgrade could reach `main`; it was only ever checked by hand.
- Options considered: A) Add the round trip plus `alembic check` to the existing CI job · B) Keep checking by hand
- Chosen: A. Two extra steps in `.github/workflows/ci.yml`.
- Reason: The standard asks for it, and a hand check is exactly what should be automatic. `alembic check` also catches a model changed without a migration.
- Consequences / follow-ups: CI takes roughly 20 seconds longer. A migration without a working `downgrade()` now fails the build.

## D-020: Client IP behind a proxy comes from a trusted X-Forwarded-For
- Date: 2026-09-19
- Approved by: Adhi
- Context: Rate limits key on the connecting address. Behind a load balancer that address is the proxy, so every user would share one limit and a single attacker could lock everyone out.
- Options considered: A) Trust `X-Forwarded-For` only when the connection comes from an address in a new `TRUSTED_PROXIES` setting · B) Always trust the header · C) Wait until a hosting platform is chosen
- Chosen: A. `TRUSTED_PROXIES` is empty by default, so nothing changes locally. The header is read right to left, skipping our own proxies, so a caller cannot forge a value.
- Reason: B lets anyone fake their address and bypass every limit. C risks reaching production with broken limits.
- Consequences / follow-ups: Set `TRUSTED_PROXIES` to the load balancer's range at deploy time. Covered by 15 tests, including forged headers, chained proxies and IPv6.

## D-021: Rate-limit storage is configurable, Redis before multiple processes
- Date: 2026-09-19
- Approved by: Adhi
- Context: D-003 chose slowapi with in-memory counters as an interim. In memory each process keeps its own count, so two processes would each allow the full limit. This is the follow-up D-003 asked for.
- Options considered: A) A `RATE_LIMIT_STORAGE_URI` setting, `memory://` by default and Redis in deployment · B) Always Redis, including locally · C) Leave it until deployment
- Chosen: A.
- Reason: Nothing changes for a single local process, and one setting switches to shared counters. Tests prove the difference: in memory two limiters allow the limit twice; with Redis they share one count.
- Consequences / follow-ups: Set `RATE_LIMIT_STORAGE_URI` to the deployed Redis before running more than one process. CI now runs a Redis service so the shared-count tests run there too. If Redis becomes unreachable in production, limiting behaviour under failure is still to be decided (open question in the reports).

## D-022: WhatsApp is alerts plus two one-tap replies, not a second app
- Date: 2026-09-19
- Approved by: Adhi
- Context: The Frontend Blueprint's flow 2.3 runs the whole journey inside WhatsApp (apply, accept, upload proof, confirm payment). Adhi's point: if the whole process happens in WhatsApp, the app has no reason to exist.
- Options considered: A) WhatsApp carries alerts with deep links, plus at most two one-tap replies (accept memo, confirm payment received) · B) The full WhatsApp journey in flow 2.3 · C) No WhatsApp at all
- Chosen: A.
- Reason: Creators find out things happened in WhatsApp, but the app holds the record, the Passport, earnings and history, which is why it is worth installing. Every duplicated action would double the code, rules and tests, and the two paths could disagree about what happened.
- Consequences / follow-ups: The notifications module needs outbound templates and one inbound webhook for the two replies, not a conversation engine: roughly a quarter of the work in flow 2.3. Blueprint flow 2.3 should be trimmed to match. Applying, pitches, proof upload and disputes stay in the app.

## D-023: In-app notifications, stored as type plus details
- Date: 2026-09-19
- Approved by: Adhi
- Context: The Frontend Blueprint marks Notifications as MVP, and D-022 makes WhatsApp alerts a delivery channel for the same events. `notifications` is already an approved module (CLAUDE.md section 3).
- Options considered: A) Store an event type, the related ids and a small JSON of rendering values · B) Store the finished sentence shown to the user
- Chosen: A. `notification` table: owner account (`ON DELETE CASCADE`), type from a fixed list, optional campaign and application links, a `details` object limited to 2,000 characters, and a read time.
- Reason: Storing English sentences would make the Tamil version impossible (ux.md section 6). The app renders wording from the type and details, so one row serves both languages.
- Consequences / follow-ups: Notifications are written in the same transaction as the event, so a record exists only if the change succeeded. Delivery (WhatsApp, push) reads these rows later and is a separate decision, together with the job runner. Only application events exist so far; deal memo and payment events follow in Phase B.

## D-024: What counts as proof of work
- Date: 2026-09-19
- Approved by: Adhi
- Context: Phase B needs a definition of "the work was done" that holds up for a solo creator on a budget phone and a one-person shop reviewing on patchy 4G.
- Options considered: A) Link plus a screenshot · B) Link plus a screenshot, and a 5-10 second screen recording for video and Story formats · C) Link only, re-checked by the server
- Chosen: B with C's mechanism. The **public link is the primary evidence**; the server re-checks it (live at day 1, 7 and 30) and records a `content_removed_on` date if it disappears. A **screenshot** is required for static posts and a **5-10 second screen recording** for video and Story formats, because a still frame proves nothing about a Reel and Stories vanish in 24 hours. Media is **compressed on the phone** before upload; the server only makes a thumbnail. Every file is stored with a checksum. Proof is required for **barter deals too**.
- Reason: A recording proves the post existed, but only a repeated link check proves it stayed up, and that check is far cheaper than asking a budget phone to upload video. Server-side video processing is infrastructure we do not need yet. Barter is often a nano creator's first deal and the one most worth documenting.
- Consequences / follow-ups: Needs the media storage decision (where files live, size limits, resumable uploads) and a scheduled job for link checks, which needs the job-runner decision. Whether a disclosure is compliant stays an ASCI question for the validation pack; the system records the creator's confirmation, it does not judge it.

## D-025: Approval window of 7 calendar days
- Date: 2026-09-19
- Approved by: Adhi
- Context: A brand must review submitted proof, or a creator waits indefinitely.
- Options considered: A) 5 working days · B) 5 calendar days · C) 7 calendar days
- Chosen: C. Proof not approved within 7 calendar days is **automatically approved**, recorded distinctly as `auto_approved`. A reminder goes out on **day 3 by WhatsApp**, not only in the app. A brand may **request changes once**, which restarts the clock; a second request does not, and the memo screen says so plainly before the first one is sent.
- Reason: "Working days" is a question a shop owner has to answer rather than a fact, so calendar days are clearer. Five calendar days is about 40% shorter than five working days, and a festival weekend would eat most of it; seven is still faster than the original and does not punish anyone for Pongal. The day-3 reminder has to reach a brand who opens the app once a month, so it goes where they already are.
- Consequences / follow-ups: Timers are anchored to midnight IST, so a deal made at 11pm does not lose a day. `auto_approved` and `approved` stay separate states, because they mean different things in the reliability record.

## D-026: Cancellation depends on whether work had started
- Date: 2026-09-19
- Approved by: Adhi
- Context: Cancelling the day after accepting, before the creator has done anything, is not the same as cancelling after a script or draft was delivered. Treating both alike would scare small brands away from barter and local campaigns, which is where the growth plan starts.
- Options considered: A) One rule for everything after acceptance · B) Split by whether work had started
- Chosen: B. Before any draft, script or proof is submitted, a cancellation is recorded as `withdrawn_early`: visible on the deal, **not counted** in the reliability record. After work has been submitted it is `cancelled_by_brand` or `cancelled_by_creator`, and it counts. **Barter cancellations are shown as a separate count and never scored**, so backing out of a free-product trial is not punished like breaking a paid deal. The memo keeps a cancellation-fee field, defaulting to zero, recorded but never collected by us.
- Reason: Fear of a permanent mark would stop the very experiments we want. Recording an unenforced fee honestly is better than pretending we can collect it.
- Consequences / follow-ups: The memo needs a "work started" marker, a new state set by the first draft, script or proof submission. Barter cancellations stay visible, so a brand cannot hide bad behaviour by routing everything through barter.

## D-027: Payment timing, states and methods
- Date: 2026-09-19
- Approved by: Adhi
- Context: We never hold money, so payment states are a record and a reputation, not a transfer.
- Options considered: A) On time or late · B) On time, late after 7 days, and unpaid after 21 days
- Chosen: B. Payment is due **7 calendar days after approval**. Not marked paid by then is `late`; still unpaid at **21 days with no dispute** is `unpaid`, a stronger and separate state. Payment may be marked paid by **UPI, bank transfer or cash**, each with a reference note; only UPI can be matched automatically, so the others rest on the creator's confirmation, and both sides are nudged to confirm. A brand's record shows median days to pay, the share late, and the number of completed deals, **only after 3 completed deals**; before that it reads "New brand, no payment history yet" rather than showing nothing.
- Reason: Late at day 8 and silence at day 25 are different problems for someone owed Rs 3,000. A Tamil Nadu shop paying cash at an event should not be marked late because nobody logged it. A blank record invites the worst assumption; a stated floor is honest.
- Consequences / follow-ups: Payment reminders go by WhatsApp, as money-related timers (D-029). Automatic matching applies to UPI references only.

## D-028: Disputes - we record, we do not judge
- Date: 2026-09-19
- Approved by: Adhi
- Context: With no money in our hands and no legal standing, acting as a judge creates liability and disappointment.
- Options considered: A) A neutral evidence timeline with factual outcomes · B) We decide who is right · C) Automatically pull the parties' WhatsApp conversation into the evidence
- Chosen: A. Either side opens a dispute; the other has 7 days to respond with evidence. Outcomes: `resolved_paid`, `resolved_withdrawn`, **`resolved_informally`** (either side may close it early, because most of these end with a phone call), or `unresolved` after 30 days. `unresolved` appears as a fact on both records, never as a verdict, and either party can export the timeline.
- Reason: Being the honest record-keeper is what makes the marketplace trustworthy. Forcing a 30-day wait for a matter already settled by phone is bad for a WhatsApp-native audience.
- Consequences / follow-ups: **C was rejected on two grounds**: the WhatsApp Business API only exposes messages in the conversation with our own number, so a brand's private chat with a creator is not available to us; and ingesting private conversations would break our own data-minimisation rule and raise a serious DPDP problem. Instead **either party attaches evidence, including WhatsApp screenshots**, and attachments join the timeline with a timestamp. The claim that this posture preserves intermediary protection under the IT Act goes to the lawyer **as a question, not a conclusion** (CLAUDE.md section 2: no guessed compliance).

## D-029: Reminder channels and notification limits
- Date: 2026-09-19
- Approved by: Adhi
- Context: Every Phase B timer (proof due, day-3 approval nudge, payment due, payment late, dispute response) could send a WhatsApp message to both sides. Template messages cost money, need approval in advance, and Indian rules restrict unsolicited and night-time messages.
- Options considered: A) WhatsApp for every timer · B) WhatsApp for money-related timers, in-app for the rest, with quiet hours and per-account preferences
- Chosen: B. WhatsApp carries the approval deadline, payment due, payment late and dispute response reminders. Everything else stays in-app. No messages during quiet hours, and each account can turn categories off.
- Reason: Assuming the app is opened rarely is correct, but four timers for both sides of every deal is a cost and an annoyance, and someone who mutes us receives nothing at all.
- Consequences / follow-ups: Needs a notification preference table and a quiet-hours rule. Template wording must be approved by the provider before launch, which takes days: plan it early.

## D-030: Phase B open points carried forward
- Date: 2026-09-19
- Approved by: Adhi
- Context: Recording what D-024 to D-029 deliberately leave open, so none of it is lost.
- Options considered: n/a (a record, not a choice)
- Chosen: Four points stay open. (1) **A day means midnight IST** for every timer. (2) **Link rot**: a removed post gets `content_removed_on`, which also matters for usage rights. (3) **Notification fatigue** is a real risk once timers chase both sides; preferences and quiet hours exist for that reason. (4) **Who the pilot serves**: this policy assumes a one-person shop, while the Frontend Blueprint assumes brand teams with admin, editor and viewer roles. Both cannot be the primary user, and the answer changes the account model.
- Reason: Writing down what is unresolved is cheaper than rediscovering it during the build.
- Consequences / follow-ups: Point 4 must be settled before any team-account work. Points 1 to 3 are handled inside Phase B.

## D-031: Upgrade FastAPI, Starlette and pytest, and audit dependencies in CI
- Date: 2026-09-20
- Approved by: Adhi
- Context: `security.md` section 8 requires a CI vulnerability audit "once approved". Running `pip-audit` by hand first showed what CI would say: 16 known vulnerabilities across two pinned packages. Eight were in Starlette, the web layer every request passes through — including an unvalidated `Host` header that injects a path into `request.url`, unbounded buffering of multipart text fields (memory exhaustion, reachable without logging in), and `max_fields` / `max_part_size` being ignored on urlencoded forms, so limits we believed were set did nothing. `fastapi==0.115.0` pinned `starlette<0.39.0`, so Starlette could not be fixed on its own.
- Options considered: A) Leave the pins alone and skip the audit · B) Add the audit without upgrading (CI red on the first run, so not a real option) · C) Upgrade FastAPI, take Starlette with it, upgrade pytest, then add the audit
- Chosen: C. `fastapi` 0.115.0 → 0.141.1, `starlette` 0.38.6 → 1.6.0, `pytest` 8.3.3 → 9.1.1. A `pip-audit` step was added to `.github/workflows/ci.yml` as gate 6 of `testing.md` section 7.
- Reason: These are fixes, not features, and one of them is reachable by anyone on the internet — which matters more now that the public Creator Passport answers without a login. The upgrade was trialled in a local environment before asking: 619 tests passed with no change to any source or test file, and the OpenAPI contract still generates 49 operations with every summary intact.
- Consequences / follow-ups: (1) `starlette` is now pinned in `requirements.txt` even though FastAPI pulls it in, because FastAPI asks only for `>=0.46.0` with no upper bound and advisories in that range stay open until 1.3.1 — unpinned, a fresh install could resolve to a vulnerable version again. It is the only transitive pin, and it exists for that reason alone. (2) The audit blocks merge on **any** known vulnerability, not only high and critical: most Python advisories carry no severity rating, so filtering by severity would let unrated ones through. Accepting one knowingly means adding `--ignore-vuln <ID>` with a comment naming who decided and why. (3) `pip-audit` is pinned at 2.10.1 and installed in the CI step, deliberately not in `requirements.txt`, so its dependencies stay out of the running app. (4) `requirements.txt` is a shared file: Erode Harish needs to run `pip install -r requirements.txt` after this merges, or his environment will disagree with the repo. (5) Starlette's own test client emits two `anyio` deprecation warnings; they are upstream, not ours.

## D-032: The payment_status table, and no status column on it
- Date: 2026-09-20
- Approved by: Adhi
- Context: D-027 set the payment rules on 19 September and the table was assigned to the Data track, but nothing had been started or pushed by the end of 20 September. Five features were blocked behind it: the payment handshake, the brand reliability record, the `late` and `unpaid` states, disputes, and the whole money half of Phase 6. Adhi took the task over so the work could continue.
- Options considered: A) A stored `status` column, as every other table here has · B) Store only the facts (`due_on`, `marked_paid_at`, `confirmed_at`) and read `due`, `late` and `unpaid` from them against today's date
- Chosen: B.
- Reason: `late` and `unpaid` are not events anybody causes — nothing happens on day 8 except that the day arrives. A stored status would need a scheduled job to flip it, and no job runner has been chosen; worse, a row could then say `due` while a creator has been waiting a month because a cron failed quietly. A derived state cannot be stale. It is the same reasoning that made proof auto-approval lazy rather than scheduled. The cost is that "show me every late payment" is a `WHERE` clause rather than an equality check, which the partial index `ix_payment_status_outstanding` exists for.
- Consequences / follow-ups: (1) **`UNPAID_AFTER_DUE_DAYS = 14` needs confirming.** D-027 says "21 days" but its own example says "silence at day 25", which only works if the 21 days run from approval rather than from the due date; with the default 7-day window that is 14 days after due. It is expressed relative to the due date because counting from approval would make a memo with a 30-day payment window turn `unpaid` nine days before the money was owed. Changing it is one number. (2) The reference column is `VARCHAR(32)` and validation is deliberately permissive: a UPI/IMPS reference is a 12-digit RRN, a NEFT UTR is 16 characters and an RTGS UTR is 22, and refusing to record a real payment because a brand's app showed an unusual id would be a worse failure than storing one we cannot match. `is_auto_matchable` answers matchability separately, and only for a UPI reference that really is 12 digits, which is what D-027's automatic-matching line rests on. (3) `derive_state` takes a `has_open_dispute` argument that is always False until the dispute table (D-028) exists; the seam is left rather than faked. (4) A barter memo has no fee, so it has no payment record, and asking for one is a domain error rather than a NOT NULL violation. (5) The table is included in a person's data export — the export completeness test failed the moment the table was added, which is what it was built to do.

## D-033: What happens when the creator never confirms
- Date: 2026-09-20
- Approved by: Adhi
- Context: The payment handshake left a gap D-027 did not cover. A brand marks a payment sent; if the creator never confirms, the record sat at `paid` forever. Research on two-sided marketplaces is consistent that non-confirmation is the common case rather than an edge case — someone who has their money has no reason to come back and tick a box — and that the behaviour must be designed in from the start rather than discovered in production.
- Options considered: A) Auto-confirm after a window of silence, mirroring the proof auto-approval in D-025 · B) A separate derived state, `unconfirmed`, that states the silence without resolving it
- Chosen: B, with a 7-day window, matching the approval window in D-025.
- Reason: The asymmetry matters. A brand that genuinely paid should not look permanently unconfirmed through nobody's fault, which is the problem with doing nothing. But auto-confirming puts words in a creator's mouth about their own income, and confirmation is the only part of this record carrying independent weight — if the platform can manufacture it, it means nothing. `unconfirmed` states exactly what is known: the brand says it paid, the creator did not answer. That is consistent with D-028, where we record and do not judge. It is also free to build, because the state is derived rather than stored and needs no scheduled job.
- Consequences / follow-ups: (1) A late confirmation is still accepted and still moves the record to `confirmed`; the window only changes what the record says in the meantime, never the creator's right to answer. (2) **Open, for the reliability record:** whether `unconfirmed` counts as paid-on-time for a brand. It should probably not be held against them, but that is a reputation decision and belongs with the reliability record, not here. (3) The window is a constant rather than a per-memo column; it moves onto the memo only if a founder wants it negotiable. (4) Migration 18 adds two notification types, `payment_marked_paid` and `payment_confirmed`, because without them nothing ever prompts a creator to confirm. The reminder types from D-029 were deliberately left out: nothing sends them until a job runner is chosen, and a CHECK constraint listing values nobody writes is a claim we have not kept. (5) The confirmation window is counted on Tamil Nadu's calendar, like every other deadline here (D-030 point 1).

## D-034: The brand payment record, and what it refuses to hide
- Date: 2026-09-20
- Approved by: Adhi
- Context: D-027 said a brand's record shows median days to pay, the share late and the number of completed deals, only after three completed deals. Building it raised three ways a record like this misleads the person it is meant to protect, all drawn from the marketplace reputation literature.
- Options considered: A) Count only deals that ended in a payment · B) Count every deal whose deadline has run out, paid or not · C) Smooth small samples toward an average, as star ratings do
- Chosen: B, with no smoothing, and with outstanding debt reported at all times.
- Reason: (1) **Silence must not launder a bad record.** The strongest finding in the literature is that people who have a bad experience leave and never report it, so bad actors go unharmed. Here it bites hardest: a creator who was never paid is the least likely person to come back and tick a box. So a payment that ran past its deadline and stayed there counts against the record whether or not anybody complained — the calendar reports it and nobody has to. (2) **"New brand" must not be a hiding place.** Reputation systems are gamed by starting again, and a three-deal floor is exactly the kind of rule to sit behind, so `currently_overdue` is reported always: below the floor, above it, and for a brand with no completed deals at all. A brand owing two creators right now can never read as simply new. (3) **No shrinkage.** Pulling a small sample toward the global mean is right for star ratings, where the number is an opinion, and wrong here, where it is a record of what happened — it would report a figure untrue of this brand. Instead the count always travels beside the figures, and below three deals the figures are withheld rather than dressed up.
- Consequences / follow-ups: (1) **Resolves D-033 point 2:** a payment the creator never confirmed counts as paid for the brand. The brand did the thing being measured, and a creator's silence is not the brand's fault. (2) A payment that is merely late is not yet counted as a failure — four days overdue is not the same as never paying — but it does appear in `currently_overdue` while it waits. (3) `paid_on_time_share` is divided by every settled deal, not only the paid ones, so a brand that paid none of three reads 0.0 rather than reporting no figure at all. `median_days_to_pay` stays null in that case, because "pays in 0 days" would be a lie in the brand's favour. (4) **`null` means "not enough to say" and must never be rendered as zero**; this is written into the endpoint description because the two mean opposite things. (5) **Open: whether this record should be public.** It is behind a login for now. Publishing a business's payment failures to the open internet is a different question from showing them to the people being asked to take the risk, and it cannot be undone once done. (6) Deadlines and on-time judgements are read on Tamil Nadu's calendar (D-030 point 1): 19:00 UTC on the due date is already the next morning in India, and reading the server's clock would quietly credit a brand with a day it did not have.

## D-035: The dispute record, and the shape of not judging
- Date: 2026-09-20
- Approved by: Adhi
- Context: D-028 set the posture — either side raises a dispute, the other has 7 days to respond with evidence, outcomes are `resolved_paid`, `resolved_withdrawn`, `resolved_informally` or `unresolved` after 30 days, and either party can export the timeline. Building it needed the tables and the rules that keep that posture honest.
- Options considered: A) One dispute row with a stored state · B) A dispute row plus a dated timeline of entries from both sides, with the state derived
- Chosen: B. Tables `dispute` (one per payment record) and `dispute_event` (the timeline).
- Reason: The timeline **is** the product here. A dispute with only a current state tells a creator nothing they can take to the other party; a dated account of what each side said, in order, is the thing that has value precisely because we are not the judge. `unresolved` is derived for the same reason as every other timer in this codebase: nobody does it, it is what 30 days of nothing looks like, and storing it would need a job runner we have not chosen and could go stale.
- Consequences / follow-ups: (1) **An open dispute holds a payment at `late` rather than letting it harden into `unpaid`**, in both the payment record and the brand's reliability record. A payment somebody is actively arguing about is not the same as one nobody will discuss, and marking a brand a non-payer mid-argument would be us taking the side we said we would not take. Once a dispute times out it stops holding the payment, so the shield cannot be used indefinitely. (2) **A late account is still accepted** — after the response window and after the 30 days — because refusing it would make the record less true rather than more orderly. Nothing is added once an outcome is agreed. (3) **Either side may close it, including long after it timed out**, because most of these end with a phone call and the record should be allowed to catch up with what really happened. (4) **Evidence is a link, not a file.** D-028 expects screenshots; where uploaded files live is still open. Rather than guess at storage we cannot change later, an entry carries a link the person already has, and a file reference joins the table beside it when media storage is decided. (5) A test asserts no outcome names a guilty party, so that if a verdict ever creeps in, it fails here. (6) Disputes and their timelines are in the data export, because D-028 promised that; the export completeness test failed the moment the tables appeared, which is what it is for. (7) `app/core/clock.py` now holds the Indian calendar, moved out of `payment_status` when the dispute timer became its second user.

## D-036: Nobody is on the public Creator Passport until they choose to be
- Date: 2026-09-21
- Approved by: Adhi
- Context: The public Creator Passport shipped on 20 September with every profile publishable and no way for a creator to say no. It was recorded at the time as the one thing that had to land before the endpoint could be deployed. The column belonged to the Data track and had not been started, so Adhi took it over.
- Options considered: A) Published by default, with an opt-out · B) Not published until the creator turns it on · C) Published by default for existing creators, opt-in for new ones
- Chosen: B. A nullable `creator.passport_published_at`, NULL for everybody, with `POST /api/v1/creators/me/passport/publish` and `.../unpublish`.
- Reason: The decision was settled by one fact — **nothing is deployed and there are no real creators yet, so the safe default is free.** Publishing somebody cannot be undone once search engines have seen it; publishing them later, once they have said yes, costs nothing. A creator who signed up to browse campaigns has not asked to be findable by strangers, and the marketplace category defaulting to public is not a reason to decide it for them. If the validation pack later says explicit consent is required under DPDP, we are already compliant; had we defaulted the other way, we would have had profiles in a search index we could not recall.
- Consequences / follow-ups: (1) **A timestamp, not a boolean**, because it is the consent itself: it records that the creator chose and when, and it is included in their own data export for that reason. (2) **Publishing twice keeps the first date.** A second tap on a slow connection is not a second decision, and rewriting the consent date would falsify the record. (3) **Withdrawing is never refused** and takes the page down at once. Somebody who wants to stop being findable should not have to argue with us. (4) An unpublished handle returns exactly the same 404 as a handle nobody has taken, so the page cannot be used to work out who chose not to be listed. (5) Publishing is its own action rather than a field on the profile update, so the moment of consent is a single auditable call (backend.md section 2). (6) **The Passport is now deployable.** This was the last thing blocking it. (7) The growth argument for defaulting to public is real but belongs at sign-up, as a clear question, not as a default nobody was asked about.

## D-037: Lint, format, strict type checking and coverage, enforced in CI
- Date: 2026-09-21
- Approved by: Adhi. Proposed at the end of the 20 September session ("coverage, strict type checking, and lint in CI"), approved there ("carry with the follow"), and confirmed on 21 September ("do the instruction"). **Erode Harish is informed through the 21 September report**, because the formatting and a few lint fixes touch Data-track files (see consequence 6).
- Context: `backend.md` section 10 named ruff and mypy but left adopting them as an open decision, and `testing.md` listed lint, type-check and coverage gates as "once approved". Each tool is a new dependency (CLAUDE.md section 5).
- Options considered: A) ruff for lint and format, mypy in strict mode, pytest-cov, all pinned in `requirements.txt` and enforced in CI · B) flake8, black and isort, with pyright · C) no tools; keep reviewing by eye
- Chosen: A
- Reason: One fast tool replaces three for lint and format, and mypy is the checker `backend.md` already names. The tools earned their place on first run: mypy found that **all four list endpoints silently dropped rows sharing a timestamp with the last row of a page** (a Python tuple comparison where a SQL row comparison was meant; fixed, with a failing test first), and ruff found 16 safety checks written as `assert`, which Python removes under `-O`.
- Consequences / follow-ups: (1) `requirements.txt` gains `ruff==0.16.8`, `mypy==2.3.1` and `pytest-cov==7.1.0`; everyone runs `pip install -r requirements.txt` again. `pip-audit` finds no known vulnerabilities in the new set. (2) CI now blocks merge on `ruff check`, `ruff format --check`, `mypy`, 80% overall coverage and 90% for every `service.py` (branches counted, which is stricter than lines alone). Measured today: 97% overall, lowest service 90.6%. (3) Every relaxation is written down with its reason in `pyproject.toml` or next to the line it applies to: two mypy options, untyped calls into redis, four `type: ignore` on Starlette handler registration, three `noqa: S105` on constants that are not secrets, one `noqa: S311` on seeded fake data. (4) The repository is reformatted once, in its own commit, listed in `.git-blame-ignore-revs` so `git blame` skips it. (5) The API contract did not change: the OpenAPI document is byte-identical before and after. (6) Data-track files changed only mechanically (import order, the `UTC` alias, lint comments, formatting), with no schema change (`alembic check` clean): `app/db/models.py`, `app/modules/auth/models/creator.py`, `app/modules/auth/models/auth_session.py`, `app/modules/deal_memo/proof_models.py`, `alembic/env.py`, `scripts/seed_dev_data.py`, `scripts/measure_performance.py`.

## D-038: The creator delivery record, and what it counts
- Date: 2026-09-21
- Approved by: Adhi, for the feature: proposed on 20 September as the highest-value next build (`docs/COMPETITIVE_LANDSCAPE.md` section 6), approved there ("carry with the follow") and confirmed on 21 September ("do the instruction"). The rules below apply decisions Adhi already approved (D-025, D-026, D-027, D-034). **The three open points at the end are not decided** and need a founder.
- Context: We built a brand payment record (D-034) and not its mirror. A brand choosing between creators has the same problem a creator has choosing between brands, and prices every creator as risky when it cannot tell them apart. Every fact the record needs is already stored, so it needs no new table.
- Options considered: A) Mirror D-034: worked out from what happened, to the same three rules, behind a login · B) Ratings or reviews written by brands · C) Wait until link re-checks exist
- Chosen: A. `GET /api/v1/creators/{creator_id}/delivery-record`.
- Reason: Reviews are opinions, easily inflated and easily used as leverage. The record is built from dated facts both sides already see. B would also hand brands a way to punish a creator for a dispute about money. C would delay the most useful half for a part (takedown checks) that is only one signal among several.
- Consequences / follow-ups: (1) **Not delivered** means cancelled by the creator after work had started (D-026), or nothing delivered 14 days after the agreed date, the same 14 days a brand gets before late becomes unpaid (D-027). The second one counts whether or not anybody complained: silence cannot launder it. (2) **Not counted:** `withdrawn_early`, cancellations by the brand, and the brand asking for changes. None of them is the creator's doing. (3) **On time** is judged by the creator's first submission, not the brand's approval, on Tamil Nadu's calendar. A deal with no agreed date cannot be late. (4) Work that approved itself because the brand never reviewed it (D-025) counts as delivered, even before anybody reads it again. (5) **Barter is shown and never scored** (D-026): barter outcomes have their own counts and stay out of `currently_overdue`, so a free-product trial is not weighed like a paid deal and cannot be used to hide one either. (6) `disclosure_confirmed_share` is the creator's own statement that the disclosure was on the post, not our judgement of ASCI compliance (D-024). (7) **Who may read it:** any brand, and the creator themself. Not other creators, because a creator is a person rather than a business. Not public. A creator asking about someone else is refused before the id is even looked up, so the endpoint cannot be used to find out which ids exist. (8) The figures are withheld below three completed deals, and `currently_overdue` is reported always (D-034). (9) Two queries, whatever the number of deals (tested). p95 was 12.3 ms locally with 50 deals, against a 300 ms budget. (10) **Deliberately left out:** `content_removed_on`, because nothing writes it until the link re-check job exists (D-024), and reporting "0 takedowns" would claim checks we never ran. Revision counts are also left out, because asking for changes is the brand's call.
- **Open, for a founder:** (a) **Deals with no agreed date are a hiding place.** A creator who accepts one and never delivers is only counted if they cancel. The fix is either making `content_due_on` required on paid memos or giving undated deals a default window. Both are product decisions, so neither was guessed. (b) Whether this record, like the brand record (D-034 point 5), should ever be public. (c) It is a record about an individual, so how long it is kept and whether a creator can contest an entry are DPDP questions for the validation pack. None was invented here.

## D-039: A scored deal needs an agreed date before it is sent
- Date: 2026-09-21
- Approved by: Adhi, in this session, choosing the recommended option
- Context: D-038 point (a). With `content_due_on` optional, a creator who accepted an undated deal and never delivered could only ever be counted if they cancelled. The delivery record had a hiding place.
- Options considered: A) A paid, commission or local-business memo cannot be sent without an agreed date; barter stays optional · B) Undated deals count as due 30 days after acceptance, for the record only · C) Leave the gap open
- Chosen: A
- Reason: A date both sides agreed protects both of them: the brand knows when to expect the work, and the creator knows exactly what "late" means. B would hold creators to a deadline nobody agreed to. It is a check in the API, not a database change.
- Consequences / follow-ups: (1) Sending a paid, commission or local-business memo without `content_due_on` is refused: 409 `memo_needs_due_date`. Barter may still leave it empty, consistent with barter never being scored (D-026). (2) **The date cannot already be in the past**, checked when the brand sends and again when the creator accepts, on Tamil Nadu's calendar: 409 `due_date_has_passed`. Accepting a passed date would make a creator overdue on the day they said yes. They can still ask for a new date. (3) Removing the date during a change request blocks the resend, so the rule cannot be dodged. (4) Commission memos need a date even though they need no fee: the fee rule (`FEE_REQUIRED_TYPES` in `deal_memo/service.py`) is about money, this one is about delivery. (5) Resolves D-038 point (a). Points (b) and (c) stay open.

## D-040: Every write outside login is safe to retry
- Date: 2026-09-21
- Approved by: Adhi, in this session, choosing the recommended option
- Context: `Idempotency-Key` protected only applications, payments and disputes. On patchy mobile data a request often succeeds while its reply is lost, and the app sends it again. For the other 24 writes that retry either did the work twice (a second campaign) or came back as a false 409: "this application already has a deal memo", "this memo already has proof waiting", "this account already has a profile". Each test in `tests/modules/test_retry_safety_api.py` showed exactly that before the change.
- Options considered: A) Every `POST` and `PATCH` outside login, now · B) Only the endpoints that create rows · C) Leave it as it was
- Chosen: A
- Reason: The false "already done" error is as damaging as a duplicate, because it tells someone their action failed when it worked, and B leaves those in place. The mechanism already existed and was tested (`a946a92`, 20 September), so it is one line per router.
- Consequences / follow-ups: (1) Profiles, Passport publishing, campaigns, deal memos, proof and notifications now honour the header, 24 operations in all. Requests without it behave exactly as before (tested). (2) **A test walks the whole OpenAPI document and fails if any `POST` or `PATCH` outside `/api/v1/auth/` lacks the header**, so a new endpoint cannot be added without it. (3) **Login is not covered.** Replaying a one-time-code check or a token refresh is a security question with its own trade-offs (`security.md`), and needs its own decision. (4) The API contract changed only by that header and its documented 503; verified operation by operation. (5) `backend.md` section 2 now states the rule.

## D-041: Application feedback states facts, and names no pattern it cannot support
- Date: 2026-09-21
- Approved by: Adhi, in this session, after seeing the three points below
- Context: Backlog C4, "no campaigns, no idea why". `GET /api/v1/applications/me/feedback` shows a creator the pattern behind their applications: rejections by reason, quotes above the campaign's own maximum budget, and open campaigns in their niches they can still apply to. How it words what it cannot know decides whether it helps or misleads.
- Options considered: A) Name the most common reason from any number of rejections, list profile "gaps" to fix · B) Name it only from three rejections and never on a tie, and report profile facts plainly
- Chosen: B
- Reason: (1) **One or two rejections are not a pattern.** Three is the floor the brand and creator records already use (D-027, D-034, D-038). (2) **A tie names no reason**, because picking one of two equal counts would invent a pattern. (3) **Bio and Passport are facts, not gaps.** Publishing the Passport is the creator's choice (D-036), and a "fix this" list would push them out of it.
- Consequences / follow-ups: (1) `most_common_reason` is null below three rejections or on a tie, documented as "no pattern yet", not "no problem". (2) Quotes are compared only where a quote and a stated maximum both exist; the rest are left out, not counted as fine. (3) Open-campaign counts leave out campaigns past their closing date and campaigns already applied to. (4) Every status and every reason key is always present, zeros included. (5) The API returns facts; the words belong to the frontend, in Tamil and English (ux.md).

## D-042: Rate card visibility, audience numbers, and the record beside the price
- Date: 2026-09-21
- Approved by: Adhi ("do research and go with best"), on decisions 2–4 of `docs/PROPOSAL_PASSPORT_RATE_CARD.md`. **Decision 1, the schema, is not covered**: it is Erode Harish's track and needs both founders.
- Context: The rate card and media kit proposal, the top build in `docs/COMPETITIVE_LANDSCAPE.md` section 6, left three product questions. Each was researched before choosing.
- Options considered: (2) prices public by default, or visible to brands with the public page on consent · (3) self-reported audience numbers shown publicly, brands only, or public links with numbers for brands · (4) the delivery record beside the price, or on a separate screen
- Chosen: (2) Brands always see prices; the public page only after the creator switches it on, a consent timestamp like D-036. (3) **The public page shows links to the channels, never our copy of a count**; signed-in brands see the numbers labelled "self-reported" with their date. (4) The brand's media kit shows the delivery record beside the packages; the records are **never merged into a single score**.
- Reason: (2) 73–78% of brands prefer creators with published rates, and nano and micro creators gain most from publishing them. So the sign-up screen asks plainly. But DPDP is consent-first, and publishing cannot be undone once indexed, so it is never a default. (3) Follower counts are the easiest number to inflate, and about two in three Indian creators show inflation. Republishing an unverifiable count under our name would lend it our credibility; a link lets anyone check the real number at the source. Other platforms' "verified" labels often mean far less than they suggest, so the word is not used here for self-reported figures. (4) The record beside the price is the one thing no competitor can show. Averaging several signals into one score hides the risk a brand most needs to see.
- Consequences / follow-ups: (1) The schema in the proposal is unchanged by these answers; it still waits on decision 1. (2) The public Passport's contract test must prove no follower or view count ever appears in it. (3) Verified figures, when they come (competitive landscape #6), need their own decision on what "verified" is allowed to mean.

## D-043: Marking many payments as sent at once, each row on its own
- Date: 2026-09-21
- Approved by: Adhi ("do research and go with best"), choosing competitive landscape item #3 and delegating the design to the research
- Context: A brand paying several creators goes through its bank's bulk transfer, which returns one reference (UTR or RRN) per row and may reject some rows while others go through. Recording each payment one by one is slow, and it is where a busy brand would stop keeping the record at all. Reelax offers bulk payouts by moving the money; we never do (constraint 1).
- Options considered: A) All-or-nothing: one bad row refuses the whole request · B) Each row recorded or refused on its own, with results in input order · C) Background processing with a job to poll
- Chosen: B. `POST /api/v1/brands/me/payments/mark-paid`, 1 to 25 rows.
- Reason: Bank bulk transfers already behave row by row, and most production APIs choose per-row results for batches. All-or-nothing would let one typo hold back other creators' notice that their money is on its way. C is for thousands of rows; a pilot brand pays a handful, and no job runner is chosen yet.
- Consequences / follow-ups: (1) **Every row makes exactly the change of the single endpoint** (`_record_marked_paid`): the same row lock, checks and creator notification, and a refused row carries the same problem code a single request would get. (2) Each row runs in its own savepoint and the recorded rows commit together once at the end, so a refused row undoes only its own changes, and an unexpected failure leaves none recorded rather than some. (3) Request-level problems (no rows, more than 25, a deal listed twice, an unusable method or reference length) refuse the whole request with 422 before anything is touched. (4) Another brand's deal is refused as `memo_not_found`, never revealed. (5) Retry-safe: the same Idempotency-Key replays the original answer, and the creator is notified once (tested). (6) Limited to 10 requests a minute. Measured: 25 rows at p95 238 ms against the 500 ms write budget, which is why the limit is 25. (7) Matching the reference against the creator's own bank record (an RRN the creator types in) is a separate step and would need a column: Data track.

## D-044: Which websites may call the API, the docs off in production, and only known environments
- Date: 2026-09-22
- Approved by: Adhi (chose option A in session, after seeing the proposal, including the preflight point below)
- Context: Two open items in `docs/standards/security.md`: section 7 asks for an explicit CORS allow-list and there was none; section 9 asks for `/docs` exposure to be decided before production. `ENVIRONMENT` also accepted any text, although it decides HSTS and the OTP sender, and would now decide the docs too. All three are needed before any frontend or deployment.
- Options considered: A) All three now: known environments only, a CORS allow-list, and `/docs`, `/redoc` and `/openapi.json` off in production · B) The CORS allow-list only, and decide on the docs at deployment
- Chosen: A.
- Reason: Each is small now and must exist before launch. Every mistake fails closed: a typo stops the app, a missing allow-list blocks browsers rather than opening to them, and docs off in production cannot leak the map of every endpoint. B would leave a checklist item open and the environment typo in place.
- Consequences / follow-ups: (1) `ENVIRONMENT` must be `local`, `test`, `staging` or `production`; anything else stops the app. (2) New setting `CORS_ALLOWED_ORIGINS`, comma separated, **empty by default, so no website may call the API from a browser** until one is listed. Each entry must be written exactly as a browser sends it (no path, no trailing slash, lower case, no default port), never `*`, and `https://` outside local and test; the app refuses to start otherwise and names the form to write. (3) No cookies are allowed across sites (the API uses bearer tokens), and a browser may send and read only our real headers. The mobile app is unaffected: CORS is a browser rule. (4) CORS sits outside the rate limiter, so a 429 or 413 still reaches the dashboard readably instead of as an opaque browser error. The browser's preflight check is answered there, before the limiter. This removes no protection: slowapi 0.1.9 already skips every request with no matching route, which includes every `OPTIONS` request today. A preflight touches no database and no data. (5) In production `/docs`, `/redoc` and `/openapi.json` answer 404; local, test and staging keep them. The frontend builds from the committed `docs/api/openapi.json`. (6) `.env.example` documents the new setting.

## D-045: An unexpected error is answered inside the middleware, so it gets every header
- Date: 2026-09-22
- Approved by: Adhi (chose option A in session, after seeing the proposal)
- Context: Found while building D-044. Starlette runs a handler registered for `Exception` in its outermost layer, outside every middleware we add. Measured on the real app: a 500 carried no `Content-Security-Policy` and no `X-Content-Type-Options`, while a 404 and a 200 had both, although `security.md` section 7 asks for them on every response. With CORS on, a 500 would also lack the permission a browser needs, so the dashboard would see a bare "network error", indistinguishable from a dropped connection, with no request ID to quote.
- Options considered: A) A small layer inside the security headers, request ID and CORS that turns an unexpected error into the usual 500 answer · B) Leave 500s as they are
- Chosen: A.
- Reason: The 500 is the answer the dashboard most needs to read: after a failed "mark paid", a person must know it failed on our side, and support needs the request ID to find it. The fix is small, adds no package, and changes no body or log line.
- Consequences / follow-ups: (1) `app/core/unexpected_error.py` calls the same handler as before (`handle_unexpected_error`), so the body, the generic message and the log line are unchanged. (2) It sits outside the rate limiter and body limit, so a failure inside them (Redis down, for example) is caught too. (3) The handler stays registered for `Exception` as a backstop for anything that fails outside the layer. (4) Once an answer has started going out, the error is passed on unchanged, since a 500 can no longer replace half an answer. The API has no streamed answers today.
