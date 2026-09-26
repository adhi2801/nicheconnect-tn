# Product Backlog — backend view

What the product needs from this repository, in the order we should build it.

**Source:** the NicheConnect TN Product, Design & Build Playbook v1.0 (17 September 2026), plus the decisions in `docs/DECISIONS.md`. The playbook is product and design; this file translates it into backend work. What the playbook does not cover at all is listed in `docs/PLAYBOOK_GAPS.md`.

**Status words** follow `CLAUDE.md` section 6: *Proposed* (written up, not in the code), *Implemented* (in the code, not run), *Tested* (tests ran and passed this session), *Verified* (tested, plus behaviour confirmed by a founder).

**Nothing here is approved work.** Each item still needs a founder decision before it is built, and anything touching money status, matching or personal data re-reads `CLAUDE.md` section 2 first.

---

## 1. Guardrails that shape every item

- **No funds.** Brands pay creators directly. We record only what was claimed, when, and by whom. Every trust feature below is built from that evidence, never from holding money.
- **No personal data in embeddings.** Phone numbers and contact details stay out of anything used for matching.
- **Compliance is not invented.** ASCI disclosure rules and DPDP retention periods come from the validation pack. Items that depend on them are marked **needs validation pack**.

---

## 2. Built so far

Checked against the code on 23 September 2026, not from memory: 64 endpoints,
20 migrations, 1173 tests passing.

| Capability | Status | Where |
|---|---|---|
| Accounts, phone OTP login, tokens, sessions | Tested | `app/modules/auth/` (D-007, D-008, D-011, D-013) |
| Refresh, logout, log out of all devices, "who am I" | Tested | `app/modules/auth/router.py` |
| Role checks for endpoints (`CurrentBrand`, `CurrentCreator`) | Tested | `app/modules/auth/dependencies.py` |
| Brand and creator profiles, tables and endpoints | Tested | D-005, D-006, D-014 |
| Campaigns, applications, discovery with filters | Tested | `app/modules/campaigns/` (Phase A) |
| Deal memos, the payment handshake, disputes | Tested | `app/modules/deal_memo/`, `payment_status/`, `disputes/` (Phase B) |
| Creator Passport, application feedback | Tested | D-036, D-041 |
| One error format, request IDs, rate limits, safe settings | Tested | `app/core/` (D-003, D-012) |
| Repeat-safe writes (`Idempotency-Key`) | Tested | `app/core/idempotency.py` (D-040) |
| Data export | Tested | `app/modules/auth/export_service.py` |
| API fuzz testing, migration linting, measured budgets | Tested | D-047, D-050, `docs/PERFORMANCE.md` |

---

## 3. Build order

Each phase is only useful once the one before it exists. **Status is from the
code**, checked 23 September 2026.

### Phase A — the marketplace core — **done**
| # | Item | Status | Notes |
|---|---|---|---|
| A1 | `campaign` table and endpoints | **Done** | Money is whole paise; that decision is settled |
| A2 | `application` table and endpoints | **Done** | Status transitions with a stated table |
| A3 | Creator and brand profile endpoints | **Done** | Ownership checks on every read and write |
| A4 | Campaign discovery for creators | **Done** | Filters: city, niche, budget, type; cursor pagination |

### Phase B — the deal and the money handshake — **done**
| # | Item | Status | Notes |
|---|---|---|---|
| B1 | `deal_memo` table, accept flow both sides | **Done** | Terms, deliverables, usage-rights window |
| B2 | `payment_status`: brand marks paid, creator confirms | **Done** | Never implies we hold money (D-033) |
| B3 | Payment reference (UTR) recorded and matched | **Done** | Repeat-proof confirmation |
| B4 | Brand payment-reliability score | **Done** | D-034, D-035 |
| B5 | Disputes with an evidence timeline | **Done** | D-036; no verdict is ever recorded |

### Phase C — trust and fairness features — **2 of 5**
| # | Item | Status | Notes |
|---|---|---|---|
| C1 | Tamper-evident record of deal and payment events | **Not started** | Append-only, chained. Needs a new table: Data track, and a schema decision |
| C2 | Creator Passport: public read-only profile | **Done** | D-036 |
| C3 | Fair-rate guidance | **Not started** | Proposed only, in `docs/PROPOSAL_PASSPORT_RATE_CARD.md`; rate card decision 1 is still open |
| C4 | Structured rejection reasons and profile guidance | **Done** | D-041 |
| C5 | Usage-rights expiry reminders | **Blocked** | The window is stored; the reminder needs the job runner |

### Phase D — matching — **done**
Built 23–25 September (D-052). `app/modules/matching/` was an empty package;
it is now the embedding input builder, the embedder, the refresh service and
the endpoint, with 55 tests.

| # | Item | Status | Notes |
|---|---|---|---|
| D1 | Embedding input builder, with a test proving no personal data is included | **Done** | Fails closed: a new column on `creator` or `campaign` breaks the test until somebody decides which side it belongs on |
| D2 | pgvector similarity search for campaign ↔ creator | **Done** | `GET /api/v1/campaigns/{id}/matches`, p95 59.6 ms against a 300 ms budget. No ANN index: an exact scan over the filtered set is faster and always exactly right at this size |
| D3 | Explainable results: the reasons behind every match | **Done** | Shared niches, city, accepted deals, and the similarity score. Structural filter first, so the reasons are facts rather than a model's opinion |

**Still to do here, and both wait on other things:** embeddings are refreshed
by `scripts/refresh_embeddings.py` on a schedule, because no job runner is
chosen (D-047 locks DBOS, nothing is installed). And the creator-facing
direction — campaigns matched to a creator — is not built; only the brand
side is.

### Phase E — reach and workflow — **1 of 9**
| # | Item | Status | Notes |
|---|---|---|---|
| E1 | Notifications module: WhatsApp and SMS behind one interface | **Records only** | Rows are written; nothing is delivered. Provider undecided, which is also why nobody can log in off a laptop |
| E2 | WhatsApp actions (apply, accept, upload proof) | **Not started** | Needs E1 |
| E3 | Offline-first write contract | **Half** | `Idempotency-Key` is done (D-040); resumable uploads are not, and proof is a URL rather than a file |
| E4 | Campaign types: barter, commission, local-business | **Done** | `CAMPAIGN_TYPES` in `app/modules/campaigns/models.py` |
| E5 | City leaderboards, festival templates, creator collectives | **Not started** | Group applications need their own model |
| E6 | Invoices and yearly earnings statement | **Blocked** | needs validation pack (GST, TDS) |
| E7 | ASCI disclosure check before submission | **Blocked** | needs validation pack |
| E8 | Data export and account deletion | **Half** | Export is done. **Deletion is not, and no app store will accept us without it in the app** |
| E9 | Public read API and webhooks for agencies | **Not started** | After the contract is stable |

### Where that leaves us

**16 of the 26 items are done, about 62%.** Phases A, B and D are complete.

Of the **10 that remain**, the split matters more than the count:

| | Items | Why |
|---|---|---|
| **Buildable now** | C1, E5, E9 | Need a decision Claude can make and record, nothing external |
| **Waiting on an account or a decision** | C3, C5, E1, E2, E3 | The notification provider, the job runner, media storage, the rate card |
| **Waiting on the validation pack** | E6, E7, E8 | GST, TDS, ASCI and retention. `CLAUDE.md` constraint 6: ask, never invent |

**E1 is the one that matters most.** Until a notification provider exists,
nobody can log in outside a developer's laptop, so all 65 endpoints are
unreachable by a real person. It is one decision, and it also unblocks E2
and C5.

**Two launch blockers sit outside this list.** In-app account deletion does
not exist and no app store will accept either app without it (that is E8,
and E8 is validation-pack blocked). And DPDP consent-manager rules land
13 November 2026.

---

## 4. Decisions needed before the phases above

Checked 23 September 2026. **Four of the seven are still open, and each one
blocks a whole phase.**

| Decision | Blocks | Status |
|---|---|---|
| Money amounts: whole paise or decimal | A1 | **Settled:** whole paise, throughout the schema |
| Campaign types for the pilot | A1, E4 | **Settled:** paid, barter, commission, local business |
| Per-phone verify limit | Security hardening | **Done:** `MAX_VERIFY_ATTEMPTS_PER_WINDOW` in `app/modules/auth/service.py` |
| Job runner (for notifications and reminders) | E1, C5 | **Open.** No background worker exists. DBOS is locked as the choice (D-047) but nothing is installed |
| Notification provider (WhatsApp or SMS, and which company) | E1, C5, and real OTP delivery | **Open, and the most expensive one.** Until it is chosen **nobody can log in outside a developer's laptop** |
| Media storage (proof uploads) | E3 | **Open.** Proof is currently a URL the creator pastes, not a file we hold |
| How a developer logs in locally | Developer experience | **Open.** Codes are never logged, by design |

---

## 5. Cross-cutting quality work

| Item | Status |
|---|---|
| Move rate limits from memory to a shared store | **Done** (D-003; now Valkey, D-048) |
| Correct client IP behind a proxy | **Done** (`tests/core/test_client_ip.py`) |
| Add the migration downgrade check to CI | **Done** (`.github/workflows/ci.yml`) |
| Seed script with realistic data | **Done** (`scripts/seed_dev_data.py`) |
| Performance budgets measured, not estimated | **Done** for reads (`docs/PERFORMANCE.md`). **Writes are still unmeasured**, and so is anything under load |
| Backup and one tested restore | **Not started.** Waits on the hosting decision |

---

## 6. What would set us apart

From the playbook's gap table, the items below are the ones the backend can make real. They are proposals, not commitments.

1. **Provable trust, not claimed trust.** C1 and B4 together mean a brand's payment record and a creator's history can be checked, not just displayed.
2. **Explainable matching** (D3), including what a creator can do to match more often.
3. **Honest statistics** (C3, B4): always with sample size and date, and "not enough data yet" when that is the truth.
4. **A backend built for bad connections** (E3), so the Android app never creates duplicates or loses work.
5. **Disputes as evidence, not email** (B5).
6. **Fraud signals with reasons and an appeal path**, never a silent block. The playbook's research shows unexplained blocks are the loudest complaint in this market.
