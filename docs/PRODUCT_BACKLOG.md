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

| Capability | Status | Where |
|---|---|---|
| Accounts, phone OTP login, tokens, sessions | Tested | `app/modules/auth/` (D-007, D-008, D-011, D-013) |
| Refresh, logout, log out of all devices, "who am I" | Tested | `app/modules/auth/router.py` |
| Role checks for endpoints (`CurrentBrand`, `CurrentCreator`) | Tested | `app/modules/auth/dependencies.py` |
| Brand and creator profile tables, tied to their account role | Tested | D-005, D-006, D-014 |
| One error format, request IDs, rate limits, safe settings | Tested | `app/core/` (D-003, D-012) |

---

## 3. Build order

Each phase is only useful once the one before it exists.

### Phase A — the marketplace core (next)
| # | Item | Why it comes first | Notes |
|---|---|---|---|
| A1 | `campaign` table and endpoints | Everything else points at a campaign | Needs the money-amount decision (paise or decimal) before the first budget field |
| A2 | `application` table and endpoints | The creator's way in; the brand's shortlist | Status transitions with a stated table |
| A3 | Creator and brand profile endpoints | Profiles exist as tables but have no API | Ownership checks on every read and write |
| A4 | Campaign discovery for creators | The "Opportunities" screen | Filters: city, niche, budget, type; cursor pagination |

### Phase B — the deal and the money handshake
| # | Item | Notes |
|---|---|---|
| B1 | `deal_memo` table, accept flow both sides | Terms, deliverables, usage-rights window |
| B2 | `payment_status`: brand marks paid, creator confirms | Never implies we hold money |
| B3 | Payment reference (UTR) recorded and matched | Repeat-proof confirmation |
| B4 | Brand payment-reliability score | Median days to pay, dispute rate, sample size, computed from B2 events |
| B5 | Disputes with an evidence timeline | Both sides see the same ordered facts |

### Phase C — trust and fairness features
| # | Item | Notes |
|---|---|---|
| C1 | Tamper-evident record of deal and payment events | Append-only, chained, verifiable by both parties |
| C2 | Creator Passport: public read-only profile | Verified facts only; no contact details |
| C3 | Fair-rate guidance | Built from completed deals; always published with sample size and date |
| C4 | Structured rejection reasons and profile guidance | Answers "no campaigns, no idea why" |
| C5 | Usage-rights expiry reminders | The playbook puts this in v2; it is cheap once B1 exists |

### Phase D — matching
| # | Item | Notes |
|---|---|---|
| D1 | Embedding input builder, with a test proving no personal data is included | `CLAUDE.md` section 2 |
| D2 | pgvector similarity search for campaign ↔ creator | Index and parameters decided after measuring |
| D3 | Explainable results: the reasons behind every match | Niche overlap, city, rate fit, past completion |

### Phase E — reach and workflow
| # | Item | Notes |
|---|---|---|
| E1 | Notifications module: WhatsApp and SMS behind one interface | Provider still undecided; retries and repeat-safety required |
| E2 | WhatsApp actions (apply, accept, upload proof) | Signed links; the conversation state lives in the backend |
| E3 | Offline-first write contract: repeat-proof requests, resumable uploads | What makes low-data mode safe on patchy 4G |
| E4 | Campaign types: barter, commission, local-business | Playbook growth features |
| E5 | City leaderboards, festival templates, creator collectives | Group applications need their own model |
| E6 | Invoices and yearly earnings statement | **needs validation pack** (GST, TDS) |
| E7 | ASCI disclosure check before submission | **needs validation pack** |
| E8 | Data export and account deletion | **needs validation pack** (retention) |
| E9 | Public read API and webhooks for agencies | After the contract is stable |

---

## 4. Decisions needed before the phases above

| Decision | Blocks | Notes |
|---|---|---|
| Money amounts: whole paise or decimal | A1 | One choice for the whole schema |
| Campaign types for the pilot | A1, E4 | Paid, barter, commission, local business |
| Job runner (for notifications and reminders) | E1, C5 | Until decided, no background worker exists |
| Notification provider (WhatsApp or SMS, and which company) | E1, and real OTP delivery | Also unblocks real logins |
| How a developer logs in locally | Developer experience | Codes are never logged, by design |
| Media storage (proof uploads) | B1, E3 | Where files live, and how they are served safely |
| Per-phone verify limit | Security hardening | Known gap from the automated review |

---

## 5. Cross-cutting quality work

| Item | Why |
|---|---|
| Move rate limits from memory to Redis | Required before more than one process runs (D-003) |
| Correct client IP behind a proxy | Otherwise every user shares one limit |
| Add the migration downgrade check to CI | `docs/standards/testing.md` gate 4 |
| Seed script with realistic Tamil Nadu data | Needed for performance checks |
| Performance budgets measured, not estimated | p95 ≤ 300 ms reads, ≤ 500 ms writes |
| Backup and one tested restore | Before production |

---

## 6. What would set us apart

From the playbook's gap table, the items below are the ones the backend can make real. They are proposals, not commitments.

1. **Provable trust, not claimed trust.** C1 and B4 together mean a brand's payment record and a creator's history can be checked, not just displayed.
2. **Explainable matching** (D3), including what a creator can do to match more often.
3. **Honest statistics** (C3, B4): always with sample size and date, and "not enough data yet" when that is the truth.
4. **A backend built for bad connections** (E3), so the Android app never creates duplicates or loses work.
5. **Disputes as evidence, not email** (B5).
6. **Fraud signals with reasons and an appeal path**, never a silent block. The playbook's research shows unexplained blocks are the loudest complaint in this market.
