# Security Standard

**For:** anyone touching login, access, secrets, personal data, rate limits, dependencies or the workflows, read in full before the first file (`CLAUDE.md` section 6). Any change here needs founder approval (`CLAUDE.md` section 5). **Last checked against the code: 14 October 2026**, on branch `docs/standards-bar`. Every claim below was re-checked then. Six that had stopped being true were corrected; they are listed in section 11.

**The bar** is `CLAUDE.md` section 7.0. **The target is OWASP ASVS 5.0, Level 2**, the verification standard for applications holding personal and business data. Today this file maps our controls to the OWASP API Security Top 10 (section 3), not yet to ASVS chapter by chapter, so Level 2 is a target, not a claim (gap 2). Each rule says what **enforces** it. A rule nothing enforces is marked *(review only)*.

Rules marked **(decision)** need a founder decision in `docs/DECISIONS.md`. Rules marked **(not yet built)** are owed before launch and tracked in section 10.

**The ten dimensions** (`CLAUDE.md` section 5), and where this standard serves each:

| Dimension | Here |
|---|---|
| Quality | Every rule names its enforcement; section 3 maps each OWASP API risk to its proof |
| Security | All of it |
| Privacy and law | Section 7; the law itself is `legal.md` |
| Trust and safety | Blocks (2) and daily ceilings (5); the rest is `trust-and-safety.md` |
| Architecture | Every access check lives in `auth` (layer 1, `backend.md` section 1); the database's own user, section 9 |
| Performance | Rate limits and the overload answer protect capacity, section 5; the budgets are `backend.md` section 6 |
| Research | Section 12 |
| Novelty, design, business | Not here: security is judged against the standards, not competitors. What the screens show for errors is `backend.md` section 3 |

---

## 1. Authentication

- **Phone number plus a one-time code** by WhatsApp through MSG91, with SMS on the same account later (D-058). No passwords anywhere. For brands and creators that is one factor, possession of the phone: NIST's lowest assurance level, chosen for reach in Tamil Nadu (gap 3). Admins prove two (below).
- **Codes** (`app/modules/auth/tokens.py`, `service.py`):
  - 6 digits from `secrets.randbelow`, valid 5 minutes, single use.
  - Only an HMAC-SHA256 of the code is stored, keyed separately from the token key, and the app refuses to start if the two keys are the same (D-011).
  - **Guessing is capped per phone in the database, whatever the IP address** (D-018): 5 tries per code, and 10 wrong tries per phone in 10 minutes across all its codes, so asking for new codes buys no extra guesses.
  - **Sending is capped:** per phone 3 codes in 10 minutes and 10 a day (in the database); per IP 3 requests in 10 minutes (the limiter).
  - The answer is the same whether or not the number has an account.
  - **Enforced by** the OTP test suites, including concurrency tests (`tests/modules/auth/`).
- **Tokens (D-008):**
  - A 15-minute access token, plus a rotating 30-day refresh token stored hashed. Settings cannot raise either (`le=15`, `le=30`).
  - Reusing an old refresh token ends the whole session family (RFC 9700's reuse detection).
  - Logout ends one session; "log out everywhere" ends all of them and clears the push tokens (D-095).
  - Keys are at least 32 characters, read from the environment, and refused at startup when they are the `.env.example` placeholder. Infra generates 64 random letters and digits (about 380 bits); `.env.example` says to generate 256 bits. Tokens carry a key id (`kid`) so keys can be rotated.
  - **Enforced by** the token, refresh and session tests.
- **Admins** (D-061):
  - A separate role that login never creates.
  - An admin login is answered exactly like a wrong code for anyone who is not one.
  - **Two factors, in one request** (D-105): the phone code and the 6-digit code of an authenticator app (RFC 6238), at `/api/v1/auth/admin/login`; `/auth/otp/verify` never logs an admin in. Either code wrong is answered as a wrong phone code. Admin routes refuse a token whose `amr` lacks `mfa` (RFC 8176).
  - The authenticator's secret is encrypted at rest (AES-256-GCM under `SECOND_FACTOR_KEY`, bound to the account); each 30-second step's code works once, read under the factor's row lock; ten refused codes in a row lock it.
  - **Set up or replaced only through `scripts/make_admin.py --second-factor`**, a one-time ticket for 15 minutes, redeemed with a phone code: no API route, no recovery codes, no SMS fallback, so there is no help desk to talk round (ASVS 5.0 6.4.3, 6.4.4).
  - An admin session lasts 1 hour from each refresh, and never past 12 hours from the login (NIST SP 800-63B-4 section 2.2; ASVS 7.3.1, 7.3.2).
  - Every active admin is told, by a notification nobody can mute, of every admin sign-in, every second factor refused after a right phone code, and every ticket issued or redeemed (ASVS 6.3.5, 6.3.7).
  - **Enforced by** `tests/modules/admin/test_admin_login_api.py`, `test_admin_login_concurrency.py`, `tests/modules/auth/test_second_factor*.py` (RFC 6238's own vectors and property tests), `test_totp_factor_model.py` and `test_admin_login_api.py` in `auth`; each rule broken on purpose and seen caught.
  - Every view of an account's details and every admin action is written to the admin log with a reason. The log refuses updates and deletes at the database (`database.md` section 3).
  - **Enforced by** `tests/modules/auth/test_admin_login_api.py` and `tests/modules/admin/`.
- **A second check before a risky change** (item 82, D-107; ASVS 5.0 7.5.1 to 7.5.3):
  - setting a UPI ID, downloading the data export and logging out everywhere each need a 6-digit code from `POST /api/v1/me/step-up`, in the `Step-Up-Code` header;
  - a code works once, for 5 minutes, for one action and, for a UPI ID, that exact ID (only HMACs of the code and the value are stored); only the newest counts; 5 wrong tries use it up;
  - without one, 401 `step_up_required` with RFC 9470's `insufficient_user_authentication` challenge;
  - step-up codes and login codes share the phone's caps, for sending and for guessing, under one per-phone lock;
  - admins use their authenticator's code instead, under the login's rules;
  - **it does not stop a SIM swap**, since the code goes to whoever has the number: a new UPI ID therefore waits 24 hours before brands see it, the owner is told by a notification nobody can mute, and can cancel it without a code;
  - **enforced by** `tests/modules/me/test_step_up_api.py`, `tests/modules/payment_status/test_upi_hold_api.py`, `test_upi_step_up_concurrency.py`, and the property and model tests beside them; each rule broken on purpose and seen caught.
- A suspended account is refused at login, on refresh and on every request. **Enforced by** `tests/modules/auth/test_suspension_api.py`.
- **Sign-up details** (D-080) are read only by the login that creates the account, so nobody can rewrite them afterwards.
- **Adults only** (D-086): creating a profile checks a date of birth against today in Tamil Nadu and keeps only the time of the confirmation, never the date.

## 2. Authorization

- Roles: `brand`, `creator`, `admin`.
- **Every** endpoint that reads or changes an object loads it through a check that the caller may (owner, party to the deal, or public by design). This is the defence against Broken Object Level Authorization, the top API risk. The checks live in `auth` and each module's dependencies; routers build no queries of their own (`tests/test_architecture.py`).
- Every such endpoint refuses another user with 404 (preferred, so existence is not confirmed) or 403. **Enforced by** `tests/modules/test_stranger_routes.py` (item 100): it builds a real world through the API and calls every one of the 65 routes that name an object as an unrelated brand and an unrelated creator, with valid bodies, so a refusal is never a validation error; a 409 or 422 counts as a leak. Routes public by design are listed with who may read them and why, and must answer them. A new route fails the test until it is covered.
- Filters use the authenticated account from the token, never an owner id from the body or query. The person's own things live under `/me/...` with no id at all.
- Status transitions check the actor: only the brand marks a payment as sent; only the creator confirms it arrived. **Enforced by** the payment tests, including properties over every state.
- Admin endpoints answer 404 to anyone who is not an admin.
- **An item withheld for legal reasons** (item 52, D-104) answers **451** to everyone but its owner, and only where it was public: a draft or an unpublished Passport still reads as not found, so withholding never reveals what was private. The owner's own attempts to start something new from it are 409 (`own_content_withheld`). **Enforced by** `tests/modules/safety/test_takedown_visibility_api.py`.
- **A block is respected everywhere one account could reach another** (item 59): no invitation, repeat or application either way, and neither appears in the other's search, matches or discovery. The check is a condition inside each query, and every refusal reads as not found, so a block is never revealed. A new route that reaches someone respects blocks in the same change, with a test in `tests/modules/safety/test_block_api.py`.

## 3. OWASP API Security Top 10 (2023)

| Risk | Our control | Proven by |
|---|---|---|
| API1 Broken object level authorization | Access checks on every object | `tests/modules/test_stranger_routes.py`, every object route (item 100) |
| API2 Broken authentication | Section 1; auth routes strictly rate limited | OTP, refresh and session test suites |
| API3 Broken object property level authorization | Separate create, update and read schemas; every request body refuses unknown fields; public responses built by hand | `tests/test_architecture.py` (all 39 bodies); contract fuzzing |
| API4 Unrestricted resource consumption | Rate limits, bounded lists, a 1 MB body limit, statement timeouts, a cap on requests in flight (D-093), daily ceilings on paid APIs | Limit tests; 413 tests; the load test (D-092) |
| API5 Broken function level authorization | Role checks on every route; admin routes separate and 404 | Role tests |
| API6 Unrestricted access to sensitive business flows | Extra limits on code sending, applications, bulk payments; **a daily ceiling per account on everything that reaches another person** (item 58); a code for each risky change, and a 24-hour wait on a new UPI ID (item 82) | `tests/modules/test_daily_ceilings.py` reads the registered limits; `tests/modules/me/test_step_up_api.py` |
| API7 Server-side request forgery | No user-supplied URL is fetched; a brand's domain check (item 74) asks two fixed DNS-over-HTTPS resolvers and the registry IANA names, about one validated name, never a URL; proof and evidence links are stored, never fetched, and accepted only from a published host list with phishing shapes refused (item 57, `app/core/links.py`) | `tests/core/test_links.py` |
| API8 Security misconfiguration | Security headers on every response, CORS allow-list, docs off in production (D-044) | Header tests, 500s included |
| API9 Improper inventory management | Committed OpenAPI contract; a test fails on any unannounced change | Contract tests |
| API10 Unsafe consumption of APIs | Timeouts, validation of third-party responses, bounded retries | Sender and reader tests |

## 4. Threat modelling

**Every feature that touches money records, personal data, login or an outside service gets a short threat model before it is built**, in its proposal's Security and Trust-and-safety lines (`CLAUDE.md` section 5). Under the STRIDE headings it names who could abuse it and how, what stops each abuse, and which test proves that. *(review only)*

Examples:
- the invite code (D-080): rewriting attribution after sign-up is stopped by reading it only when the account is created;
- the payment record: a brand "confirming" its own payment is stopped by the actor check;
- UPI IDs (D-085): the threat model is in `app/modules/payment_status/upi_service.py`.

## 5. Rate limiting

| Route class | Limit | Keyed by |
|---|---|---|
| Default, for any route without its own | 60 a minute | the account, or the address when signed out |
| Code send | 3 in 10 minutes | the address (the phone's caps are in section 1) |
| Code verify | 10 in 10 minutes | the address (the phone's caps are in section 1) |
| Asking for a step-up code (item 82) | 3 in 10 minutes, 10 a day | the account (and the phone's caps, shared with login codes) |
| Refresh and logout | 30 a minute | the address |
| Writes | 30 a minute, most with a daily ceiling | the account |
| Search and matching | 30 a minute | the account |
| Public pages | 60 a minute | the address |

- **Every route is limited**: the limiter's middleware gives any route without its own limit the default. **Enforced by** `tests/test_api_contract.py` (every operation documents its 429) and `tests/test_rate_limit.py` (routers use the typed decorator).
- Anything that reaches another person also has a daily ceiling (`trust-and-safety.md` rule 2).
- Counters live in Valkey (D-003, D-048), shared by every process.
- A 429 carries `Retry-After` and the standard error body.
- Limits are tuned from real traffic, never guessed upward.

## 6. Secrets

- Secrets live only in environment variables: `.env` locally (gitignored), AWS Secrets Manager in staging and production (`infra/`).
- Never in code, tests, logs, commit messages, reports or screenshots. The app refuses to start on a placeholder value.
- A leaked secret is rotated at once, even if the commit was deleted. Every secret has a rotation step in `docs/INCIDENT_RESPONSE.md`. **Enforced by** `tests/test_incident_response.py`.
- **Secret scanning blocks a merge:** Gitleaks reads the whole git history on every CI run (D-082); findings that are not secrets are listed one by one, by exact fingerprint, in `.gitleaksignore`. GitHub push protection was switched on by Adhi on 10 October 2026.

## 7. Personal data and privacy (DPDP)

- **Collect only what a feature needs**, and give every personal field a stated purpose. The purpose is written in the data export, which every table either joins or explains its absence from. **Enforced by** `tests/modules/me/test_export_api.py`.
- Personal data stays out of logs, error messages, analytics events, traces, embeddings (constraint 2) and error reports (D-074 scrubs before sending; D-094 traces carry none). **Enforced by** the scrubber's and tracer's tests for reports and traces; *(review only)* for log lines (`backend.md` section 9).
- Contact details are never shown on public pages; the Passport has none (D-036).
- **Consent is a recorded event with a timestamp, never a default** (D-036: nobody is public until they choose).
- Consent wording, retention periods, deletion, and the consent-manager rules that take effect on 13 November 2026 follow the validation pack (constraint 6). Nothing is invented.
- **A personal-data breach is reported to the Data Protection Board and to the people affected within the time the DPDP Rules set** (the validation pack confirms the clock), and a cyber incident to CERT-In within 6 hours (CERT-In directions of 28 April 2022). The plan is `docs/INCIDENT_RESPONSE.md`; the law behind both is `docs/standards/legal.md` sections 3.1 and 3.2.
- Account deletion is tested end to end once the policy is decided (E8).

## 8. Transport and headers

- HTTPS only outside local development; HSTS in production.
- On every response, errors and 500s included (D-045):
  - `X-Content-Type-Options: nosniff`;
  - `Referrer-Policy: no-referrer`;
  - `X-Frame-Options: DENY`;
  - a `Content-Security-Policy` chosen by path.
- CORS: an explicit allow-list in `CORS_ALLOWED_ORIGINS`, each origin written exactly as a browser sends it. Never `*`; no cookies across sites (D-044).
- **Enforced by** `tests/core/test_security_headers.py` and the CORS tests.

## 9. Supply chain and operations

- **Dependencies:**
  - Every dependency is pinned, approved (`CLAUDE.md` section 5) and locked with hashes in `uv.lock` (D-072); only the app's own group reaches a server.
  - `pip-audit` blocks merge on any known vulnerability (D-031).
  - Prefer maintained libraries with recent releases; avoid anything abandoned for over a year. *(review only)*
- **CI:**
  - Every action is pinned to a commit hash, credentials are not persisted, and permissions are least-privilege.
  - zizmor audits the workflows on every run (D-047), which enforces all three.
- **Images:**
  - Slim base images pinned by digest; the app's environment has no pip.
  - Grype blocks merge on any fixable vulnerability; accepted risks are listed one by one with a reason and an expiry condition (D-064, D-074).
- **Dependency updates:** Dependabot proposes updates weekly as pull requests, for Python, the CI actions, the base images, Compose and OpenTofu, each held 7 days after release; security fixes come at once (`.github/dependabot.yml`, D-082). Each still needs a founder's approval to merge. It runs: its updates were merged to `main` on 12 October (FastAPI, SQLAlchemy 2.1, the AWS provider and more).
- **Licences:** every dependency's licence is on an approved list, checked in CI (D-086).
- **SBOM:** a CycloneDX bill of materials of the API image, written by Syft on every CI run and kept 90 days (D-082); published with each release once releases exist.
- **To add before launch:** signed images with provenance (Sigstore cosign, SLSA build level 2) **(not yet built: waits for a registry to push images to, D-063)**.
- **Least privilege in AWS:** the app's IAM role can reach only its own proof-file folder in its bucket, and its secrets through the execution role. **The app's database login is least privilege** (item 97, D-100): it reads and writes rows and nothing more, and on the sealed tables only reads and adds, and on takedowns never deletes (item 52), so it cannot switch off a seal, remove a preserved takedown or drop a table. Only the release step connects as the owner (`database.md` section 8). Proven by `tests/modules/test_app_role.py`, and by CI running the suite as that login.
- **Incident response:** `docs/INCIDENT_RESPONSE.md` covers who is called, how to rotate every secret, how to take the API down safely, and how to tell people (D-082). **Rehearsal not yet done**: once on staging before launch.
- **Disclosure:** `SECURITY.md` (report privately through GitHub, response targets, safe harbour) and `/.well-known/security.txt` (RFC 9116) on the API, whose `Expires` a test makes us renew (D-082). Private vulnerability reporting is on, and CI fails if it is switched off (testing.md gate 13).

## 10. Before production (checklist)

- [ ] Sections 1 to 9 implemented and tested, the items marked "not yet built" included
- [x] `/docs` exposure decided: off in production (D-044)
- [x] Generic 500 messages with every header (D-045)
- [x] Error reports scrubbed of personal data, proven by tests (D-074)
- [x] **The app's database login owns nothing and can only read and write rows** (item 97, D-100); still to confirm in staging once deployed
- [ ] Backups enabled and one restore tested (`database.md` section 8)
- [ ] Dependency audit and image scan clean on the release commit
- [x] Secret scanning in CI and Dependabot configured and running (D-082)
- [x] Push protection and private vulnerability reporting switched on in the repository settings (Adhi, 10 October 2026; private reporting confirmed through GitHub's API, and CI checks it on every run)
- [x] `SECURITY.md`, `security.txt`, incident plan written (D-082)
- [ ] Incident plan rehearsed on staging
- [ ] The open code-scanning alert on GitHub read and fixed or accepted (gap 1)
- [ ] An outside penetration test of the API, findings fixed or accepted by a founder **(decision: who and when)**
- [ ] The validation pack's DPDP items in force (consent, retention, breach notice)

## 11. Gaps, named

**Closed on 17 October:** a stolen session setting a creator's UPI ID, taking their export or logging them out everywhere with the token alone (item 82, D-107).

**Closed on 16 October:** admins logging in with one factor, and admin sessions renewing for a day at every refresh with no overall limit (item 101, D-105).

**Closed on 14 October:** the app connecting to the database as the table owner (item 97, D-100), and no mechanical proof that every object route refuses a stranger (item 100, D-102). **A claim of mine corrected the same day:** this file said nothing had been merged to `main` since 1 October and Dependabot had never run; a stale local copy of `main` misled me, and both were false.

**Corrected on 14 October:** the database user "has no superuser rights" (it owned every table; fixed the same day by item 97); this file "maps our controls to ASVS" (it maps the API Top 10: gap 2); keys "at least 256 bits" (the app enforces 32 characters; the generators give 256 bits or more); the guessing cap (it is also 10 wrong tries per phone in 10 minutes, across codes); the code-send limit "per IP, 10 a day" (the daily cap is per phone only); and a refresh and logout limit the table had left out.

| # | Gap | Risk | Acting on it |
|---|---|---|---|
| 1 | **A code-scanning alert is open on GitHub and nobody here has read it** (https://github.com/adhi2801/nicheconnect-tn/security/code-scanning/1). GitHub's API needs a login to read it even on a public repository (checked 14 October). No workflow here uploads results, so it is likely GitHub's default CodeQL setup | Unknown until read | A founder reads it, or signs in to `gh` so it can be read here |
| 2 | **No chapter-by-chapter ASVS 5.0 mapping** | "Level 2" cannot be claimed | Map V1 to V17 before the penetration test, so the tester checks what we claim |
| 3 | **Brands and creators log in with one factor**, and the admins' second factor (D-105) can still be phished in real time, as any typed code can | A SIM swap is a brand's or creator's account; a convincing fake admin page could take both admin codes. Since item 82 a stolen session cannot change where a creator is paid, but a SIM swap still gets every code, so a new UPI ID's 24-hour wait and an in-app alert are the only answer to it; nothing yet delivers that alert outside the app (E1) | Passkeys (item 79) for everyone, admins first, once the domain and an admin web page exist |
| 4 | Incident plan not rehearsed; no penetration test; images not signed | Untested plans fail when needed | Section 10 |

## 12. Sources

Each link checked to exist on 14 October 2026.

- [OWASP ASVS](https://owasp.org/www-project-application-security-verification-standard/) (5.0, May 2025) and the [OWASP API Security Top 10, 2023](https://owasp.org/API-Security/editions/2023/en/0x11-t10/).
- [OWASP Authorization cheat sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): deny by default, check every object.
- [NIST SP 800-63B-4](https://pages.nist.gov/800-63-4/sp800-63b.html): authenticators, one-time codes, assurance levels.
- [RFC 9700](https://www.rfc-editor.org/rfc/rfc9700): OAuth 2.0 security best current practice, refresh token rotation and reuse detection. [RFC 8725](https://www.rfc-editor.org/rfc/rfc8725): JSON Web Token best current practices.
- [OWASP Secure Headers Project](https://owasp.org/www-project-secure-headers/).
- [STRIDE, as Microsoft's threat modelling tool defines it](https://learn.microsoft.com/en-us/azure/security/develop/threat-modeling-tool-threats).
- [CERT-In directions of 28 April 2022](https://www.cert-in.org.in/PDF/CERT-In_Directions_70B_28.04.2022.pdf): 6-hour incident reporting.
- [RFC 9116](https://www.rfc-editor.org/rfc/rfc9116): `security.txt`.
- A second check before risky changes (read 17 October 2026, D-107): [RFC 9470](https://www.rfc-editor.org/rfc/rfc9470) (OAuth 2.0 step-up authentication challenge); [OWASP ASVS 5.0, V7 Session Management](https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x16-V7-Session-Management.md) section 7.5; [NIST SP 800-63B-4, authenticator events](https://pages.nist.gov/800-63-4/sp800-63b/events/); [the EBA on dynamic linking](https://www.eba.europa.eu/single-rule-book-qa/qna/view/publicId/2018_4414); [Upwork's hold on a new withdrawal method](https://support.upwork.com/hc/en-us/articles/211060918); [SBI on UPI's limits after a new device or PIN](https://sbi.co.in/web/yono/blog/understand-upi-transaction-limits-cooling-period-and-payment-tips).
- The admins' second factor (read 16 October 2026, D-105): [RFC 6238](https://www.rfc-editor.org/rfc/rfc6238) (TOTP) and [RFC 8176](https://www.rfc-editor.org/rfc/rfc8176) (`amr` values); [OWASP ASVS 5.0, V6 Authentication](https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x15-V6-Authentication.md) and [V7 Session Management](https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/en/0x16-V7-Session-Management.md); [Cloudflare on the 2022 phishing attack](https://blog.cloudflare.com/2022-07-sms-phishing-attacks); [Help Net Security on the Retool breach](https://www.helpnetsecurity.com/2023/09/14/retool-breach/); [BleepingComputer on help-desk MFA resets](https://www.bleepingcomputer.com/news/security/3-key-takeaways-from-the-scattered-spider-attacks-on-insurance-firms/).
- [SLSA levels](https://slsa.dev/spec/v1.0/levels): build provenance.
- [Gitleaks](https://github.com/gitleaks/gitleaks), [zizmor](https://docs.zizmor.sh/), [GitHub push protection](https://docs.github.com/en/code-security/secret-scanning/introduction/about-push-protection).

## 13. How this file is kept true

- Re-checked against the code whenever it is read for work, and at least monthly with `docs/PLATFORM_AND_TECH_PLAN.md`'s review.
- A rule that gains enforcement says so; a rule found untrue is corrected in the same change (`docs/README.md` section 0).
