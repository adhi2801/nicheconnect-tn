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
