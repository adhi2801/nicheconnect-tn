# Daily Engineering Report: 2026-09-22

**Branch:** `feature/attention`  ·  **Author:** Adhi  ·  **Pushed:** Yes  ·  **PR:** [#13](https://github.com/adhi2801/nicheconnect-tn/pull/13) (open, into `main`)

This report covers one commit, `9275be3`, made at 00:26 after the evening update to the 2026-09-21 report. It was already pushed. This wrap-up checked that, re-ran every check, and writes it up.

## 1. Founder summary

- **Everything is on GitHub.** Every local branch matches its remote copy, nothing is uncommitted, and there are no stashes. The two branches with no remote copy of their own (`feature/auth-refresh-logout`, `feature/profile-role-link`) have no commits that aren't already on GitHub.
- **New feature: "what needs my attention".** `GET /api/v1/me/attention` tells a brand or creator what is waiting on them, most urgent first. A brand sees applications to review, memos to draft or revise, proof to review before it approves itself, creators to pay, and disputes to answer. A creator sees memos to answer, work to deliver, payments to confirm, late payments owed to them, and disputes to answer.
- **Why it matters:** it warns people before their trust record changes. A brand sees a payment two days before it becomes late, while there is still time to pay.
- **Nothing new is stored.** Each item is worked out from existing records and disappears once it is done. No table, no migration, no new package.
- **Tests: 1,102 passing**, up from 1,078. Lint, formatting and strict type checks are clean. GitHub Actions is green on this commit for both the push run and the PR run.
- **PR #13 now carries the whole line of work:** 44 commits ahead of `main`, including migrations 17 to 20. PR #11 is still open and is entirely contained in #13.
- **Still needs Erode Harish:** his review of migrations 17 to 20 and the acknowledgement described in the 2026-09-21 report, section 15.

## 2. Work completed

| Task | Status | Evidence |
|---|---|---|
| `GET /api/v1/me/attention` for brands and creators | Tested | `9275be3`; 24 new tests, all passing in this session's full run |
| The delivery record's "approved, including by the clock" rule made shared, so the attention list and the delivery record always agree | Tested | `9275be3`, `app/modules/deal_memo/delivery_record.py` |
| API contract refreshed: one new path, two new schemas | Tested | `docs/api/openapi.json` in `9275be3`; the contract guard test passes |
| Checked that all work is pushed | Verified by evidence | `git fetch`, then every local branch compared with its remote copy |

## 3. Files

### Created

| File | Purpose |
|---|---|
| `app/core/attention.py` | The shared attention item and the "most urgent first" ordering |
| `app/modules/auth/attention_router.py` | The HTTP endpoint, rate limited |
| `app/modules/auth/attention_service.py` | Collects each module's items for the signed-in account |
| `app/modules/campaigns/attention.py` | Applications waiting for a brand's review |
| `app/modules/deal_memo/attention.py` | Memos, work and proof waiting on either side |
| `app/modules/payment_status/attention.py` | Payments to make, confirm, or chase |
| `app/modules/disputes/attention.py` | Disputes waiting for a response |
| `tests/modules/auth/test_attention_service.py` | Ordering, ties and the 50-item cap |
| `tests/modules/test_attention_api.py` | Every kind of item, tested end to end through real deals |

### Modified

| File | What changed | Why | Behaviour impact |
|---|---|---|---|
| `app/main.py` | Registers the attention router | New endpoint | One new endpoint |
| `app/modules/auth/schemas.py` | `AttentionRead` and its item schema | Response shape | None on existing endpoints |
| `app/modules/deal_memo/delivery_record.py` | "Approved, including by the clock" rule made public | So the attention list and the delivery record share one rule | None |
| `docs/api/openapi.json` | One path, two schemas | The contract guard requires it | None |

### Deleted

None.

## 4. API changes

| Method | Path | Purpose | Auth | Rate limited | Tests |
|---|---|---|---|---|---|
| GET | `/api/v1/me/attention` | What is waiting on the signed-in brand or creator, most urgent first | Signed-in account with a profile (409 without one) | 60/min | 24 |

Each item has a `kind` code plus the facts: due date, days left (on the India calendar), campaign, the other party, and the amount. The app supplies the wording, in Tamil and English. `counts` covers every kind for the role, including zeros. At most 50 items are returned, with `total` and `truncated`. Due dates follow decisions already made: D-025, D-027, D-028, D-033 and D-039.

## 5. Database changes

| Migration | Tables / columns / indexes | Downgrade tested | Impact |
|---|---|---|---|
| None | None | n/a | Read-only feature over existing tables |

## 6. Testing

- **Commands run (this session):** `venv/Scripts/python.exe -m pytest` (twice), then `venv/Scripts/python.exe -m pytest -o addopts="" -q` to get the totals line. Also `ruff check .`, `ruff format --check .` and `mypy`.
- **Result:** 1,102 passed · 0 failed · 0 skipped (56 s). Ruff: all checks passed; 193 files already formatted. Mypy (strict): no issues in 94 source files.
- **CI:** GitHub Actions green on `9275be3`: [push run](https://github.com/adhi2801/nicheconnect-tn/actions/runs/35641646511) and [PR run](https://github.com/adhi2801/nicheconnect-tn/actions/runs/35644066417). That includes the coverage gates.
- **Not run this session:** a local coverage figure and a performance measurement. The commit message reports p95 21 ms for a brand with 40 deals and 10 campaigns, against the 300 ms budget, and says five rules were broken on purpose and each broke its test. Both come from the earlier session and were **not re-verified** here.
- **New tests:** 24, covering: every kind of item appears when due and disappears when done; ordering; accounts can't see each other's items; profile required; rate limit; a constant number of queries; ties; the 50-item cap.

## 7. Commits pushed

Nothing new was pushed before this report. The one commit not yet reported, already on GitHub:

```
9275be3 feat(api): what needs my attention, for brands and creators
```

This report is committed and pushed on the same branch.

## 8. Decisions approved today

| ID | Decision | Approved by | Impact |
|---|---|---|---|
| None | No new entry in `docs/DECISIONS.md` | n/a | The feature adds no table, package or module. The approval for it came from the earlier session and **can't be confirmed from evidence here** |

## 9. Dependencies

None.

## 10. Bugs found

None.

## 11. Technical debt

| Item | Why it exists | Risk | Cleanup plan |
|---|---|---|---|
| Reminders are pull-only | Push reminders (D-029) wait on a job runner | People only see items when they open the app | Add push once the job runner is decided |
| `tests/modules/test_attention_api.py` sits outside any one module's folder | It covers four modules | Harder to find by the module-based test layout | Leave it, or agree a home for cross-module tests |
| Performance figure not re-measured this session | Measured in the earlier session only | Low: 21 ms against a 300 ms budget | Re-run with seeded data at the next performance pass |
| Carried: no CORS allow-list, `coverage` not pinned, `/docs` in production | See the 2026-09-21 report | As before | As before |

## 12. Blockers

| Blocker | Impact | What's needed | From whom |
|---|---|---|---|
| Review of migrations 17 to 20 and D-032 to D-036 | Data-track work landed without its owner; nothing can merge to `main` | Review on PR #13 (or #11), plus the acknowledgement in the 2026-09-21 report, section 15 | Erode Harish |
| Which PR to review: #11 or #13 | #13 contains all of #11 and more, so reviewing both doubles the work | A choice; recommended: review #13 and close #11 | Both founders |
| Decision 1 of the rate card proposal | Rate cards can't be built | Decision (two tables, one column) | Both founders |
| Brand and creator records public or not; DPDP retention (D-034 point 5, D-038 b and c) | Both records stay behind a login | Decision, and the validation pack | Both founders |

## 13. Health

| Area | Status | Why |
|---|---|---|
| Backend | 🟢 | 1,102 tests, strict types, lint clean |
| Database | 🟡 | No change today; migrations 17 to 20 still waiting for their track owner's review |
| APIs | 🟢 | One new read endpoint, rate limited, contract refreshed and guarded |
| Tests & CI | 🟢 | All pass locally; GitHub Actions green on push and PR |
| Infrastructure | 🔴 | No hosting, backups or job runner. Nothing deployed |

## 14. Next recommended tasks

1. **Erode Harish reviews PR #13, starting with migrations 17 to 20.** Nothing merges to `main` until he does, and #13 now covers the whole line in one place.
2. **Merge PR #12 (notice for Erode Harish)**, so his sessions show him the notice before he starts any task.
3. **Decide decision 1 of the rate card proposal.** It unblocks the next feature on the competitive build list, and Erode Harish implements the tables.

_Not started automatically. Awaiting founder approval._

## 15. Handoff

- **Pick up from:** `feature/attention`, at the report commit after `9275be3`. Pushed; PR #13 open into `main`.
- **Pending:** nothing uncommitted.
- **Open questions:** close PR #11 in favour of #13? Rate card decision 1. Whether the brand and creator records are ever public.
- **Watch out for:**
  - PR #13 is 44 commits and includes four Data-track migrations. Don't merge #11 and #13 separately without checking the order.
  - Any API change fails a test until `docs/api/openapi.json` is refreshed: `venv\Scripts\python.exe -m tests.openapi_snapshot`.
  - On Adhi's laptop, bare `python` points at another project's venv. Use `venv\Scripts\python.exe`.
- **First command to run:** `git fetch origin`
