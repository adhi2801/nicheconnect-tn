<!-- Every merge to main carries this evidence (CLAUDE.md sections 6 and 8, D-191).
     Write "none" where a line does not apply, and say why. Never tick what did not happen in this session. -->

## What and why

- What this changes, in plain words:
- Decision entry (D-NNN) in `docs/DECISIONS.md`, approved by whom and when:
- Finish-line item(s) and the capability that owns each (`docs/BACKEND_COMPLETE.md` section 2a):

## The eight steps, with evidence

1. **Constraints** (`CLAUDE.md` section 2) checked; none broken:
2. **Standards read in full** for this area (name each file):
3. **Research**, dated sources; the strongest competitor's version and how ours goes further:
4. **Proposal approved** before building, with all twelve dimensions; any change from it approved before it was built:
5. **Built** on its own branch, one file one job:
6. **Proof:**
   - Tests required by `docs/standards/testing.md` section 1 for each kind of change:
   - Every rule, guard and lock broken on purpose and seen failing (list each break and the test that caught it):
   - Concurrency test for each "only if" rule; query-count test for each list (two of every kind):
   - p95 of every new or changed route, measured (reads 300 ms, writes 500 ms):
   - Mutation floor held; new pure rules added to `[tool.mutmut]`:
   - Independent review: findings, and how each was fixed or answered:
7. **The whole job in this change:** code, tests, decision entry, OpenAPI snapshot and frontend types, the data export, `docs/BACKEND_COMPLETE.md`, `docs/README.md` and every document affected:
8. **Honest report:** what is not built or not proven:

## Definition of done (`CLAUDE.md` section 8)

- [ ] Proposed with all twelve dimensions and approved before it was built (step 4 above)
- [ ] Tests for the success case **and** the failure cases (validation, permission, not found), run in this session and passing
- [ ] Every public endpoint rate limited, with an access check on every object it reads or changes (owner, party, or public by design)
- [ ] Error format, pagination and naming match `docs/standards/backend.md`
- [ ] Schema changes only through a migration with a working downgrade
- [ ] No new dependency without a recorded approval (name the D-entry, or "none added")
- [ ] Every document it affects still meets the bar of `docs/README.md`

## Backend gates (write "none" if no backend file changed)

- [ ] ruff, format, mypy, lint-imports, Squawk, migration round trip, gitleaks: run locally and passed
- [ ] The affected suites and the cross-cutting tests passed locally; the full suite runs in CI

## Frontend (write "none" if nothing under `frontend/` changed)

- [ ] `pnpm --filter web lint`, `test` and `build` passed locally
- [ ] `pnpm --filter web e2e` passed locally: the browser tests and the axe accessibility check (WCAG 2.2 AA plus 7:1 body text, light and dark, motion on and off, phone and laptop)
- [ ] Lighthouse within `frontend/apps/web/lighthouserc.cjs`, no ratchet line loosened; the numbers CI printed:
- [ ] `pnpm audit` clean, or each accepted advisory listed with its reason in `frontend/pnpm-workspace.yaml` under a recorded decision
- [ ] Each new or changed screen meets `docs/standards/frontend.md` section 14: all five states (loading, empty, error, success, offline), at 360 px and at desktop width, in light and dark; every string in the catalogue; built against `docs/api/openapi.json`

## Merge

- [ ] CI seen green on the exact commit to be merged
- [ ] Reviewed by the other founder, or this says plainly that no second person reviewed it
