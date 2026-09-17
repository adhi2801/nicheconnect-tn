# Daily Engineering Report: 2026-09-17

**Branch:** `feature/creator-model` (built on `docs/quality-standards`)  ·  **Author:** Adhi  ·  **Pushed:** Yes (both branches)  ·  **PR:** not opened. Open [docs/quality-standards](https://github.com/adhi2801/nicheconnect-tn/compare/docs/quality-standards?expand=1) first, then [feature/creator-model](https://github.com/adhi2801/nicheconnect-tn/compare/feature/creator-model?expand=1)

## 1. Founder summary
- Quality standards are installed: a slimmer `CLAUDE.md` plus six binding files in `docs/standards/` (branch `docs/quality-standards`).
- The database now has the core identity tables: `creator` (new), `brand` (fixed), `account`, `otp_challenge` and `auth_session`. Each has its rules enforced by the database, and each has tests.
- Login design is decided: phone OTP for brands and creators, a 15-minute access token plus a rotating 30-day refresh token, and sync database code (D-007 to D-009).
- The token library python-jose (known security flaws) and the unused passlib were replaced with PyJWT (D-010).
- Tests went from 3 this morning to 79, all passing locally.
- Every migration was tested up → down → up. The Brand and account migrations were also tested on a database built with `main`'s older code.
- **For Erode:** older local databases get their Brand constraint names renamed automatically. If you have test brand rows, the account migration stops and asks you to delete them.
- **Next:** the login logic (settings, error format, OTP service, then endpoints). No endpoints exist yet beyond `/healthz`.

## 2. Work completed
| Task | Status | Evidence |
|---|---|---|
| Install quality standards; point DECISIONS.md at CLAUDE.md section 10 | Implemented (docs) | `62af270` |
| Constraint naming convention | Tested | `8c3333a`; `pytest` 79 passed |
| Creator table (D-005) | Tested | `8c3333a`, `tests/modules/auth/test_creator.py` |
| Brand length, lowercase-email and name rules; legacy constraint renames (D-006) | Tested | `8c3333a`, `test_brand.py`, legacy-database upgrade run this session |
| Account table and profile links (D-011) | Tested | `8c3333a`, `test_account.py`, unlinked-row stop run this session |
| OTP challenge table (D-007, D-011) | Tested | `8c3333a`, `test_otp_challenge.py` |
| Auth session table (D-008, D-011) | Tested | `8c3333a`, `test_auth_session.py` |
| Swap python-jose and passlib for PyJWT (D-010) | Tested | `4043485`; `pip check` clean; encode/decode smoke test; `pytest` passed |
| Shared test fixture and factories | Tested | `78b2646` |
| CI run for the pushed branches | Not verified | `gh` CLI not installed; check the Actions tab |

## 3. Files
### Created
| File | Purpose |
|---|---|
| `docs/standards/backend.md`, `database.md`, `security.md`, `testing.md`, `frontend.md`, `ux.md` | Binding quality standards |
| `app/modules/auth/models/creator.py` | Creator public profile (no contact details) |
| `app/modules/auth/models/account.py` | Login identity: phone and role |
| `app/modules/auth/models/otp_challenge.py` | Hashed one-time login codes |
| `app/modules/auth/models/auth_session.py` | Hashed rotating refresh-token sessions |
| `alembic/versions/15e894f4fe7e_add_creator_table.py` | Creates `creator` |
| `alembic/versions/c78f2f83c465_fix_brand_email_and_name_constraints.py` | Brand limits and rules; conditional legacy renames (hand-written) |
| `alembic/versions/0d4be8a8813a_add_account_table_and_link_brand_and_.py` | Creates `account`; adds `account_id` to brand and creator |
| `alembic/versions/a3547503e1e9_add_otp_challenge_table.py` | Creates `otp_challenge` |
| `alembic/versions/3d218c522ec6_add_auth_session_table.py` | Creates `auth_session` |
| `tests/conftest.py` | Shared rollback database fixture |
| `tests/factories.py` | Builders with obviously fake contact details |
| `tests/modules/auth/test_creator.py`, `test_account.py`, `test_otp_challenge.py`, `test_auth_session.py` | Database rule tests |
| `docs/reports/2026-09-17-feature-creator-model.md` | This report |
### Modified
| File | What changed | Why | Behaviour impact |
|---|---|---|---|
| `CLAUDE.md` | Replaced setup-wrapper form with the operating manual; added quality bar | SETUP_STANDARDS.md run as designed | Governance only |
| `docs/DECISIONS.md` | "section 9" → "section 10"; D-005 to D-011 added | Decision log | None |
| `app/db/base.py` | Naming convention on `Base.metadata` | database.md section 1 | New constraints get predictable names |
| `app/db/models.py` | Registers Account, AuthSession, Creator, OtpChallenge | Alembic discovery | None |
| `app/modules/auth/models/brand.py` | `name` 150 chars, `email` 320 chars, lowercase and not-blank rules, `account_id` link | D-006, D-011 | Mixed-case emails and blank names are rejected; a brand needs an account |
| `requirements.txt` | −python-jose, −passlib, +PyJWT 2.14.0 | D-010 | Reinstall required |
| `tests/modules/auth/test_brand.py` | Uses shared fixture and factories; 10 new tests | Cover D-006 and D-011 | None |
### Deleted
| File | Reason | Impact |
|---|---|---|
| `SETUP_STANDARDS.md` (never committed) | One-time setup file, per its own instructions | None |

## 4. API changes
None. No endpoints were added or changed.

## 5. Database changes
| Migration | Tables / columns / indexes | Downgrade tested | Impact |
|---|---|---|---|
| `15e894f4fe7e` add creator table | `creator`: 9 columns, 8 checks, unique handle, GIN index on niches | Yes | New table |
| `c78f2f83c465` fix brand email and name constraints | `brand.name` VARCHAR(150), `brand.email` VARCHAR(320), lowercase and not-blank checks; renames `brand_pkey`/`brand_email_key` where present; lowercases emails | Yes; also run on a legacy database, and on a case-duplicate database (stopped and rolled back as designed) | Stops if two emails differ only in capitals. Downgrade keeps new names and lowercased emails. |
| `0d4be8a8813a` add account table and link brand and creator | `account` (phone, role, 2 checks, unique phone); required unique `account_id` on brand and creator, `ON DELETE RESTRICT` | Yes; unlinked-row stop run on a throwaway database | Stops if brand or creator rows exist (test data only) |
| `a3547503e1e9` add otp challenge table | `otp_challenge`: 3 checks, index `(phone, created_at DESC)` | Yes | New table |
| `3d218c522ec6` add auth session table | `auth_session`: FK to account `ON DELETE CASCADE`, unique token hash, hash check, indexes on account_id and family_id | Yes | New table |

`alembic check` reported no drift between models and database after the last migration.

## 6. Testing
- **Commands run:** `pytest` (several times; final run in wrap-up), `pytest -v tests/modules/auth/<file>`, `alembic upgrade head` / `downgrade <rev>` / `downgrade base` / `upgrade head` for each migration, `alembic check`, `pip check`
- **Result:** 79 passed · 0 failed · 0 skipped (1 deprecation warning from Starlette's test client)
- **New tests:** 75 (22 creator, 16 account, 15 OTP challenge, 12 auth session, and 10 new in brand). 77 database tests in total, including the 2 original brand tests.
- **Not verified:** CI results for the pushed branches.

## 7. Commits pushed
```
78b2646 test(auth): cover constraints on auth and profile tables
8c3333a feat(auth): add creator, account, OTP and session tables
4043485 chore(deps): replace python-jose and passlib with PyJWT
62af270 docs(standards): add quality standards and slim CLAUDE.md
```
(plus this report's commit)

## 8. Decisions approved today
| ID | Decision | Approved by | Impact |
|---|---|---|---|
| D-005 | Creator table; `TEXT[]` niches and languages; English only; naming convention | Adhi | New table |
| D-006 | Brand lowercase email and length limits | Adhi | API must lowercase emails |
| D-007 | Phone OTP login for both roles | Adhi | Sending provider still to decide |
| D-008 | 15-minute access token plus rotating 30-day refresh token | Adhi | Session table; config change pending |
| D-009 | Synchronous SQLAlchemy | Adhi | Routes that use the database are plain `def` |
| D-010 | PyJWT replaces python-jose and passlib | Adhi | Reinstall |
| D-011 | Account, OTP challenge and session tables; Indian mobiles only; one role per account; `OTP_HASH_KEY` | Adhi | Three migrations |

## 9. Dependencies
| Package | Version | Reason | Approval ref |
|---|---|---|---|
| PyJWT (added) | 2.14.0 | Token signing and verification | D-010 |
| python-jose[cryptography] (removed) | 3.3.0 | Known flaws, unused | D-010 |
| passlib[bcrypt] (removed) | 1.7.4 | Not needed with OTP login, unused | D-010 |

## 10. Bugs found
| Severity | Description | Status |
|---|---|---|
| Medium | Constraint names depended on when a database was built: fresh databases got new names, older ones kept Postgres defaults | Fixed by the conditional rename in `c78f2f83c465`; tested on a legacy database |
| Low | Autogenerate produced an empty Brand migration and tried to add an unrelated rename to the Creator migration | Handled: Brand migration hand-written; rename removed from the Creator migration |

## 11. Technical debt
| Item | Why it exists | Risk | Cleanup plan |
|---|---|---|---|
| The database does not stop a creator profile linking to a brand-role account (or the reverse) | A database-level fix needs a composite foreign key | Medium once sign-up exists | Enforce in the sign-up service, with a test |
| Duplicate niches (e.g. `food, food`) are not blocked by the database | Hard to express as a CHECK | Low | Deduplicate in the API input schema |
| CI runs `alembic upgrade head` only | Existing workflow | Medium: downgrade bugs reach `main` | Add downgrade base → upgrade head (testing.md section 7, gate 4); infrastructure approval needed |
| `access_token_expire_minutes` is still 60 in config | Not touched yet | Low: no tokens issued yet | Set to 15 when adding `OTP_HASH_KEY` |
| OTP and expired-session rows are kept indefinitely | Retention period needs DPDP guidance | Low at pilot scale | Cleanup job after the validation pack and job-runner decision |
| D-004 approver still `<founder name>` | Carried over | Low | Erode confirms |

## 12. Blockers
| Blocker | Impact | What's needed | From whom |
|---|---|---|---|
| CI result unknown for both pushed branches | Can't mark CI green | Check the Actions tab | Adhi |
| Rule and cross-track changes need both founders | Standards PR and D-005 to D-011 were approved by Adhi only | Review and approve both PRs | Erode Harish |
| OTP sending provider and DLT rules | Real codes can't be sent | Provider decision; validation pack details | Both founders |

## 13. Health
| Area | Status | Why |
|---|---|---|
| Backend | 🟢 | App unchanged; models import cleanly |
| Database | 🟢 | 7 migrations at head; round trips and `alembic check` clean |
| APIs | 🟡 | Only `/healthz`; no auth endpoints yet |
| Tests & CI | 🟡 | 79 local tests pass; CI result for these branches not verified; CI lacks the downgrade check |
| Infrastructure | 🟢 | Docker Postgres and Redis healthy on this machine |

## 14. Next recommended tasks
1. **Open and review both PRs**, standards first. The Creator PR contains the standards commit until that PR merges.
2. **Check CI** on both branches, and fix it if red.
3. **Settings:** add `OTP_HASH_KEY`, set the access token to 15 minutes, and update `.env.example`. Needs infrastructure approval.
4. **Problem Details error format and request IDs**, shared by every endpoint.
5. **OTP service and endpoints** (`/api/v1/auth/otp/request`, `/otp/verify`), with a fake sender, injectable clock, rate limits and the role-match check.

_Not started automatically. Awaiting founder approval._

## 15. Handoff
- **Pick up from:** `feature/creator-model` at the report commit (code at `78b2646`)
- **Pending:** Both PRs to open and review; CI status; settings change for `OTP_HASH_KEY`.
- **Open questions:** OTP provider (SMS or WhatsApp, and which company)? DPDP retention for OTP and session rows? Erode's approval of D-004 to D-011 and the standards?
- **Watch out for:** After pulling, run `pip install -r requirements.txt`, then `alembic upgrade head`. Delete local test brand rows first if the account migration stops. Docker Postgres is on port 5433 locally. Read `docs/standards/` before coding.
- **First command to run:** `git fetch origin`
