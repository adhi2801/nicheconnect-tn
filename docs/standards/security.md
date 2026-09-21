# Security Standard

Applies to auth, permissions, secrets, PII, rate limiting and dependencies. Any change here needs founder approval (CLAUDE.md section 5).
Rules marked **(decision)** need a recorded decision before first use.

---

## 1. Authentication

- **(decision)** login method: phone OTP (via SMS or WhatsApp), email magic link, or both.
- **OTP rules** if chosen:
  - 6 digits, cryptographically random, valid for 5 minutes, single use.
  - Store only a hash of the OTP, never the plain value.
  - Maximum 5 verification attempts per OTP, then invalidate it.
  - Send limits per phone number and per IP (e.g. 3 per 10 minutes, 10 per day).
  - The same response whether or not the account exists.
- **(decision)** token strategy. Default recommendation: short-lived access token (15 minutes) plus a rotating refresh token (30 days) stored hashed server-side, so a session can be revoked. Reuse of an old refresh token revokes the whole session family.
- Signing keys come from the environment, are at least 256 bits, and support rotation (key ID in the token header).
- Logout revokes the refresh token. "Log out of all devices" revokes every session for the user.
- Passwords, if ever added: argon2id or bcrypt through a maintained library, never custom hashing.

## 2. Authorization

- Two roles to start: `brand` and `creator`. Admin access is a separate, audited role added only by decision.
- **Every** endpoint that reads or changes an object loads it through a dependency that checks ownership (for example, `get_campaign_owned_by_current_brand`). This is the main defence against Broken Object Level Authorization, the top API risk.
- Every such endpoint has a test proving another user gets 404 or 403.
- Filters use the authenticated user from the token, never an owner ID taken from the request body or query.
- Status transitions check the actor: only the brand can mark a payment as paid; only the creator can confirm it was received.

## 3. OWASP API Security Top 10 checklist

| Risk | Our control |
|---|---|
| Broken object level authorization | Ownership dependencies plus cross-user tests |
| Broken authentication | OTP and token rules above; auth routes strictly rate limited |
| Broken object property level authorization | Separate create/update/read schemas, `extra="forbid"`, allow-listed response fields |
| Unrestricted resource consumption | Rate limits, pagination caps, request body size limit (1 MB default), query timeouts |
| Broken function level authorization | Role checks on every route; admin routes separate |
| Unrestricted access to sensitive flows | Extra limits on OTP send, application submit, notification triggers |
| Server-side request forgery | No user-supplied URLs are fetched server-side without an allow-list |
| Security misconfiguration | Secure headers, CORS allow-list, debug off, `/docs` access decided before production |
| Improper inventory management | OpenAPI kept complete; old API versions retired on a schedule |
| Unsafe consumption of APIs | Timeouts, validation of third-party responses, retries with limits |

## 4. Rate limiting

| Route class | Starting limit | Keyed by |
|---|---|---|
| Default (all routes) | 60 / minute | IP, or user once authenticated |
| OTP send | 3 / 10 minutes, 10 / day | phone number and IP |
| OTP verify | 10 / 10 minutes | phone number and IP |
| Write endpoints (create/update) | 30 / minute | user |
| Search and matching | 30 / minute | user |

- Storage moves from memory to Redis before more than one app process runs (D-003).
- A 429 includes `Retry-After` and the standard error body.
- Limits are tuned from real traffic, not guessed upward.

## 5. Secrets

- Secrets live only in environment variables: `.env` locally (gitignored), platform secret settings in staging and production.
- Never in code, tests, logs, commit messages, reports or screenshots.
- `.env.example` holds placeholders only.
- A leaked secret is rotated immediately, even if the commit was deleted.
- CI uses test-only values.

## 6. PII and privacy

- Collect only what a feature needs. Every PII field has a stated purpose.
- PII stays out of logs, error messages, analytics events and embeddings.
- Contact details are shown only to the parties of an accepted deal, if at all. **(decision)**
- Consent, retention periods and deletion behaviour follow the DPDP guidance in the validation pack. Don't invent retention periods.
- Account deletion (`DELETE /me`) is tested end to end once the policy is decided.

## 7. Transport and headers

- HTTPS only outside local development; HSTS enabled in production.
- Response headers: `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `X-Frame-Options: DENY`, and a `Content-Security-Policy` on any HTML the API serves.
- CORS: explicit allow-list of frontend origins. Never `*` with credentials.

## 8. Dependencies and supply chain

- Every dependency is pinned in `requirements.txt` and approved (CLAUDE.md section 5).
- CI runs `pip-audit` on every push (D-031). Any known vulnerability blocks merge, not only high or critical ones, because most Python advisories carry no severity rating.
- Prefer well-maintained libraries with recent releases and many users. Avoid packages abandoned for over a year.
- Enable GitHub Dependabot alerts and secret scanning on the repository.

## 9. Before production (checklist)

- [ ] All items in sections 1–8 implemented and tested
- [ ] `/docs` exposure decided
- [ ] Debug mode off; generic 500 messages
- [ ] Database user for the app has no superuser rights
- [ ] Backups enabled and one restore tested
- [ ] Sentry PII scrubbing verified
- [ ] Dependency audit clean
