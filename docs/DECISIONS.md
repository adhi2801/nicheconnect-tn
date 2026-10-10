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

## D-047: The technology baseline, and upgrading when something better comes
- Date: 2026-09-22
- Approved by: Adhi and Erode Harish. Adhi approved in this session ("lock in these as thing we use and in future if a new thing comes and that will help us we need upgrade") after seeing section 4 of `docs/PLATFORM_AND_TECH_PLAN.md`, researched against 22 September 2026 releases. **Erode Harish's approval was relayed by Adhi later in the same session** ("he has approved"), covering the items that needed him: his track and the choices `CLAUDE.md` gives to both founders. D-046 (three platforms, both roles on each) is a separate decision and is not covered here.
- Context: Adhi's standing order is that every layer uses the best current technology and stays clearly ahead of every competitor. Section 4 of the plan lists, for each layer, what we run and what is current. He asked to lock those in as what we use, with a rule that keeps them current.
- Options considered: A) Lock the baseline and adopt a standing upgrade rule Â· B) Choose tools one at a time as each is needed, with no baseline Â· C) Move to the newest release of everything as soon as it ships
- Chosen: A.
- Reason: With a baseline, nobody re-argues settled choices, and every session builds on the same stack. Under B, choices drift between sessions and founders. C chases novelty: betas and release candidates break things, and a benchmark win often disappears on an API that waits on its database. The rule adopts new things once they are proven to help us, which is what "best" means in practice.
- Consequences / follow-ups: (1) **The baseline** is the table in section 4.0 of the plan. Locked: current library versions (4.1) including httpx2; Schemathesis; current CI action versions pinned to commit SHAs, with zizmor; OpenTelemetry as the tracing standard; mypy (strict), ruff, pytest and uvicorn kept. Locked with Erode Harish's approval: Python 3.14 and uv; PostgreSQL 18 with UUIDv7 for new tables; Valkey 9.1; hybrid Tamil search in Postgres; Squawk; DBOS; the AI layer; the frontend stack. (2) **The upgrade rule.** A new tool, version or model replaces a baseline item when all four hold: it is stable (not a beta, release candidate or origin trial); it is maintained; it measurably helps us on our own tests, benchmarks or Tamil test set (faster, safer, cheaper, or better for users); and it keeps every constraint in `CLAUDE.md` section 2. **Security fixes do not wait for the review**: they are applied as soon as they pass the tests. (3) **How an upgrade happens:** on its own branch, with the full suite green and before-and-after numbers when speed or cost is the reason. The other founder reviews the pull request. The plan's row and its "last checked" date are updated, and a new decision entry is written whenever a baseline item changes. The approval gates in `CLAUDE.md` section 5 still apply: "locked" never means "installed without asking". (4) **Watching:** the monthly review (plan section 9) checks each layer against current releases, and so does every session that touches that layer. Anything better becomes a DECISION NEEDED, never a silent change. Items not ready yet stay on the Watch list with the condition that would make us adopt them. (5) Still open, not locked: hosting, where traces go, the login provider, the lint tool (Biome or Oxlint), the API client generator (Hey API or Orval), and the Tamil fonts (chosen by testing). (6) Locking a choice does not carry it out. Each locked item is still built on its own branch, one file at a time. (7) A one-line rule in `CLAUDE.md` binds every session to this. Both founders approved it with the rest.

## D-048: Valkey replaces Redis for the cache and rate limits
- Date: 2026-09-23
- Approved by: Adhi and Erode Harish. Adhi approved in this session, after being shown the baseline gap ("need everything to be in the locked d-047 stage the best"). **Erode Harish's approval was relayed by Adhi in the same session** ("harish has confirm everything"), as with D-047. His own confirmation of the section 0 notice is still outstanding and should be recorded in the report for the day he gives it.
- Context: D-047 locked "Valkey 9.1.2 or newer" as the cache and rate-limit store, but locking a choice does not carry it out. We were still running `redis:7-alpine` on a floating tag, two major versions behind either option.
- Options considered: A) Valkey 9.1.2 on an exact tag Â· B) Redis 8 Â· C) Stay on Redis 7
- Chosen: A.
- Reason: Valkey is the Linux Foundation fork under a BSD licence, where Redis 8 is AGPL; 9.1 is up to 17% faster, and 9.1.1 fixed critical TLS and stream bugs. It speaks the same protocol, so nothing in the application changes. C leaves us on an unmaintained major with a tag that can move under us.
- Consequences / follow-ups: (1) **Nothing in the application changed.** The service is still named `redis` in `docker-compose.yml` and in CI, so `REDIS_URL`, `.env`, `.env.example` and every connection string stay exactly as they are. redis-py speaks to Valkey unchanged. (2) The tag is exact, `valkey/valkey:9.1.2-alpine`, which is also the D-047 "exact version tags" row for this service. The Postgres image is still on a floating `pgvector/pgvector:pg16` tag; pinning it belongs with the PostgreSQL 18 upgrade, which is the Data track's. (3) A healthcheck was added locally, using `valkey-cli ping`, so `docker compose up` matches what CI already did. (4) **Verified in this session against a real Valkey 9.1.2 container**, not against Redis: the whole suite, 1170 passed and 5 skipped, including the 45 rate-limit-storage and idempotency tests that are the only ones that touch it. The container reports `server_name:valkey`, `valkey_version:9.1.2`, and `redis_version:7.2.4` as its compatibility shim. (5) **Not a data migration.** The store holds rate-limit counters and idempotency records, both short-lived and rebuilt on use, so the old container was removed rather than migrated. Anything running against a shared store must restart onto the new one. (6) Section 4.2 of the plan is updated to say this is built.

## D-049: PostgreSQL 18 with pgvector 0.8.6, on exact image tags
- Date: 2026-09-23
- Approved by: Adhi and Erode Harish. Adhi approved in this session ("need everything to be in the locked d-047 stage the best", then "carry on go on" after being offered this specific item). **Erode Harish's approval was relayed by Adhi in the same session** ("harish has confirm everything"), as with D-047 and D-048. His own confirmation of the section 0 notice is still outstanding. The database is his track: this was built by Adhi's session because he had confirmed and the work was blocking, and it is his to review on the pull request.
- Context: D-047 locked PostgreSQL 18, UUIDv7 for new tables, exact image tags and pgvector 0.8.2 or newer, but none of it was carried out. We were running 16.15 on a floating `pgvector/pgvector:pg16` tag.
- Options considered: A) 18 now on an exact tag, new volume Â· B) 18 now, reusing the existing volume via `pg_upgrade` Â· C) Wait for 19 (final targeted end of October 2026)
- Chosen: A.
- Reason: 18 brings asynchronous I/O, native `uuidv7()` and statistics that survive an upgrade. B buys nothing here, because the only local data was 13 throwaway OTP rows and CI starts empty every run. C leaves a floating tag and an unpinned pgvector in place for another month, and 19 is not to be adopted until its first minor update anyway.
- Consequences / follow-ups: (1) **The image tag is `pgvector/pgvector:0.8.6-pg18-trixie`**, exact in both versions. This also settles the "exact version tags" row for this service, and the pgvector row: **CVE-2026-3172 (CVSS 8.1) affects pgvector 0.6.0 to 0.8.1**, and 0.8.6 is clear of it. Nothing below 0.8.2 may be deployed anywhere, including hosting. (2) **The mount point had to move, and this is a real breaking change in the image.** From 18 the volume is mounted at `/var/lib/postgresql`, not `/var/lib/postgresql/data`; the image keeps data in a major-version subdirectory so `pg_upgrade --link` can work without crossing a mount boundary. Mounting the old path makes 18 refuse to start (docker-library/postgres#1259). Anyone whose container will not start should check this first. (3) **Nothing was destroyed.** 18 uses a new volume, `db_data_pg18`; the 16 volume `db_data` is left in place, so reverting is only reverting the file. Remove the old one by hand once happy: `docker volume rm nicheconnect-tn_db_data`. (4) **Every developer recreates their local database**: `docker compose up -d` then `alembic upgrade head`. A 16 data directory cannot be read by 18. (5) **Verified in this session on a real 18.6 container:** all 20 migrations apply, downgrade to base and reapply cleanly (testing.md gate 4); `alembic check` reports no drift; the whole suite is 1170 passed, 5 skipped; mypy and ruff clean. `SELECT uuidv7()` works natively and pgvector reports 0.8.6. (6) **UUIDv7 is available but nothing uses it yet.** D-047 locks it for **new** tables only; existing tables keep `gen_random_uuid()` and are not rewritten. The first new table should use `uuidv7()` as its default, and that is the Data track's to apply. (7) The suite ran in 58s against 18 where it took 67s against 16. That is one wall-clock observation on a laptop, not a benchmark, and no performance claim is made from it.

## D-050: Squawk lints the migrations a branch adds, not the whole chain
- Date: 2026-09-23
- Approved by: Adhi and Erode Harish. Adhi approved in this session ("need everything to be in the locked d-047 stage the best", then "carry on go on"). **Erode Harish's approval was relayed by Adhi in the same session** ("harish has confirm everything"), as with D-047, D-048 and D-049. Migrations are his track: the check is wired here, and which rules it enforces is left to him where it changes how he writes them.
- Context: D-047 locked Squawk to lint each migration's SQL for table locks and downtime before it merges. Nothing was wired up. Running it over the whole chain for the first time found 47 issues across the 20 migrations already on `main`.
- Options considered: A) Lint only the migrations a branch adds Â· B) Lint the whole chain every run Â· C) Lint the whole chain but exclude every rule that currently fires
- Chosen: A.
- Reason: B is red on day one over 47 findings in migrations that are already applied and cannot be changed without new ones, and a check that is loud about things nobody can fix is a check everyone learns to skip. C keeps the noise out but disarms the tool. A asks the only question that can still be answered: is the migration *being added* safe?
- Consequences / follow-ups: (1) `scripts/lint_new_migrations.py` diffs against `origin/main`, takes each added migration's `revision` and `down_revision`, has Alembic emit just that migration's SQL offline, and runs Squawk on it. No database is needed. It exits 0 when a branch adds no migration, which is most branches. (2) CI runs it before applying migrations, and `actions/checkout` now uses `fetch-depth: 0`, because diffing against `origin/main` needs more than one commit of history. (3) `.squawk.toml` lists every excluded rule with its reason. `prefer-robust-stmts` is off because Alembic already tracks what has run, and writing every statement as `IF NOT EXISTS` would hide a genuine conflict behind a silent no-op. `prefer-text-field` and the two integer-width rules are off because they are one schema-wide decision for the Data track, not something a branch adding one table can answer: 34 of the 47 findings are `VARCHAR(n)` columns Squawk would rather were `TEXT` with a `CHECK`. (4) **Open, and Erode Harish's to decide:** `require-lock-timeout` and `require-statement-timeout` are excluded *only* because enabling them changes how migrations are written. Alembic emits no timeouts, so a migration needing a lock can queue behind a long query and hold the table shut while it waits. The fix is two lines at the top of each migration, or once in `alembic/env.py`, which is his file. When he chooses, delete those two lines from `.squawk.toml`. (5) **It already found a real one.** Migration `c3b81e47af20` adds a `CHECK` constraint to the existing `notification` table without `NOT VALID`, which takes a full table scan and blocks writes for its duration. Harmless here because it ran on an empty table and we have not deployed, but the pattern is the one to avoid: new constraints on a populated table want `NOT VALID` and a later `VALIDATE CONSTRAINT`. (6) Verified in this session: against `origin/main` it reports nothing to check and exits 0; against a ref three migrations back it passes two and fails the third on exactly that constraint. 1170 passed, 5 skipped; mypy, ruff and zizmor clean.

## D-051: Adhi builds the whole backend; the two-track split goes dormant
- Date: 2026-09-23
- Approved by: Adhi, in this session ("he reviewed everything and i am doing the full backend related stuff all mine because i am doing the whole backend"). **Erode Harish's review and his confirmation of the section 0 notice were relayed by Adhi**, not given in a session here, as with D-047 and D-048 to D-050.
- Context: The repository was set up for two founders working in separate tracks, with an open notice in `CLAUDE.md` section 0 carrying nine unanswered asks to Erode Harish. Every merge to `main` waited on his review, and eight branches were queued behind it. Adhi states he is now building the backend alone.
- Options considered: A) Record it: Adhi owns both tracks, the overlap rules go dormant, everything else stays Â· B) Delete the two-track structure from `CLAUDE.md` entirely Â· C) Leave the structure as written and keep routing Data-track work to Erode Harish
- Chosen: A.
- Reason: C was blocking real work against a reviewer who is not reviewing. B throws away a structure that is correct whenever the second founder is building, and it would have to be rewritten from memory to bring back. A unblocks the work and keeps the rules recoverable.
- Consequences / follow-ups: (1) **Adhi approves and owns every backend area**, the Data track included: `app/db/`, `app/modules/*/models*`, `alembic/`, seed scripts and query performance. (2) **The overlap rules are dormant, not deleted**, and apply again the moment Erode Harish picks work back up. The migration rule still binds whoever is working: one new migration in flight at a time, so the chain cannot fork. (3) **One owner is not no process.** The approval gates in section 5, this log, and the definition of done all apply unchanged. (4) **Review honesty.** Section 6 expects a second founder to review every merge. While one person builds, each pull request and each report must say the work has not had a second pair of eyes, rather than letting "reviewed" be assumed. This is the real cost of the change and it should not be quiet. (5) The section 0 notice is closed and folded away as a record rather than deleted, so what was settled on 21 to 23 September is still readable. (6) **Now unblocked by this decision:** the two Squawk timeout rules held for the Data track (D-050 point 4), UUIDv7 on the first new table (D-049 point 6), uv and Python 3.14, and the `VARCHAR` versus `TEXT` schema question behind 34 of the pre-existing Squawk findings. Each still needs its own decision; this one only removes "waiting for the other founder" as the reason none of them has been made. (7) **Still not decided, and not made so by this:** the Colyv rename and dropping Tamil. Both change shared files and the product's stated position, both were asked for on 23 September, and neither has a decision entry yet.

## D-052: Phase D starts — Qwen3 embeddings, two tables, no vector index
- Date: 2026-09-23
- Approved by: Adhi, in this session. He read `docs/PROPOSAL_MATCHING.md`, including the measured cost of the dependency, and told Claude to decide rather than keep asking ("i said go with what you feel the best is"). The recommendations in that document are therefore adopted as written. **Not reviewed by Erode Harish** (D-051).
- Context: `app/modules/matching/` was an empty package. Phase D was the only phase with nothing in it, while `docs/COMPETITIVE_LANDSCAPE.md` rests the product's whole position on it: competitors let a brand filter a list, we claim to match. pgvector 0.8.6 was pinned and available (D-049) and unused.
- Options considered: A) Qwen3-Embedding-0.6B, two derived tables, exact search Â· B) A larger model (llama-embed-nemotron-8b, KaLM-Gemma3-12B) Â· C) An embedding API instead of a local model Â· D) Vectors as columns on `creator` and `campaign`, with an HNSW index from the start
- Chosen: A.
- Reason: Qwen3-Embedding-0.6B carries the best MTEB score per parameter by a distance (64.34 at 0.6B, against 72.32 at 11.8B for the ceiling model) and runs beside the API. It is multilingual, so choosing it does **not** depend on settling English-only first, which matters while that has no decision entry. B is better and far too heavy for a pilot. C sends creator profile text off our infrastructure for a per-call fee. D drags a 4 KB vector into every `SELECT creator` and builds an index for a recall problem we do not have.
- Consequences / follow-ups: (1) **Two tables, `creator_embedding` and `campaign_embedding`**, keyed by the row they describe, `ON DELETE CASCADE`. An embedding is derived data: losing every row costs a rebuild, not data, and it must never be the reason a deletion is refused. `source_hash` lets a rebuild skip rows whose input did not change; `model` lets two models coexist while one replaces the other. (2) **No UUIDv7 default**, although D-049 locks it for new tables: neither table generates an id, because the primary key is the foreign key. (3) **No vector index, deliberately.** Matching filters structurally first — city, niche, budget, status — and ranks by similarity inside that result, which at pilot scale leaves tens of rows. An exact scan over tens of vectors beats an index lookup and is always exactly right, where an approximate index is not. **The trigger to add HNSW is a measured p95 over the 300 ms read budget in `docs/PERFORMANCE.md`, not a hunch.** (4) **1024 dimensions**, the model's native width, fixed in the column rather than configurable because changing it is a migration. Matryoshka truncation can narrow it later without retraining. (5) **The dependency is not added yet.** Measured: a plain `pip install sentence-transformers` pulls about 2.0 GB on Linux, roughly 1.4 GB of it CUDA for a workload that will never touch a GPU. When it is added it must come from PyTorch's CPU index, in its own requirements file with its own CI job, because `pip-audit --strict` over torch's tree will fail a build one day. (6) **Constraint 2 is enforced in `embedding_input.py`, not here.** That module refuses to declare a field whose name looks private and fails closed when a new column appears; this migration only stores the result. (7) Both tables are declared in `NOT_EXPORTED` with a reason a person can read: everything the numbers were built from is already in their export in words, and the numbers are rebuilt from those words. **Whether that is the right answer under DPDP is a validation-pack question** (constraint 6) and is not decided here. (8) Verified in this session: the migration applies, downgrades and reapplies; `alembic check` reports no drift; 22 matching tests including a real `cosine_distance` query, which is what proves the extension is live; 1200 passed overall.

## D-053: Design research runs in parallel; frontend code still waits (amends D-004)
- Date: 2026-09-23
- Approved by: Adhi, in this session ("i am doing whole backend he started frontend ideas and design process like research work on frontend"), having told Claude to decide rather than keep asking. **Not reviewed by Erode Harish** (D-051), although it describes what he is doing.
- Context: D-004 chose "complete the backend first, then UI/UX design, web dashboard and mobile app". Erode Harish has in fact started frontend research and design. That is a departure from a recorded decision, and leaving it unrecorded would mean the log no longer describes what the team does — which is worse than amending it.
- Options considered: A) Amend D-004: design research in parallel, frontend code still gated Â· B) Hold D-004 as written and ask Erode Harish to stop Â· C) Drop the build-order gate entirely and let frontend code start
- Chosen: A.
- Reason: D-004's stated reason was that "a stable, tested API lets the UI be designed against real data and contracts, with no rework." That risk is about **building** against a moving contract. Research, flows and a design system carry almost none of it, and they feed the backend useful questions early. C throws away the protection that reason describes: frontend code against an unfinished API is exactly the rework D-004 was avoiding. B stops work that costs the backend nothing.
- Consequences / follow-ups: (1) **Research, user flows, a design system and visual design may proceed now.** Frontend **code** — the web dashboard and the mobile app — still starts only when the backend is complete, and this repository still contains none (section 1). (2) **Designs are checked against `docs/api/openapi.json`**, the committed contract, which is now guarded by a test and by Schemathesis. A screen needing a field the API does not answer is a backend request, not a frontend decision, and should arrive as one. (3) D-004 is **amended, not reversed**: its gate on frontend code stands. (4) The design system that exists already (named Colyv, English only) predates this entry; it is consistent with D-054 below. (5) **Open:** whether the design work should live in this repository once it becomes code. It should not — section 1 says this repo is backend only — so a second repository will be needed, and nobody has made that decision.

## D-054: English only; Tamil is dropped
- Date: 2026-09-23
- Approved by: Adhi, in this session, asked directly and answered directly ("yeah the text language should be english"). **Not reviewed by Erode Harish** (D-051).
- Context: `CLAUDE.md` section 7, `docs/standards/ux.md` and several earlier entries promise Tamil and English from day one. `docs/COMPETITIVE_LANDSCAPE.md` names Tamil-as-the-product's-language as the one thing no reviewed competitor does. The design system built on 23 September already says English only. The repository and the product had drifted apart, and this settles which one is right.
- Options considered: A) English only Â· B) Tamil and English from day one, as written Â· C) English now, Tamil later behind the same message files
- Chosen: A, with the mechanism of C kept.
- Reason: Adhi decided it. The mechanism is kept because it costs nothing: the backend already returns facts rather than sentences (D-041 point 5, and notification rows store `type` and `details`), so a second language remains possible later without a rewrite. Nothing needs undoing to allow it back.
- Consequences / follow-ups: (1) **The cost is real and is recorded here rather than glossed:** `docs/COMPETITIVE_LANDSCAPE.md` treats Tamil as the product's language as our separation from every competitor, including Chennai-based Social Beat. Dropping it narrows the claim to execution and trust rather than language. That was Adhi's call to make, and he made it knowingly after being shown this. (2) **The backend changes almost nothing**, because it was never written to hold English sentences. What changes is documentation: `CLAUDE.md` section 7, `docs/standards/ux.md` lines 11, 32 and 48, and the competitive positioning. (3) **D-047's locked hybrid Tamil search row is void**, along with the Tamil test set that was to choose every AI and embedding model. The embedding model chosen in D-052, Qwen3-Embedding-0.6B, is multilingual, so **nothing needs re-choosing** and Tamil would work if it returned. (4) **Strings still come from message files, never written into a component.** That is the mechanism from option C and it is what keeps this reversible. (5) Earlier entries mentioning Tamil are **not rewritten**: this log is append-only and they were true when written.

- Consequences / follow-ups: (1) **Two tables, `creator_embedding` and `campaign_embedding`**, keyed by the row they describe, `ON DELETE CASCADE`. An embedding is derived data: losing every row costs a rebuild, not data, and it must never be the reason a deletion is refused. `source_hash` lets a rebuild skip rows whose input did not change; `model` lets two models coexist while one replaces the other. (2) **No UUIDv7 default**, although D-049 locks it for new tables: neither table generates an id, because the primary key is the foreign key. (3) **No vector index, deliberately.** Matching filters structurally first — city, niche, budget, status — and ranks by similarity inside that result, which at pilot scale leaves tens of rows. An exact scan over tens of vectors beats an index lookup and is always exactly right, where an approximate index is not. **The trigger to add HNSW is a measured p95 over the 300 ms read budget in `docs/PERFORMANCE.md`, not a hunch.** (4) **1024 dimensions**, the model's native width, fixed in the column rather than configurable because changing it is a migration. Matryoshka truncation can narrow it later without retraining. (5) **The dependency is not added yet.** Measured: a plain `pip install sentence-transformers` pulls about 2.0 GB on Linux, roughly 1.4 GB of it CUDA for a workload that will never touch a GPU. When it is added it must come from PyTorch's CPU index, in its own requirements file with its own CI job, because `pip-audit --strict` over torch's tree will fail a build one day. (6) **Constraint 2 is enforced in `embedding_input.py`, not here.** That module refuses to declare a field whose name looks private and fails closed when a new column appears; this migration only stores the result. (7) Both tables are declared in `NOT_EXPORTED` with a reason a person can read: everything the numbers were built from is already in their export in words, and the numbers are rebuilt from those words. **Whether that is the right answer under DPDP is a validation-pack question** (constraint 6) and is not decided here. (8) Verified in this session: the migration applies, downgrades and reapplies; `alembic check` reports no drift; 22 matching tests including a real `cosine_distance` query, which is what proves the extension is live; 1200 passed overall.

## D-055: Rate card schema — two tables and a consent column
- Date: 2026-09-25
- Approved by: Adhi, who told Claude to read the documents and decide ("you have all the .md files so go through them all and decide"). This closes **Decision 1 of `docs/PROPOSAL_PASSPORT_RATE_CARD.md`**, the last one outstanding; decisions 2, 3 and 4 were approved on 21 September as D-042. The proposal assigned this to Erode Harish, which D-051 supersedes. **Not reviewed by the other founder.**
- Context: Going through the documents end to end turned up an ordering mistake worth recording. `docs/COMPETITIVE_LANDSCAPE.md` section 6 ranks the rate card and media kit **first** of everything left to build, and matching **seventh** — and matching is what got built on 23 to 25 September (D-052). `docs/PLAYBOOK_GAPS.md` section 2 compounds it: the pilot plan is a **concierge start**, where "for the first 50 deals, a founder runs matching by hand". Automated matching was never the pilot's bottleneck. The rate card was, and it had been sitting fully specified with three of its four decisions already approved.
- Options considered: A) `creator_channel` and `creator_package` tables plus `creator.rate_card_public_at` · B) One JSONB column on `creator`
- Chosen: A, as the proposal recommended.
- Reason: These are lists with rules — a price must be positive, a platform must be one we know, a creator has one Instagram rather than four — and the database can enforce all of it (`database.md` section 3). B enforces nothing, and fair-rate guidance (#2 on the competitive list) has to query across these rows, which JSON makes miserable.
- Consequences / follow-ups: (1) **Two tables, both `ON DELETE CASCADE`** from `creator`: a channel or a price means nothing without the person offering it, and neither should ever be the reason a deletion is refused. (2) **`creator.rate_card_public_at` is a second, separate consent** from `passport_published_at`: a creator may want to be findable without publishing what they charge. NULL for everybody, for the same reason as D-036 — publishing someone's rates cannot be undone once search engines have read them. (3) **Nothing is verified and nothing pretends to be.** No `source` column, the word "verified" appears nowhere, and every follower count carries `figures_as_of`, the date the creator claimed it. About two in three Indian creators inflate them, so D-042 already settled that the public page links to the channel rather than republishing our copy of the number. (4) **A price of zero is refused.** It is not a price, and it would quietly skew fair-rate guidance, which will read these rows. (5) **The ten-package limit is the API's job**, not a CHECK: a database cannot count rows in one. `position` is capped at 19 so reordering has room. (6) **Both tables are exported**, because a creator's rate card is their own data and unlike most of what we hold it is something they typed rather than something that happened to them. (7) **Deliberately not done here:** the API in section 5 of the proposal, and the media kit endpoint. This change is the schema only, as the proposal sequenced it. (8) **A follow-up the measurements argue for:** the embedding input should probably include packages and channels. On the current profiles the model separates a food creator from a fitness creator by 0.0115; on richly written ones it separates them by 0.2704. The gap is the text, not the model, and a rate card is the richest thing a creator writes. It is noted in `embedding_input.py` and needs its own change, because that module reads one table and this would make it three. (9) Verified in this session: migration applies, downgrades and reapplies; `alembic check` clean; Squawk clean; 28 model tests covering every CHECK, the unique constraint and both cascades; 1228 passed overall.

## D-056: Fair-rate guidance, step 1 — published asking prices, five creators or nothing
- Date: 2026-09-26
- Approved by: Adhi, in this session ("yes" to both recommendations in `docs/PROPOSAL_FAIR_RATE_GUIDANCE.md`). **Not reviewed by the other founder** (D-051).
- Context: Backlog C3, #2 on the competitive list, unblocked by the rate card (D-055). Collabstr, Qoruz and YouTube's desired rates, checked on 26 September, all work from asking prices; none shows a range with its sample size for Tamil Nadu.
- Options considered: (1) whose prices count: A) only creators who published their rate card · B) every creator's packages; (2) minimum sample: A) five creators · B) ten
- Chosen: 1A and 2A.
- Reason: (1) Published creators already chose to show their prices to strangers, so counting them anonymously needs no new consent. Counting everyone's is a new purpose for what they typed, which is a DPDP question for the validation pack (constraint 6). Widening later is one line; figures cannot be unpublished. (2) Five keeps any single price from being inferred and gives answers during the pilot; the count is always shown so a reader can weigh it.
- Consequences / follow-ups: (1) `GET /api/v1/rate-guidance`, any signed-in account, 60/min, one query, no new table and no migration. p95 14.0 ms on seeded data. (2) Each creator counts once (their own median first); quartiles only, never a minimum or maximum; below five creators the figures are null, meaning not enough to say. (3) Narrows to niche and city, then niche, then neither, and reports which; cities match case-insensitively. (4) Audience bands come from the follower count on the same platform: under 10k, 10k–50k, 50k–100k, 100k–500k, 500k and over. Self-reported, and the response says so with the oldest count's date. (5) **Open for the validation pack:** may unpublished prices be counted (option 1B)? (6) **Step 2, agreed fees, is not approved.** It needs structured deliverables on the deal memo (a schema decision), a stricter minimum including three brands, and the validation pack's answer on fee confidentiality.

## D-057: A deal record nobody can quietly rewrite (C1, step 1)
- Date: 2026-09-26
- Approved by: Adhi, in this session ("yes" to option A of `docs/PROPOSAL_DEAL_RECORD.md`, after seeing the schema). **Not reviewed by the other founder** (D-051).
- Context: Deal, proof and payment rows are updated in place, so history is lost and nothing proves what was agreed; the operator could change a row unseen. QLDB, the usual managed answer, shut down in July 2025; BSA 2023 section 63 asks for hash values of electronic records.
- Options considered: A) build step 1 now (hash chain, database-enforced append-only, verification) · B) wait and build it with step 2 (signed receipts, daily RFC 3161 anchoring)
- Chosen: A.
- Reason: Step 1 stands on its own and step 2 builds on it without changing it; waiting would tie it to the undecided job runner.
- Consequences / follow-ups: (1) Table `deal_record_entry`: UUIDv7 ids, UNIQUE (deal, sequence), CHECKs on kind, actor, hash lengths, the genesis rule and `facts` being an object; `ON DELETE RESTRICT` from `deal_memo`; no FK on the actor's account. (2) **Two named departures from `database.md`:** no `updated_at`, and the schema's first trigger, refusing UPDATE, DELETE and TRUNCATE. (3) **Fingerprint v1 is frozen**: SHA-256 over `deal-record/v1\n`, the previous hash and RFC 8785-compatible canonical JSON, pinned by a hand-worked test vector; no new dependency. `recorded_at` is inside the seal, so the app sets it. The actor is sealed as `actor_account_sha256`, the SHA-256 of the account id, not the id: the first draft sealed the raw id, which the other side is never shown, so nobody outside could have checked the seals. Caught by a test that verifies from the JSON alone, and changed before v1 left this machine. (4) **Nothing typed goes in**: terms, links, notes and references are fingerprints only. (5) Existing deals get `record_started` on their first new entry rather than from the migration, so the algorithm exists once. (6) **Every transition writes one entry in its own transaction**: memo sent, change requested, accepted, declined, cancelled; proof submitted, approved, auto-approved (with both times) and sent back; payment opened, marked paid (single and bulk share the code) and confirmed; dispute opened, added to and closed. A draft cancelled before sending writes nothing. (7) `GET /api/v1/deal-memos/{id}/record` for the two parties only (404 otherwise), with `intact`, the first broken entry, whether the accepted terms still match, and `latest_seal`. Times are returned in the seal's exact spelling, as they are in the export's `deal_record` section, so both can be checked with the script in `docs/DEAL_RECORD_VERIFY.md`; a test runs that script from the markdown itself. (8) **Tests that really commit** (the payment concurrency tests) remove their entries through `tests/record_cleanup.py`, which uses `session_replication_role = replica` for one transaction. That needs a superuser, which local and CI have and the service must never be given; it is the same bypass the proposal names as step 1's limit. (9) Verified in this session: migration round trip, `alembic check` and Squawk clean; 16 model, 23 service and 22 API tests; 1375 passed overall. Measured with 30 deals rolled back: every write with its entry p95 ≤ 31 ms (budget 500), the verified record read p95 12.1 ms (budget 300). (10) Step 2 (signed receipts, daily RFC 3161 anchoring) and the three validation-pack questions in the proposal stay open.

## D-058: Login codes by WhatsApp through MSG91, with SMS on the same account later
- Date: 2026-09-26
- Approved by: Adhi, in this session ("i need the best so carry on"), in reply to the recommendation for MSG91, WhatsApp first. **Not reviewed by the other founder** (D-051).
- Context: No provider was chosen, so nobody could log in outside a developer's laptop (backlog E1). `docs/DECISION_NOTIFICATION_PROVIDER.md` recommended WhatsApp first through one provider carrying both WhatsApp and SMS; prices were checked again on 26 September.
- Options considered: A) MSG91 for both channels, WhatsApp first · B) Meta's WhatsApp Cloud API directly, and a separate SMS provider later · C) a global provider (Twilio and similar)
- Chosen: A.
- Reason: MSG91 passes Meta's WhatsApp authentication rate through at cost (about ₹0.12–0.14 a code) for ₹500 a month; SMS codes cost about ₹0.15 on the same account, so the fallback is a setting rather than a second integration; billing is in rupees with GST invoices, and it helps with DLT registration. B saves ₹500 a month but means two integrations, two bills and DLT alone. C adds a per-message fee that can double the cost.
- Consequences / follow-ups: (1) **Built:** `Msg91WhatsAppSender` behind the existing `OtpSender` interface, chosen by `OTP_SENDER=msg91`; our code in the template body and copy-code button; 3 s connect and 10 s read timeouts, at most 3 attempts with backoff and jitter, retrying only network failures, 429 and 5xx; no phone, code or provider reply text in any log or error. A half-configured provider stops the app at startup. Tested against a fake MSG91 only. (2) **Before the first real send**, `build_payload` must be checked against the request MSG91's dashboard generates for the approved template: the public documentation confirms the endpoint, header, number field and where the code goes, not the whole body. (3) **Only Adhi can do:** open the MSG91 account and Meta business verification in the company's name; get the authentication template approved; **start DLT registration the same day**, since it takes weeks; put the key in `.env`, never in chat or a commit. (4) **Still open:** whether the company is registered in India with GST (the cheap WhatsApp rate depends on it), and whether pilot creators all use WhatsApp on the number they sign up with (if not, SMS is needed at launch). (5) Not built yet: SMS fallback, and delivery of the other notifications, which needs the job runner.

## D-059: Local login is a command that prints a token
- Date: 2026-09-26
- Approved by: Adhi, in this session ("yes", to option A of `docs/DECISION_LOCAL_LOGIN.md`). **Not reviewed by the other founder** (D-051).
- Context: Locally, login codes are kept in the server's memory and never logged, so nobody could call the API as a signed-in user on a laptop; design and frontend work (D-053) would stop on it.
- Options considered: A) a local-only command that prints a token · B) a fixed code accepted when ENVIRONMENT=local · C) a local-only endpoint returning the last code · D) logging the code locally
- Chosen: A.
- Reason: It adds nothing to the running app, so a misconfigured server cannot expose a login bypass. B and C put one inside the app; D breaks the rule that codes are never logged.
- Consequences / follow-ups: (1) `scripts/dev_login.py <phone>` mints a token with the same `create_access_token` the login endpoint uses; only the token goes to stdout, so a shell can capture it. (2) It refuses unless ENVIRONMENT=local, and refuses a number outside the seed script's fake range unless `--any-phone` is given. (3) Verified in this session: 9 tests, including that the printed token is accepted by `GET /api/v1/auth/me`; run for real against the seeded local database, a brand's token answered 200 and a real-looking number was refused. (4) If the frontend later needs the real login screens end to end, option C comes back as its own decision.

## D-060: DBOS as the job runner, and a daily outside timestamp on the deal record
- Date: 2026-09-26
- Approved by: Adhi, in this session ("yes", to all five recommendations in `docs/PROPOSAL_RECORD_ANCHORING.md`). **Not reviewed by the other founder** (D-051).
- Context: The job runner blocked notifications, reminders, proof re-checks and step 2 of the deal record; D-047 locked DBOS, to be installed with its first job. Step 1 of the deal record (D-057) admits that someone with full database control could rebuild and reseal a chain.
- Options considered: (1) dbos 3.1.0, 2.31.1, Procrastinate, or a cron job outside the app · (2) DBOS keeps its own `dbos` schema and migrates it itself, or we copy its DDL into Alembic · (3) rfc3161-client, hand-written ASN.1, or no verification · (4) the two tables as proposed · (5) two outbound timestamp requests a day
- Chosen: dbos 3.1.0; its own `dbos` schema, managed by DBOS; rfc3161-client 1.0.9 (with cryptography pinned); the two tables; DigiCert and Sectigo.
- Reason: 3.x costs no migration when starting with no workflows, and the first job's failure only delays a checkpoint. DBOS's internal tables are a library's versioned state, like `alembic_version`; copying them into our chain would mean maintaining another project's schema. Signature checks are not a place to improvise parsing. Two authorities from different companies mean no single outage or compromise matters.
- Consequences / follow-ups: (1) **Constraint 3 is read as covering our schema, not a library's own state tables**; Alembic does not look outside the default schema, so `alembic check` stays clean. Revisit if that reading is ever challenged. (2) `deal_record_checkpoint` and `deal_record_timestamp` are append-only by trigger, through one general `append_only_refuse_change()` that names the table it guards. (3) Leaves are not stored: the record is append-only, so each deal's latest seal at a cut-off can always be recomputed. (4) A checkpoint without timestamps is a visible gap, retried on the next run. (5) No PII may be passed into a DBOS workflow: its inputs are stored in Postgres. Only ids and times. (6) pip-audit clean on the new pins (26 September).

## D-061: The admin side: an admin role, suspension, reports and an admin log
- Date: 2026-09-27
- Approved by: Adhi, in this session: "yes" to option A, then "yes" to the full design in `docs/PROPOSAL_ADMIN.md` after seeing it. **Not reviewed by the other founder** (D-051).
- Context: A pilot cannot be run without finding an account, suspending a fake or abusive one, and handling users' reports; today each would mean hand-editing the database, which constraint 3 forbids.
- Options considered: A) an admin role with endpoints, suspension, reports and an append-only log · B) no admin API, act in the database
- Chosen: A, exactly as designed in the proposal.
- Reason: B breaks constraint 3 the first time someone must be suspended, and leaves no record of who did what.
- Consequences / follow-ups: (1) `account.role` admits `admin`; admins are created only by `scripts/make_admin.py`, never by login; login with role admin never creates an account and answers exactly as a wrong code when none exists. (2) `account.suspended_at` and `suspension_reason`, checked on every request; a suspended creator leaves search, matching and the public page, a suspended brand's campaigns leave discovery, and existing deals stay usable by the other party. (3) `report` with one open report per reporter per subject, and `admin_action`, append-only by trigger, logging every admin action and every view of an account's details. (4) The downgrade refuses while any admin exists. (5) Exports: suspension status and the reports a person made are exported; the admin log is not, with the reason printed in every export. (6) **Open for the validation pack:** how long reports and the admin log are kept, whether a suspended person must be offered an appeal, and whether a person may see admin log entries about them.

## D-062: Hosting on AWS Mumbai, with files in S3
- Date: 2026-09-27
- Approved by: Adhi, in this session ("a", to option A of `docs/DECISION_HOSTING.md`). **Not reviewed by the other founder** (D-051).
- Context: Nothing was deployed, so no user could reach the backend, and the MSG91 sender and the daily checkpoint (D-060) had nowhere to run.
- Options considered: A) AWS Mumbai · B) DigitalOcean Bangalore · (Google Cloud Mumbai set aside: its pgvector was last reported inside CVE-2026-3172's range)
- Chosen: A.
- Reason: Every need is met by a managed service in one Indian region: RDS PostgreSQL 18 with pgvector 0.8.2, the release that fixes CVE-2026-3172; ElastiCache Valkey 9.1, matching D-048; ECS Fargate containers with room for DBOS and the embedding model; private S3 with signed uploads; Secrets Manager. It grows without a move. B's pgvector version could not be confirmed.
- Consequences / follow-ups: (1) Staging and production as separate environments; staging can be switched off. (2) Estimated at about $175 a month for both before GST and credits; **an estimate from published prices, to be confirmed in AWS's calculator before anything is opened**. (3) **Only Adhi can:** open the account in the company's name, secure the root user with MFA and never use it, apply for AWS Activate credits, and decide who gets access. (4) **Still separate decisions:** OpenTofu as the infrastructure-as-code tool (a new dependency); where traces go (plan 4.5). (5) A restore from backup is tested before the first real user. (6) Whether DPDP ever requires Indian storage stays a validation-pack question; this choice does not depend on the answer.

## D-063: How the app is packaged and deployed: OpenTofu, split requirements, one image
- Date: 2026-09-27
- Approved by: Adhi, in this session ("all 3", then "yes" to pinning certifi, each after seeing the proposal). **Not reviewed by the other founder** (D-051).
- Context: Hosting is chosen (D-062); the app now needs an image to run and infrastructure to run it on.
- Options considered: (1) OpenTofu, Terraform, AWS CDK, or the console · (2) keep one requirements file, or split runtime from developer tools · (3) the image: a small Debian-based Python 3.12 image pinned by digest, multi-stage, non-root, CPU torch, built and vulnerability-scanned in CI
- Chosen: all three as recommended, and `certifi` pinned.
- Reason: (1) Every AWS resource written in the repository and reviewed as a diff; open source. (2) Production should not carry, or need patching for, tools it never runs. (3) The smallest image that runs the app as it is tested, with nothing that builds code reaching production.
- Consequences / follow-ups: (1) `requirements.txt` is what the app runs; `requirements-dev.txt` includes it and adds the tools. Laptops and CI install the developer list; pip-audit reads it, so both are audited. (2) **The split found a real bug**: the timestamp checks import `certifi`, which only a developer tool had been installing, so a runtime-only install could not start. It is now pinned (2026.7.22), and a runtime-only install was proven to start with no developer tool present. (3) Python 3.14 (D-047) stays a separate upgrade. (4) Nothing is applied to AWS until the account exists and the OpenTofu code has been reviewed.

## D-064: The images are scanned by Grype in CI, and the embedding model is pinned in code
- Date: 2026-09-30
- Approved by: Adhi, in this session ("carry on A" to the scanner, then "carry on with A" to both follow-ups, each after seeing the proposal). **Not reviewed by the other founder** (D-051).
- Context: D-063 requires the images to be built and scanned in CI; nothing did either. Building and running the images for the first time found two things. (1) The embeddings image could not load its own model: the app asked for "the newest" version, and offline (as the image runs) that cannot be looked up, so the daily refresh would have failed on its first run in production. (2) Grype finds 10 vulnerabilities in CPython 3.12.14 itself, the newest 3.12, fixed only in 3.13 and later, so the approved rule (fail on anything with a fix) would be red from the first run.
- Options considered: Scanner: A) Grype, pinned by version and checksum · B) Trivy, whose distribution was hijacked on 19 March 2026 · C) only the AWS registry scan after push. Model: A) the app asks for an exact revision · B) only the image records the revision as "newest". CPython findings: A) accept the 10 by ID in `.grype.yaml` until the Python 3.14 upgrade · B) move to Python 3.14 now · C) do not gate on the interpreter.
- Chosen: A, A, A.
- Reason: Grype has no compromise history and a checksum-pinned binary cannot be swapped quietly. Pinning the model revision is the same rule as every other dependency, and makes laptops, CI and AWS run the same weights. Moving to 3.14 would still leave 4 of the 10, and our code uses none of the affected modules except base64 in the page cursor, which parses strictly after decoding (read, not tested).
- Consequences / follow-ups: (1) CI's new `image` job builds the API image and fails on any fixable vulnerability of any severity; for pull requests to main it also builds the embeddings image and reports without failing (D-052). (2) `MODEL_REVISION` in `embedder.py` must equal the Dockerfile's `ARG MODEL_REVISION`; a test enforces it. (3) The 10 accepted CPython entries name version 3.12.14, so any Python change brings them back for review; remove them at the Python 3.14 upgrade (D-047), keeping any it does not fix. (4) A new advisory can turn CI red with no code change; the fix is a newer base digest, or a reasoned entry in `.grype.yaml`.

## D-065: Proof of delivery as files: signed uploads to S3, every image cleaned on the server
- Date: 2026-09-30
- Approved by: Adhi, in this session ("approve A", to the recommendation in `docs/PROPOSAL_PROOF_FILES.md`, after seeing it: option A for both decisions, the three packages, the table and the infrastructure). **Not reviewed by the other founder** (D-051).
- Context: Proof is a pasted link, which disappears when a post is deleted, and brands ask for screenshots of reach that have no link (backlog E3). D-062 already settled that files go straight from the phone to S3 through signed uploads.
- Options considered: (1) images as uploaded, apps strip location, or the server re-encodes every image · (2) tests against an in-memory stand-in plus moto, or SeaweedFS/Garage in docker-compose now (MinIO stopped publishing free images in October 2025)
- Chosen: (1) the server re-encodes every image; (2) the stand-in plus moto, SeaweedFS later when frontend work needs a local S3.
- Reason: (1) the only option where a mistake in an app or a web upload cannot leak a creator's home location; re-encoding also defuses files disguised as images. (2) nothing unmaintained, no new service before anyone needs it.
- Consequences / follow-ups: (1) New packages: boto3 and Pillow (runtime), moto (development). Pillow's frequent security releases must be taken promptly; pip-audit fails CI until they are. (2) One new table, `proof_file`; a proof's link becomes optional. (3) Images only in the pilot: JPEG, PNG, WebP, 10 MB each, 10 per proof; video stays a link. (4) Infrastructure: the bucket's CORS, the task role limited to the uploads prefix, a one-day expiry for abandoned uploads; not applied until AWS exists. (5) How long proof files are kept is a validation pack question; the deal record keeps only fingerprints, so files can be deleted without breaking it.

## D-066: The deal record seals the clean copy of every proof file
- Date: 2026-10-01
- Approved by: Adhi, in this session ("yes", to the recommendation after seeing it). **Not reviewed by the other founder** (D-051).
- Context: D-065 cleans every proof image of location and hidden data, keeps only the clean copy and deletes the original. The fingerprint sealed at submission is the original's, so on its own the record would point at a file that no longer exists, and nothing would prove which file a brand actually saw.
- Options considered: A) a new record entry kind, `proof_file_cleaned`, sealing the clean copy's fingerprint beside the original's · B) record only the original's fingerprint
- Chosen: A.
- Reason: every file a brand sees stays provable, from the record alone, without trusting us.
- Consequences / follow-ups: (1) Migration `f276d2c6ce1e` widens the record's kind check, added NOT VALID and validated after commit; its downgrade refuses while any such entry exists, since the record is append-only. (2) Entries are made by `system`, one per cleaned file, after the proof's own entry. (3) A file refused by the cleaner is not recorded; the creator sees it as rejected on the proof. Recording refusals would need another kind and another decision.

## D-067: A proof shows its files in the order the creator chose, the order the record seals
- Date: 2026-10-01
- Approved by: Adhi, in this session ("A", to the decision and schema request after seeing them). **Not reviewed by the other founder** (D-051).
- Context: Submitting proof promised files "in the order to show them", and the deal record sealed them in that order, but they were shown in upload order. Uploaded A then B and submitted as B, A, the record said B, A and the brand saw A, B: evidence that reads differently on screen and in the record.
- Options considered: A) a `position` column on `proof_file`, set when a file joins a proof, and one order everywhere · B) no schema change: drop the promise, show and seal in upload order
- Chosen: A.
- Reason: the record and the screen must always agree, and keeping the creator's order costs one small column.
- Consequences / follow-ups: (1) Migration `608541cc4a4e`: `position` smallint, empty exactly while pending, 0 to 9 otherwise, unique per proof; checks NOT VALID then validated after commit, the unique index built CONCURRENTLY. (2) It fills existing attached files with their upload order inside the same migration. database.md section 6 puts backfills in their own migration; the approved plan did not, since `proof_file` has never been deployed or merged and holds no real data. (3) The proof's files, the view links (step 5) and the data export carry this order; the export lists `position`. (4) The downgrade drops the column; files fall back to upload order.

## D-068: Patch OpenSSL and PCRE2 in the API image until the base image catches up
- Date: 2026-10-01
- Approved by: Adhi, in this session ("A", to the decision after seeing it). **Not reviewed by the other founder** (D-051).
- Context: CI's image scan (D-064) started failing on `main` with no change of ours: Debian published fixes for OpenSSL 3.5.7 (9 CVEs, one High) and PCRE2 10.46 (one High) after our pinned base, `python:3.12-slim-trixie` of 19 September, was built. Docker had not rebuilt that image yet, so moving the pin could not help.
- Options considered: A) install the fixed versions, exactly, in the Dockerfile's api stage · B) wait for Docker's rebuild, then move the pin · C) accept the risk in `.grype.yaml`
- Chosen: A.
- Reason: D-047's rule is that security fixes are taken at once. OpenSSL carries our outgoing TLS (S3, MSG91, the timestamp authorities), so it is not a risk to accept, and waiting leaves `main` red and the image flawed for days.
- Consequences / follow-ups: (1) One `apt-get install --only-upgrade` step with exact versions (`openssl`, `libssl3t64`, `openssl-provider-legacy` 3.5.7-1~deb13u3; `libpcre2-8-0` 10.46-1~deb13u3), apt's lists removed after. The embeddings image inherits it. (2) **Remove the step** when the base digest moves to an image that already carries these versions or newer. (3) The `build` stage is not patched: it is thrown away and never ships.

## D-069: Erode Harish's review and approval of D-055 to D-068, relayed by Adhi
- Date: 2026-10-01
- Approved by: Erode Harish, **relayed by Adhi** in this session ("for everything till now whatever you have asked erode as reviewed and approved", then, asked whether Harish had actually seen and approved them, "yes he approved everything"). Harish did not confirm in a session here, the same footing as D-047 and D-051.
- Context: Since D-051 Adhi has built the backend alone, and every entry from D-055 to D-068 says it was not reviewed by the other founder. Those entries stay as written; the log is append-only, and this entry is what changes their standing.
- Options considered: A) record the relayed approval of all fourteen · B) leave them marked unreviewed
- Chosen: A.
- Reason: Adhi relayed Harish's approval of everything raised so far, after being told the record would say "relayed".
- Consequences / follow-ups: (1) D-055 to D-068 count as approved by both founders, by relay: the rate card schema, fair-rate guidance, the deal record and its daily outside timestamp, WhatsApp login through MSG91, local developer login, DBOS, the admin side, hosting on AWS Mumbai, packaging and deployment with OpenTofu, image scanning with Grype, proof files and their cleaning, the clean copy sealed in the record, proof file order, and the image's OpenSSL and PCRE2 fix. (2) PRs #32, #33 and #34, already merged, are covered by this entry; their descriptions said unreviewed and are not edited. (3) Work after this entry is unreviewed again until a founder says otherwise, and reports and PRs keep saying so (CLAUDE.md section 0).

## D-070: Results a brand can trust, read from the proof: build layers 1 to 3
- Date: 2026-10-01
- Approved by: Adhi, in this session ("Approve A", to the recommendation in `docs/PROPOSAL_PROOF_RESULTS.md` after seeing it: decision 1 option A, the model rule of decision 2, the dependency, the schema and the infrastructure). **Not reviewed by the other founder.**
- Context: Brands pay for reach and receive screenshots that can be edited ("the Screenshot Portfolio Scam"); the platforms' own numbers need each creator's login to an app Meta has reviewed. Proof files and their sealed fingerprints exist since D-065 and D-066. Competitive item #4: nobody holds deal, delivery, payment and result in one record.
- Options considered: (1) A) read, check and seal every proof screenshot now · B) wait for platform connections only · C) brands type numbers in themselves; (2) the model: Opus 5.5, Sonnet 5.5 or Haiku 4.5
- Chosen: (1) A, with platform-verified numbers as a later layer; (2) Opus 5.5 until a test set of real screenshots, with their true numbers written down, shows which model reads every number right at what cost.
- Reason: results for every deal and any size of brand, checked against facts we hold and sealed, which no competitor has; the model chosen by measurement, not by price or guess.
- Consequences / follow-ups: (1) New runtime package `anthropic` 1.11.0 (needs httpx2 2.x, which D-047 pins). (2) Off by a setting (`PROOF_READING_ENABLED`) in every real environment until the validation pack says whether a creator's insights may go to a processor (constraint 6); on, the app refuses to start without `ANTHROPIC_API_KEY`. (3) A screenshot reading is never called verified: Anthropic's vision documentation says Claude cannot tell a real image from a fake one. (4) One table, `proof_file_reading`, and one record kind, `proof_results_read`, come with step 3; the key goes in Secrets Manager with step 6. (5) Only the clean copy is ever sent; Anthropic states it does not train on uploaded images and does not keep them beyond the request. (6) Automatic fallback to another model on a refusal is not enabled: a refusal is recorded as a failed reading, never a guess.

## D-071: Coimbatore first; what the backend builds before launch; the AI interface
- Date: 2026-10-01
- Approved by: Adhi, in this session: the public receipt check declined in his own words ("no need because it is between creator and brand"); the remaining recommendations approved with "do all", after seeing each with its reasons and sources. **Not reviewed by the other founder.**
- Context: The day's research (`docs/PSYCHOLOGY_AND_TRUST.md`, `docs/GO_TO_MARKET.md`, `docs/COMPETITIVE_LANDSCAPE.md` version 3) left decisions open that the finish line and the pilot depend on.
- Options considered: the pilot city, Coimbatore or Madurai; for each new backend item, build before launch, after launch, or not at all; for AI features, Pydantic AI (D-047) or our own thin interface.
- Chosen: (1) **Coimbatore**, with three niches: food and cafés, fashion and textiles, beauty and salons. (2) **Built before launch**: notification preferences (quiet hours, digest, a choice per event); typical response times from real data, shown only from 5 examples; invite and source attribution; city and niche aggregates for public pages (backend now, published once a city has the data). (3) **After launch**: milestones; camera signatures (C2PA). (4) **Declined**: the public deal receipt check. (5) **English only stands** (D-054); the brand interviews ask whether Tamil would change anything, and the pilot decides whether to revisit it. (6) **AI features use our own thin interface**, as results from proof does (D-070); Pydantic AI is adopted when a second provider or agent features arrive. D-047's baseline row is amended to match.
- Reason: (1) about twice Madurai's population and spending, a café boom, the state's second quick-commerce market, CODISSIA's 7,000+ businesses, Tiruppur's clothing brands next door, and a founder can be there. (2) More than six notifications a week makes users 3.4 times as likely to uninstall within 30 days; attribution not recorded from day one can never be recovered; the frontend needs these shapes. (3) Milestones need real deals; Pixel holds about 4% of India's ultra-premium phones, so almost no proof would carry a camera signature. (4) A deal is private between its parties; each can already check its own record. (5) Data from the pilot, not a guess. (6) One provider today; a dependency for no gain until there are two.
- Consequences / follow-ups: `docs/BACKEND_COMPLETE.md` holds 20 items, with section 5 listing what was declined or deferred; the receipt-sharing loop leaves `docs/GO_TO_MARKET.md`; the Tamil question joins the interview in `docs/REVENUE_RESEARCH.md`; novelties 2 and 3 in `docs/COMPETITIVE_LANDSCAPE.md` are marked waiting and declined; the AI row of `docs/PLATFORM_AND_TECH_PLAN.md` section 4.0 is amended.

## D-072: Python 3.14 and uv, built: one locked dependency list for every machine
- Date: 2026-10-01
- Approved by: Adhi, in this session ("do all especially this Python 3.14 + uv"), building the item D-047 locked on 22 September (Erode Harish's approval relayed then, and of D-055 to D-068 in D-069). **This build is not reviewed by the other founder.**
- Context: D-047 locked Python 3.14 and uv; nothing was built, so laptops, CI and the images still ran 3.12 with pip and three requirements files. The audit for `docs/BACKEND_COMPLETE.md` found it (item 1).
- Options considered: (1) keep the requirements files and use uv only as a faster pip · (2) make the project a uv project: one list in `pyproject.toml`, a committed `uv.lock` with hashes for every package, uv in CI and the images
- Chosen: 2, with Python 3.14.7 (the newest 3.14, on laptops through uv and in the images through `python:3.14-slim-trixie`, pinned by digest) and uv 0.12.21 (pinned in CI, and copied into the build stage from Astral's image, pinned by digest).
- Reason: one source of truth, so a dependency cannot be added in one file and missed in another; every machine installs the same bytes; a tampered download fails its hash; `--locked` stops a change reaching main without its lock.
- Consequences / follow-ups: (1) `requirements.txt`, `requirements-dev.txt` and `requirements-ml.txt` are gone; their packages, pins and reasons are in `pyproject.toml` (the app, a `dev` group, an `ml` group), and torch still comes only from PyTorch's CPU index. (2) Commands change: `uv sync`, `uv run …` (`CLAUDE.md` section 4, README, the scripts). Laptops use `.venv`; the old `venv` can be deleted once a founder has run `uv sync`. (3) CI installs with `setup-uv` pinned to a commit (v10.2.0); zizmor and pip-audit run through `uvx`, still outside the app's dependencies; pip-audit checks the lock exported in full, with no re-resolution. (4) On 3.14, ruff removed 16 quoted type hints that lazy annotations (PEP 649) make unnecessary; the full suite proved Pydantic reads them correctly. (5) The images: the app environment has no pip at all, and uv is not shipped. (6) `.grype.yaml`: the upgrade fixed 6 of the 10 CPython flaws accepted for 3.12.14; the 4 that 3.14.7 still has (stringprep, poplib, zipfile, urllib's password managers) are accepted for exactly 3.14.7, re-checked against the code. (7) The OpenSSL and PCRE2 step from D-068 stays: the 3.14 image has the same base as the 3.12 one.

## D-073: D-004 was approved by Adhi
- Date: 2026-10-04
- Approved by: Adhi, in this session ("approved by me"), answering who approved D-004, whose entry still read `Approved by: <founder name>`.
- Context: A review finding (PR #6, P2) noted that D-004 had no named approver while standards treated it as settled. The log is append-only, so the old line stays as written and this entry completes it.
- Options considered: A) record Adhi as D-004's approver · B) mark D-004 as never approved
- Chosen: A.
- Reason: Adhi stated that he approved it. Its rule also stands through D-053, which amended it with a recorded approval.
- Consequences / follow-ups: D-004 (backend first, frontend code after the backend is complete, as amended by D-053) is a decided rule with a named approver. Review finding #3 in `docs/REVIEW_FINDINGS.md` is resolved.

## D-074: Error tracking with Sentry, scrubbed of personal data; Python 3.14.8 for the image gate
- Date: 2026-10-04
- Approved by: Adhi, in this session ("i have approved", 4 October, after the proposal to add `sentry-sdk` 2.71.0 and move to Python 3.14.8).
- Context: (1) An unexpected error was only a CloudWatch log line nobody would read until a user complained (`docs/BACKEND_COMPLETE.md`, observability). (2) CI's image gate failed on `62a1000` and after: three new CPython advisories on 3.14.7, one fixed in 3.14.8 (released with uv 0.12.23 on 3 October).
- Options considered: Error tracking: A) Sentry (free plan, 5,000 errors a month, the de facto standard; the SDK is MIT licensed) · B) CloudWatch alarms on error log lines only (no grouping, no stack traces in the alert, no release tagging) · C) self-hosted GlitchTip (a new service to run, against CLAUDE.md section 3). Image gate: A) move to 3.14.8 and accept, for exactly 3.14.8, the three flaws fixed only in 3.15 · B) accept all of them on 3.14.7.
- Chosen: A for both.
- Reason: Sentry gives an alert with the stack trace, grouped by bug and tagged with the release, at no cost at pilot scale. Moving to 3.14.8 fixes five flaws outright (D-047: security fixes at once) rather than accepting them.
- Consequences / follow-ups: (1) `app/core/error_tracking.py`, started in `app/main.py`, off unless `SENTRY_DSN` is set. Error log lines become events (the 500 handler, a failed login-code send, a failed anchor); 4xx and deliberate 5xx answers do not. (2) Never sent: request bodies, cookies, query strings, the account, the IP address, local variables; phone numbers, emails, UPI IDs and long numbers anywhere in an event are replaced before it leaves the process. 26 tests read exactly what would be sent. No performance tracing. (3) New settings `SENTRY_DSN` and `APP_RELEASE`; infra passes the DSN as a plain setting (a DSN can only send errors in, so Sentry treats it as public) and the release as the image's git commit. (4) To do by a founder: create the Sentry organisation (the data region, US or EU, is chosen then and cannot change; the validation pack should say which DPDP prefers) and set `sentry_dsn` for staging and production. (5) Python 3.14.8 in `.python-version` and the image (pinned by digest), uv 0.12.23 in CI and the image; `.grype.yaml` now accepts only CVE-2026-87910 (tarfile), CVE-2025-15367 (poplib) and CVE-2026-12345 (tempfile), for exactly 3.14.8, none used by our code; the local gate passes.

## D-075: One list of my payments, and their totals
- Date: 2026-10-04
- Approved by: Adhi, in this session ("i have approved", then "carry on"), after the plan naming "one list of payments across all deals" as the third piece of work.
- Context: The website wireframes (4 October) need a Payments screen: who is owed, who is paid, what is overdue. The API only answered one deal's payment at a time, so the screen would make a call per row, which `docs/standards/ux.md` section 7 treats as a backend request.
- Options considered: A) `GET /api/v1/payments/mine` (newest first, filtered by view, each row with its campaign, creator and brand) plus `GET /api/v1/payments/mine/totals` · B) add payment fields to the memo list · C) leave it to the frontend
- Chosen: A.
- Reason: two calls answer the whole screen; B would load payment data for every memo, paid or not; C is the per-row pattern the standard forbids.
- Consequences / follow-ups: (1) Read-only: no table, column or migration; states are worked out exactly as for a single payment. (2) Views: `to_pay`, `awaiting_confirmation`, `finished`; every payment is in exactly one. Totals: count and amount in each, plus `overdue`, always returned, zero included. (3) Brands and creators see only their own deals; an admin gets 403, a missing profile 409. (4) Disputes are read for the whole page in one query; a test proves a page of three costs the same queries as a page of one, and fails when a per-row query is added. 26 tests. Rate limited at 60 a minute.

## D-076: Each deal's stage and whose move it is; a campaign at a glance
- Date: 2026-10-04
- Approved by: Adhi, in this session ("make sure we are above top tier in everything as well carry on"), continuing the wireframes' backend requests after D-075.
- Context: The website wireframes (4 October) show each deal as one of five stages (Memo sent, Agreed, In progress, Payment, Finished) with who acts next, and head each campaign with "n of m deals finished" and Complete. Without the backend saying so, each screen would read every memo, proof and payment and work it out, once per card, and the website and both apps could each work it out differently.
- Options considered: A) work the stage out in the backend from the memo, its proof and its payment, never stored; and a per-campaign summary · B) store a stage column and keep it in step on every change · C) leave it to each client
- Chosen: A.
- Reason: one definition, consistent with the rules already built: approval counts the clock (D-025, through `is_approved`), a barter deal finishes when its work is approved (D-026), a paid deal finishes only when the creator confirms the money arrived (D-027). B would be a second copy of facts already stored, free to drift; C is three copies.
- Consequences / follow-ups: (1) `app/modules/deal_memo/stage.py`: `stage` is one of `draft`, `memo_sent`, `agreed`, `in_progress`, `payment`, `finished`, `declined`, `cancelled`; `waiting_on` is `brand`, `creator` or null once ended; `has_open_dispute`. (2) `GET /deal-memos/mine` and `GET /deal-memos/{id}` now carry them (fields added, nothing removed); `/mine` takes `campaign_id`, for a campaign's board. Writes still answer the plain memo. (3) `GET /campaigns/{id}/summary`, owning brand only: applications by status, deals by stage (every status and stage, zeros included), `deals_agreed`, `deals_finished`, `deals_waiting_on_brand`, `complete` (closed, at least one deal agreed, every agreed deal finished, no memo unanswered). (4) No table, column or migration. Stages for a whole page or campaign take a fixed number of queries; tests prove it and fail when a per-row lookup is added. 37 tests: every rule without a database, one deal walked through all five stages, and Complete in each case.

## D-077: Typical response times, measured from the deal record
- Date: 2026-10-08
- Approved by: Adhi: item approved in D-071 ("typical response times from real data, shown only from 5 examples"); built on 8 October on his instruction to carry on with the next items.
- Context: Known waiting lowers anxiety (`docs/PSYCHOLOGY_AND_TRUST.md`); each side should know how long the other usually takes, without anything invented.
- Options considered: A) measure from the deal record's dated, sealed entries · B) from notification timestamps · C) from status-change columns
- Chosen: A.
- Reason: the deal record is the one complete, ordered history of who did what when; notifications are a delivery log, and status columns keep only the latest change.
- Consequences / follow-ups: (1) `GET /api/v1/brands/{id}/response-times` (any signed-in account, as the payment record): work submitted to approved or sent back, an approval by the clock counting at the window's end. `GET /api/v1/creators/{id}/response-times` (brands or the creator, as the delivery record): memo sent to answered, and payment marked sent to confirmed. (2) Median in hours to a tenth; null below 5 examples; `examples` always returned. Requests still waiting are not counted; a memo withdrawn before an answer is left out. (3) **Not measured: how fast a brand answers an application**: only the latest status change is stored, so a figure would be a guess. Measuring it needs a first-decision timestamp, a schema change for a later decision. (4) No table, no migration. 22 tests.

## D-078: City figures for public pages: counts and medians, five or nothing
- Date: 2026-10-08
- Approved by: Adhi: item approved in D-071 ("city and niche aggregates for public pages, backend now, published once a city has the data"); built on 8 October on his instruction to carry on.
- Context: City pages are how search and AI answer engines find a local marketplace (`docs/GO_TO_MARKET.md`); the frontend needs the figures' shape now.
- Options considered: what counts: A) published Passports, published rate cards and open campaigns only · B) also figures from deals
- Chosen: A.
- Reason: published creators chose to be seen (D-036), published prices chose to be shown (D-056), open campaigns are public by design. Deals are private between their parties (D-071 declined even a public receipt), so no public figure is built from one.
- Consequences / follow-ups: (1) `GET /api/v1/cities` (cities with at least 5 published creators, largest first) and `GET /api/v1/cities/{city}/figures` (published creators, by niche, open campaigns, median asking price by platform and format): public, no login, 60 a minute, cached an hour with an ETag. (2) Five or nothing: any figure on fewer than 5 is null, never zero; medians only, never a minimum or maximum; each creator counts once in a price. (3) Suspended accounts and their brands' campaigns never count (D-061). Cities match without regard to case or spaces and show the spelling most creators used. (4) No table, no migration. 15 tests. (5) Publishing city pages is a frontend and SEO step; the figures stay null until a city has the data.

## D-079: Notification preferences, with urgent events never held
- Date: 2026-10-08
- Approved by: Adhi, in this session ("approve all", after `docs/PROPOSAL_NOTIFICATION_PREFERENCES_AND_ATTRIBUTION.md` section 1 with its schema and the defaults decision). Item approved in principle by D-071.
- Context: More than six notifications a week makes users 3.4 times as likely to uninstall within 30 days (D-071). Push and WhatsApp delivery are not built; the preferences decide how they will be.
- Options considered: defaults: A) quiet hours 22:00 to 08:00 Tamil Nadu time on for everyone, digest off · B) no quiet hours until set
- Chosen: A.
- Reason: only non-urgent notifications are ever held, and those can wait until morning.
- Consequences / follow-ups: (1) Table `notification_preference` (migration `636f06a7e2dc`), one row per account, written only on save; no row means the defaults. (2) `GET` and `PUT /api/v1/me/notification-preferences`; PUT replaces the whole set in one insert-or-update, so a retry or two saves at once are safe. (3) Urgent types (`memo_sent`, `proof_submitted`, `proof_revision_requested`, `payment_marked_paid`) cannot be muted: the API answers 422 and the database's own check refuses it. (4) `preference_service.decide` is the rule the future sender must call: urgent now, muted in the app only, daily digest at its hour, otherwise held through quiet hours; tested before any sender exists. (5) Preferences govern delivery outside the app only; the in-app list keeps everything. (6) In the data export; the export now writes times of day as `HH:MM`. 32 tests.

## D-080: Invite and source attribution, written once at sign-up; inviters see counts only
- Date: 2026-10-08
- Approved by: Adhi, in this session ("approve all", after `docs/PROPOSAL_NOTIFICATION_PREFERENCES_AND_ATTRIBUTION.md` section 2 with its schema, the sign-up change, and the decision on what an inviter sees). Item approved in principle by D-071.
- Context: Attribution not recorded at sign-up can never be recovered (D-071); the pilot's question is which channel brings brands and creators.
- Options considered: what an inviter sees: A) counts only · B) names of who joined
- Chosen: A.
- Reason: B tells one person that another joined, a DPDP question for the validation pack; A loses nothing a reward would need. Widening later is one endpoint; narrowing after names were shown is impossible.
- Consequences / follow-ups: (1) Tables `invite_code` and `account_attribution` (migration `8c960d1db341`), new and empty; existing accounts have no row. (2) `POST /auth/otp/verify` takes an optional `arrival` (invite code, source, campaign tag), **read only by the login that creates the account**, in that login's own transaction; a returning login cannot rewrite it. An unknown code is ignored, never refused. A valid code makes the source `invite`; `invite` and `not_given` cannot be claimed. (3) `GET /api/v1/me/invite-code` (eight characters with no 0, O, 1 or I; made on first request, the same after, safe against two first requests at once), `GET /api/v1/me/invites` (brands and creators joined, counts only), `GET /api/v1/admin/signups` (per week from Monday, Tamil Nadu time, source and role; counts only, so no admin log entry). (4) The database refuses a misreadable code and a code without an invitation. (5) The downgrade refuses while any attribution exists. (6) In the export, without the inviter's code. (7) **Rewards are not built**: what they are, and their tax treatment, is for the founders and the validation pack. 32 tests.

## D-081: The world-class bar written down once; the docs given one index; the standards raised
- Date: 2026-10-08
- Approved by: Adhi, in this session ("make the md files to the level of the best billion dollar ... i am fed of repeating the standards"; "i mean all md files ... are you using all the md files").
- Context: Adhi had to restate his quality bar session after session; 39 markdown files had no index; 13 decided proposals sat beside live plans; four lists of work overlapped; several standards still marked as open decisions that were settled weeks ago; and testing.md listed a banned-term CI gate that did not exist.
- Options considered: A) write the bar into `CLAUDE.md`, index the docs, archive what is decided, raise each standard against named best practice, and build the missing gate · B) leave the files and restate the bar in each session
- Chosen: A.
- Reason: `CLAUDE.md` is read at the start of every session, so a bar written there never needs repeating; an index tells anyone which file is binding and which is history.
- Consequences / follow-ups: (1) `CLAUDE.md` section 7.0, "The bar: world-class by default". (2) `docs/README.md` indexes every doc by job: rules, record, plan, research, reference. (3) The 10 `PROPOSAL_*` and 3 `DECISION_*` papers already built moved to `docs/decided/`, with a map; references updated outside this append-only log. (4) `backend.md`, `database.md`, `security.md`, `testing.md` and `ux.md` rewritten: settled decisions recorded as settled; added the API evolution rules (additive only in v1; `Deprecation` and `Sunset` headers), the lock-then-check rule, the query-count rule, the destructive-downgrade rule, operations and restore drills, ASVS 5.0 Level 2 as the security target with a control map and threat modelling, the "prove a test can fail" rule, and the real list of 11 CI gates. Owed items are marked "not yet built" rather than claimed: secret scanning in CI, Dependabot, an SBOM, signed images, `SECURITY.md` and `security.txt`, an incident plan, a restore drill, a penetration test. (5) `tests/test_banned_terms.py` enforces the money-words rule across every tracked file, shown to catch a breach.

## D-082: The security items owed before launch, built: secret scanning, an SBOM, Dependabot, SECURITY.md, security.txt, the incident plan
- Date: 2026-10-08
- Approved by: Adhi, in this session ("approve all, build them all in the best order", answering the question whether to build secret scanning, Dependabot and `SECURITY.md` now, which changes CI).
- Context: D-081's rewrite of `docs/standards/security.md` marked these as owed and not built. Each is small, and each is expected of any service businesses trust.
- Options considered: secret scanner: A) Gitleaks, installed from the release binary pinned by version and checksum · B) TruffleHog, which tests a found key by calling the service it belongs to. SBOM: A) Syft, Anchore's, like Grype · B) none until releases exist. Updates: A) Dependabot with a 7-day cooldown · B) Renovate, a third-party app with write access.
- Chosen: A in each.
- Reason: Gitleaks never sends a found key anywhere; a pinned checksum cannot be moved the way a tag can (the reason for D-064). Syft matches Grype's install and vendor. Dependabot is GitHub's own, needs no extra app with write access, and its cooldown keeps hijacked releases (tj-actions March 2025, Trivy March 2026) out while security fixes still arrive at once.
- Consequences / follow-ups: (1) CI scans the whole git history with Gitleaks 8.30.1 before installing anything; the three findings on the existing history were example idempotency keys in tests, listed by exact fingerprint in `.gitleaksignore`; shown to catch a planted key. (2) The image job writes the API image's CycloneDX SBOM with Syft 1.54.0 and keeps it 90 days (`actions/upload-artifact` v7.0.1, pinned to its SHA; v7.0.2 was a day old). (3) `.github/dependabot.yml`: uv, GitHub Actions, Docker, Compose and OpenTofu, weekly, 7-day cooldown, minor and patch grouped for Python; every update still needs founder approval to merge. (4) `SECURITY.md`: private reports through GitHub, response targets, scope, safe harbour, no bounty yet. (5) `GET /.well-known/security.txt` (RFC 9116): public, 60 a minute, cached a day; `Expires` 30 April 2027, and a test fails 30 days before it lapses as the renewal reminder. (6) `docs/INCIDENT_RESPONSE.md`: roles, the first hour, rotating each secret, taking the API down, DPDP notice (the clock from the validation pack), the write-up; **not yet rehearsed**. (7) Founder steps in the repository settings: switch on push protection and private vulnerability reporting. (8) Signing images waits for a registry (D-063). zizmor finds nothing in the workflow.

## D-083: Creator availability, "booked until": shown to brands, informs and never blocks
- Date: 2026-10-08
- Approved by: Adhi, in this session ("approve all, build them all in the best order"), for item 45 of `docs/BILLION_DOLLAR_GAP.md` with its gate (database).
- Context: Brands invite and shortlist creators who cannot take the work, and creators get applications nobody can act on; both find out only in a WhatsApp reply. A creator's own "booked until" date answers it before anyone asks.
- Options considered: A) one date, "booked until", that informs search and matching and blocks nothing · B) a calendar of bookable slots, as Passionfroot sells to newsletter and B2B creators · C) a yes/no switch
- Chosen: A.
- Reason: a single date is what an Instagram or YouTube creator in Tamil Nadu actually knows, and it is enough to rank and filter. B is richer and fits ad slots in newsletters, not reels; it can grow from A if pilot creators ask. C cannot say when they are free again. Passionfroot's slot calendar remains stronger for slot-sold media; ours is stronger in that it feeds straight into who a brand sees first.
- Consequences / follow-ups: (1) Column `creator.booked_until` (migration `f74cbe0d42c9`), nullable, no default, no index (only ever a filter on rows other conditions pick); the downgrade drops it, a preference the creator can set again. (2) `GET` and `PUT /api/v1/creators/me/availability`: from today to a year ahead, in Tamil Nadu days; null clears it. A passed date reads as taking work, worked out on every read, never cleared by a job. (3) Creator search returns each result's `booked_until` and takes `available_on` to keep only creators free that day. (4) A campaign's suggested creators put those taking work today first, booked ones after with the date. (5) **Not on the public Passport**: creators published it before this existed. (6) Nothing blocks: a booked creator can apply and be contacted. (7) In the creator's data export. 23 new tests; the four rules each shown to fail when broken.

## D-084: Brands invite creators, and "work together again" is a repeat invitation
- Date: 2026-10-10
- Approved by: Adhi, in this session, choosing option A for item 42 of `docs/BILLION_DOLLAR_GAP.md` ("A"), with its gate (database).
- Context: Every deal began with a creator applying. A brand that found the right creator in search, or wanted last month's creator again, could only hope they applied. Item 42 had been written up as "nothing new stored"; that was wrong, because a memo needs an accepted application and a brand had no way to create one.
- Options considered: A) a brand invites a creator to an open campaign, as an `application` row with origin 'invited'; "work together again" is an invitation naming the earlier deal, and accepting it drafts the memo from that deal's terms · B) a rebook button that only copies the old campaign as a new draft, leaving the creator to find it and apply.
- Chosen: A.
- Reason: B still waits on the creator to notice and apply; A puts the offer in front of them, and it also serves invitations from search, which impact.com and Skeepers both offer (their help pages, read 10 October 2026). As on impact.com's marketplace, accepting an invitation needs nothing more from the creator: the brand already chose them (help.impact.com, read 10 October 2026). Ours goes further for repeats: the memo arrives drafted with the agreed terms, and the brand sees the creator's delivery record (D-038) before choosing to repeat.
- Consequences / follow-ups:
  1. Migration `2c3bf71783d2` changes `application`:
     - adds `origin`, `invitation_note`, `decline_reason` and `repeat_of_application_id` (FK to `application`, RESTRICT, partial index);
     - makes `pitch` nullable, tied to the origin by a check;
     - adds the statuses 'invited' and 'declined';
     - adds the four invitation notification types, which a person may mute.
     
     Every check is added NOT VALID and validated after the transaction, and the index is built concurrently. The downgrade refuses while any invitation exists.
  2. `POST /campaigns/{id}/invitations` (brand), `POST /applications/{id}/accept-invitation`, `/decline-invitation` with a reason code (creator), `/withdraw-invitation` (brand), and `POST /deal-memos/{id}/repeat` (brand; an agreed, uncancelled deal whose fee suits the new campaign's type).
  3. Moves now depend on who makes them, so a creator declines an invitation and never withdraws the brand's offer.
  4. Policy: at most 25 unanswered invitations per campaign, held by a lock on the campaign row. There is no expiry: an invitation lasts while its campaign is open, and accepting needs it open and its brand not suspended.
  5. What changes for other features:
     - the creator's to-do list gains `answer_invitation`;
     - the brand's `draft_memo` item now also covers a memo written but never sent, which had been a gap;
     - creator feedback leaves invitations out;
     - the campaign summary counts `invited` and `declined`;
     - both sides' exports carry the new fields.
  6. A new test compares every CHECK in the models with the migrated database, which `alembic check` does not do.
  7. Tests: 83 new API tests and 2 concurrency tests. Sixteen rules were each shown to fail when broken.

## D-085: The UPI pay link, with the creator's UPI ID stored by consent
- Date: 2026-10-10
- Approved by: Adhi. Item 32 of `docs/BILLION_DOLLAR_GAP.md` was approved on 8 October ("approve all"), with its gate named as a founder decision on storing UPI IDs. After the plan to store them was put to him on 10 October, he confirmed it ("carry on working next").
- Context: A brand pays a creator by copying an amount and a UPI ID by hand, the most error-prone step in a deal. `docs/standards/database.md` section 4 forbade storing UPI identifiers without a founder decision.
- Options considered: A) store the creator's UPI ID with consent, and give the brand on the deal NPCI's `upi://pay` link while the payment is open · B) no stored ID: the creator types it into each deal · C) leave payment details off the platform.
- Chosen: A.
- Reason: It removes the step where money goes to the wrong place, and the money still moves only between the two banks (constraint 1). The design, its choices and its threat model are in `docs/decided/PROPOSAL_UPI_PAY_LINK.md`.
- Consequences / follow-ups:
  1. Table `creator_upi` (migration `e39beab4e841`), separate from `creator`, one row per creator. Its checks refuse a malformed ID and a phone-number ID. The downgrade refuses while any row exists, since each row is a consent record.
  2. `GET`, `PUT` and `DELETE /api/v1/creators/me/upi`, and `GET /api/v1/deal-memos/{id}/payment/pay-details` for the deal's brand while the payment is open (20 a minute).
  3. Rules:
     - no link above UPI's ₹1 lakh limit between people;
     - person-to-person fields only;
     - a UPI ID set in the last 24 hours is flagged to the brand.
  4. Off until the validation pack's notice exists: setting `UPI_NOTICE_VERSION` (`.env.example`, `infra/`) switches it on. Withdrawing always works.
  5. In the creator's data export.
  6. Tests: 51, and 13 rules shown to fail when broken.
  7. Owed: the notice wording, and trying the link on real phones with the main UPI apps before launch.
  8. `database.md` section 4 now names this decision.

## D-086: Adults only; contact details flagged, not hidden; 180-day logs; four CI checks
- Date: 2026-10-10
- Approved by: Adhi, in this session ("approve all"), on the four decisions put to him after the legal and trust-and-safety standards.
- Context: The legal research (`docs/standards/legal.md`) and the trust-and-safety review (`docs/standards/trust-and-safety.md`) found decisions only a founder could make, and CI gaps.
- Options considered and chosen:
  1. **Adults only** (chosen), over allowing minors with parental consent. A contract with a minor is void in India, and DPDP requires verified parental consent for their data. Creating a profile takes a date of birth, checked against today in Tamil Nadu. Only `account.adult_confirmed_at` is kept (migration `5cf8639be443`), never the date: the least the rule needs.
  2. **Contact details flagged, not hidden**, until there is an in-app chat to talk through instead (item 60).
  3. **Logs kept 180 days** (chosen), over 30, as CERT-In requires. OpenTofu refuses less.
  4. **CI** (all chosen):
     - every job on `ubuntu-24.04`, never `ubuntu-latest`;
     - a new `infrastructure` job running `tofu fmt -check` and `tofu validate` on every environment, OpenTofu 1.12.6 pinned by checksum;
     - a licence allow-list (pip-licenses 5.5.5) that fails on anything not approved;
     - proof and evidence links from a published host list (item 57).
- Reason: each closes a gap the research found, with the smallest change that does.
- Consequences / follow-ups:
  - Creating a profile now requires `date_of_birth`. No client exists yet (D-053), so tightening the contract costs nothing today.
  - Lawyer question 2 in `legal.md` section 4 asks whether a declared date is enough.
  - The persuasion levers we use, and the line each must not cross, are written into `legal.md` section 3.5.

## D-087: The founders' weekly numbers, as an admin view
- Date: 2026-10-10
- Approved by: Adhi, in this session ("carry on with the remaining docs then item 63"), for item 63, which the survival playbook proposed the same day.
- Context: `docs/SURVIVAL_PLAYBOOK.md` section 4 names the numbers that say each week whether the first city is dense enough and the business alive. They could only be counted by hand.
- Options considered: A) one admin endpoint, worked out from the records on every read · B) a stored daily snapshot table · C) counting by hand from the export.
- Chosen: A.
- Reason: "worked out, never stored" (`backend.md` section 2) keeps the numbers from drifting from the records, and it costs a fixed number of queries whatever the size. B would add a job and a second truth; C does not survive a busy week.
- Consequences / follow-ups:
  1. `GET /api/v1/admin/numbers`: admins only (404 for anyone else), 20 a minute. Any 1 to 90 Tamil Nadu days ending on `ending_on`, beside the same length before, optionally for one city.
  2. What it reports:
     - new and active brands and creators;
     - campaigns posted, and the fill rate (an agreed deal within 14 days);
     - median hours to a first application;
     - applications sent and accepted so far, and invitations;
     - deals agreed, their value, and the repeat share;
     - payments confirmed, and the share paid on time.
  3. Policy written into the code:
     - every rate is null below five examples;
     - a campaign counts towards the fill rate only once it is 14 days old;
     - a campaign still in draft is not counted;
     - a repeat is any deal between a pair that agreed one before.
  4. Totals only, naming no one, so reading it writes no admin log entry (D-061).
  5. A campaign's publishing time is not stored, so `created_at` stands in for it. A campaign kept long in draft looks slower to fill than it was.
  6. Tests: 19; ten rules each shown to fail when broken. Mutation testing found that nothing checked the period's last day at Tamil Nadu midnight, and a test now does.
