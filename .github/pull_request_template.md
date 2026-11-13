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

## Gates

- [ ] ruff, format, mypy, lint-imports, Squawk, migration round trip, gitleaks: run locally and passed
- [ ] The affected suites and the cross-cutting tests passed locally; the full suite runs in CI
- [ ] CI seen green on the exact commit to be merged
- [ ] Reviewed by the other founder, or this says plainly that no second person reviewed it
