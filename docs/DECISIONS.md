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
- Approved by: Adhi (Erode Harish still to confirm: CLAUDE.md section 3 needs both founders for architecture)
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
