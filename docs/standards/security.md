# Security Standard

Applies to auth, permissions, secrets, personal data, rate limiting and dependencies. Any change here needs founder approval (`CLAUDE.md` section 5). The bar is `CLAUDE.md` section 7.0.

**Target: OWASP ASVS 5.0, Level 2.** This is the verification standard for applications handling personal and business data, and this file maps our controls to it. Rules marked **(decision)** need a recorded decision; rules marked **(not yet built)** are owed before launch and tracked in section 10.

---

## 1. Authentication

- **Phone number plus a one-time code** by WhatsApp through MSG91, with SMS on the same account later (D-058). No passwords anywhere.
- **Codes:**
  - 6 digits, cryptographically random, valid 5 minutes, single use.
  - Only an HMAC of the code is stored, keyed separately from the token key (D-011).
  - At most 5 tries per code, counted per phone in the database whatever the IP address (D-018).
  - Sending is limited per phone and per IP.
  - The answer is the same whether or not the number has an account.
- **Tokens (D-008):**
  - A 15-minute access token, plus a rotating 30-day refresh token stored hashed.
  - Reusing an old refresh token revokes the whole session family.
  - Logout revokes one session; "log out everywhere" revokes all of them.
  - Keys are at least 256 bits, read from the environment, and carry a key id (`kid`) so they can be rotated.
- **Admins** (D-061):
  - A separate role that login never creates.
  - An admin login is answered exactly like a wrong code for anyone who is not one.
  - Every view of an account's details and every admin action is written to the admin log with a reason.
- A suspended account is refused at login, on refresh and on every request.
- **Sign-up details** (D-080) are read only by the login that creates the account, so nobody can rewrite them afterwards.

## 2. Authorization

- Roles: `brand`, `creator`, `admin`.
- **Every** endpoint that reads or changes an object loads it through a dependency that checks the caller may (owner, party to the deal, or public by design). This is the defence against Broken Object Level Authorization, the top API risk.
- Every such endpoint has a test proving another user gets 404 (preferred, so existence is not confirmed) or 403.
- Filters use the authenticated account from the token, never an owner id from the body or query. The person's own things live under `/me/...` with no id at all.
- Status transitions check the actor: only the brand marks a payment as sent; only the creator confirms it arrived.
- Admin endpoints answer 404 to anyone who is not an admin.

## 3. OWASP API Security Top 10 (2023)

| Risk | Our control | Proven by |
|---|---|---|
| API1 Broken object level authorization | Access dependencies on every object | Cross-user tests on every endpoint |
| API2 Broken authentication | Section 1; auth routes strictly rate limited | OTP and refresh test suites |
| API3 Broken object property level authorization | Separate create/update/read schemas, `extra="forbid"`, hand-built public responses | Schema tests; contract fuzzing |
| API4 Unrestricted resource consumption | Rate limits, pagination caps, 1 MB body limit, statement timeouts, daily ceilings on paid APIs | Limit tests; 413 tests |
| API5 Broken function level authorization | Role checks on every route; admin routes separate and 404 | Role tests |
| API6 Unrestricted access to sensitive business flows | Extra limits on code sending, applications, bulk payments | Limit tests |
| API7 Server-side request forgery | No user-supplied URL is fetched; proof links are stored, never fetched | Code review |
| API8 Security misconfiguration | Security headers on every response, CORS allow-list, docs off in production (D-044) | Header tests, 500s included |
| API9 Improper inventory management | Committed OpenAPI contract; a test fails on any unannounced change | Contract tests |
| API10 Unsafe consumption of APIs | Timeouts, validation of third-party responses, bounded retries | Sender and reader tests |

## 4. Threat modelling

**Every feature that touches money records, personal data, login or an outside service gets a short threat model before it is built.** The proposal names, under the STRIDE headings:
- who could abuse it and how;
- what stops each abuse;
- which test proves that.

Examples:
- the invite code (D-080): rewriting attribution after sign-up is stopped by reading it only when the account is created;
- the payment record: a brand "confirming" its own payment is stopped by the actor check.

## 5. Rate limiting

| Route class | Starting limit | Keyed by |
|---|---|---|
| Default | 60 / minute | IP, or the account once signed in |
| Code send | 3 / 10 minutes, 10 / day | phone and IP |
| Code verify | 10 / 10 minutes | phone and IP |
| Writes | 30 / minute | account |
| Search and matching | 30 / minute | account |
| Public pages | 60 / minute | IP |

- Counters live in Valkey (D-003, D-048), shared by every process.
- A 429 carries `Retry-After` and the standard error body.
- Limits are tuned from real traffic, never guessed upward.

## 6. Secrets

- Secrets live only in environment variables: `.env` locally (gitignored), AWS Secrets Manager in staging and production (`infra/`).
- Never in code, tests, logs, commit messages, reports or screenshots. The app refuses to start on a placeholder value.
- A leaked secret is rotated at once, even if the commit was deleted.
- **Secret scanning blocks a merge:** Gitleaks reads the whole git history on every CI run (D-082); findings that are not secrets are listed one by one, by exact fingerprint, in `.gitleaksignore`. GitHub push protection on the repository stops most before they are pushed **(a founder switches it on in the repository settings)**.

## 7. Personal data and privacy (DPDP)

- **Collect only what a feature needs**, and give every personal field a stated purpose. The purpose is written in the data export, which every table either joins or explains its absence from (a test enforces it).
- Personal data stays out of logs, error messages, analytics events, embeddings (constraint 2) and error reports (D-074 scrubs before sending).
- Contact details are never shown on public pages; the Passport has none (D-036).
- **Consent is a recorded event with a timestamp, never a default** (D-036: nobody is public until they choose).
- Consent wording, retention periods, deletion, and the consent-manager rules that take effect on 13 November 2026 follow the validation pack (constraint 6). Nothing is invented.
- **A personal-data breach is reported to the Data Protection Board and to the people affected within the time the DPDP Rules set** (the validation pack confirms the clock). The response plan is in section 9 **(not yet built)**.
- Account deletion is tested end to end once the policy is decided (E8).

## 8. Transport and headers

- HTTPS only outside local development; HSTS in production.
- On every response, errors and 500s included (D-045):
  - `X-Content-Type-Options: nosniff`;
  - `Referrer-Policy: no-referrer`;
  - `X-Frame-Options: DENY`;
  - a `Content-Security-Policy` on any HTML.
- CORS: an explicit allow-list in `CORS_ALLOWED_ORIGINS`, each origin written exactly as a browser sends it. Never `*`; no cookies across sites (D-044).

## 9. Supply chain and operations

- **Dependencies:**
  - Every dependency is pinned, approved (`CLAUDE.md` section 5) and locked with hashes in `uv.lock` (D-072); only the app's own group reaches a server.
  - `pip-audit` blocks merge on any known vulnerability (D-031).
  - Prefer maintained libraries with recent releases; avoid anything abandoned for over a year.
- **CI:**
  - Every action is pinned to a commit hash, credentials are not persisted, and permissions are least-privilege.
  - zizmor audits the workflows on every run (D-047).
- **Images:**
  - Slim base images pinned by digest; the app's environment has no pip.
  - Grype blocks merge on any fixable vulnerability; accepted risks are listed one by one with a reason and an expiry condition (D-064, D-074).
- **Dependency updates:** Dependabot proposes updates weekly as pull requests, for Python, the CI actions, the base images, Compose and OpenTofu, each held 7 days after release before it is proposed; security fixes come at once (`.github/dependabot.yml`, D-082). Each still needs a founder's approval to merge. **Dependabot reads its settings only from the default branch, so it starts once `.github/dependabot.yml` is merged to `main`.**
- **To add before launch:**
  - an SBOM (CycloneDX) of the API image, written by Syft on every CI run and kept 90 days (D-082); published with each release once releases exist;
  - signed images with provenance (Sigstore cosign, SLSA build level 2) **(not yet built: waits for a registry to push images to, D-063)**.
- **Least privilege in AWS:** the app's IAM role can reach only its own bucket and its own secrets; the database user has no superuser rights.
- **Incident response:** `docs/INCIDENT_RESPONSE.md` covers who is called, how to rotate every secret, how to take the API down safely, and how to tell people (D-082). A test fails if a secret the app is given, or a password OpenTofu generates, has no rotation step (`tests/test_incident_response.py`). **Rehearsal not yet done**: once on staging before launch.
- **Disclosure:** `SECURITY.md` (report privately through GitHub, response targets, safe harbour) and `/.well-known/security.txt` (RFC 9116) on the API, whose `Expires` a test makes us renew (D-082). **A founder switches on private vulnerability reporting in the repository settings**; CI fails until it is on (testing.md gate 13).

## 10. Before production (checklist)

- [ ] Sections 1 to 9 implemented and tested, the items marked "not yet built" included
- [x] `/docs` exposure decided: off in production (D-044)
- [x] Generic 500 messages with every header (D-045)
- [x] Error reports scrubbed of personal data, proven by tests (D-074)
- [ ] Database user without superuser rights, verified in staging
- [ ] Backups enabled and one restore tested (`database.md` section 8)
- [ ] Dependency audit and image scan clean on the release commit
- [x] Secret scanning in CI and Dependabot configured (D-082)
- [ ] Push protection and private vulnerability reporting switched on in the repository settings
- [x] `SECURITY.md`, `security.txt`, incident plan written (D-082)
- [ ] Incident plan rehearsed on staging
- [ ] An outside penetration test of the API, findings fixed or accepted by a founder **(decision: who and when)**
- [ ] The validation pack's DPDP items in force (consent, retention, breach notice)
