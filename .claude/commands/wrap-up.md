---
description: End-of-session routine. Verify the work, commit, push the branch, and write the Daily Engineering Report.
---

# Wrap-up

The founder typing `wrap up` (or `/wrap-up`) **is approval to commit and push the current feature branch**, provided every safety check below passes. Anything outside this routine still needs normal approval.

Work through the phases in order. Never skip one. If a **STOP** condition is hit, stop, explain it in plain English, give the exact fix, and ask how to proceed. Do not work around it.

Developers use Windows PowerShell: run commands one at a time.

---

## Phase 1: Collect evidence

Run and read the output of:

```
git branch --show-current
git status --short
git log --oneline -15
git log --oneline @{u}..HEAD
git diff --stat
git diff --cached --stat
```

If `@{u}` errors, the branch has no upstream yet. Note that and continue.

Also gather:
- Test commands actually run this session, and their results
- `docs/DECISIONS.md` entries added today
- Any migrations under `alembic/versions/` added or changed
- Any change to `requirements.txt`

---

## Phase 2: Safety checks

| Check | How | If it fails |
|---|---|---|
| Not on `main` | branch name | **STOP.** Offer to create `feature/<name>` from the current changes |
| No merge conflicts in progress | `git status` | **STOP** |
| No secrets staged or unstaged | Look for `.env`, `*.pem`, `*.key`, `id_rsa`, lines like `SECRET_KEY=`, `API_KEY=`, `TOKEN=` with real values, and anything under `venv/` | **STOP.** Unstage it and suggest a `.gitignore` entry |
| Restricted vocabulary | Search the changed files for the four banned terms in `CLAUDE.md` section 2 | **STOP.** List the file and line numbers |
| No large or generated files | Files over 5 MB, `__pycache__`, build output | **STOP** |
| Dependencies approved | Every new package in `requirements.txt` has an approval in this session or in `docs/DECISIONS.md` | **STOP.** List the unapproved packages |
| Migrations reviewed | Every new migration was shown to and approved by a founder | **STOP** |

---

## Phase 3: Tests

Run `pytest`.

- **All pass:** continue.
- **Failures:** **STOP.** Show a summary of the failing tests and their likely cause. Ask:
  - A) fix now
  - B) commit to the branch marked work-in-progress, push, and note the failures prominently in the report
  - C) don't commit
- **Can't run** (for example, Docker is off): say so, ask whether to continue, and mark tests "Not run" in the report.

Never report tests as passing unless they ran in this phase or earlier in this session.

---

## Phase 4: Commit

1. Show the list of files to be committed, grouped as new, modified and deleted.
2. Group the changes into logical commits, at most one per concern, using Conventional Commits:
   `feat(scope): …`, `fix(scope): …`, `test(scope): …`, `docs: …`, `chore: …`
   If tests failed and the founder chose B, prefix the subject with `wip:`.
3. Stage files **by name** (`git add path/to/file`), never `git add .` or `git add -A`.
4. Commit. Messages must not contain the restricted vocabulary.

If there is nothing to commit and nothing unpushed, skip to Phase 6 and say so.

---

## Phase 5: Push

1. `git fetch origin`
2. If the remote branch has commits you don't have: **STOP.** Explain, and ask before `git pull` (merge, not rebase).
3. Push:
   - No upstream yet: `git push -u origin <branch>`
   - Otherwise: `git push`
4. Confirm by running `git log --oneline @{u}..HEAD`. It must print nothing.
5. If the push fails (auth, network, rejected): **STOP.** Show the error, explain it in plain English, and give the exact fix. Do not retry with force.
6. Give the PR link: `https://github.com/adhi2801/nicheconnect-tn/compare/<branch>?expand=1`. Never merge it.

---

## Phase 6: Write the Daily Engineering Report

Save it to `docs/reports/YYYY-MM-DD-<branch-name>.md`, then commit it on the same branch (`docs: add engineering report YYYY-MM-DD`) and push again, running the Phase 5 checks.

Also print the **Founder summary** section in the chat.

Use this template. Write every section; put "None" where nothing applies.

```markdown
# Daily Engineering Report: YYYY-MM-DD

**Branch:** `<branch>`  ·  **Author:** <founder>  ·  **Pushed:** Yes / No  ·  **PR:** <link or "not opened">

## 1. Founder summary
<Max 8 bullets, plain English, readable in 2 minutes: what got done, what changed for users or the team, what's blocked, what's next.>

## 2. Work completed
| Task | Status | Evidence |
|---|---|---|
| <task> | Proposed / Implemented / Tested / Verified | <commit hash, test name> |

## 3. Files
### Created
| File | Purpose |
|---|---|
### Modified
| File | What changed | Why | Behaviour impact |
|---|---|---|---|
### Deleted
| File | Reason | Impact |
|---|---|---|

## 4. API changes
| Method | Path | Purpose | Auth | Rate limited | Tests |
|---|---|---|---|---|---|

## 5. Database changes
| Migration | Tables / columns / indexes | Downgrade tested | Impact |
|---|---|---|---|

## 6. Testing
- **Commands run:** <exact commands>
- **Result:** <n> passed · <n> failed · <n> skipped. If not run, say "Not run" and why.
- **New tests:** <list>

## 7. Commits pushed
<output of `git log --oneline` for commits pushed in this session>

## 8. Decisions approved today
| ID | Decision | Approved by | Impact |
|---|---|---|---|

## 9. Dependencies
| Package | Version | Reason | Approval ref |
|---|---|---|---|

## 10. Bugs found
| Severity | Description | Status |
|---|---|---|

## 11. Technical debt
| Item | Why it exists | Risk | Cleanup plan |
|---|---|---|---|

## 12. Blockers
| Blocker | Impact | What's needed | From whom |
|---|---|---|---|

## 13. Health
| Area | Status | Why |
|---|---|---|
| Backend | 🟢 / 🟡 / 🔴 | |
| Database | 🟢 / 🟡 / 🔴 | |
| APIs | 🟢 / 🟡 / 🔴 | |
| Tests & CI | 🟢 / 🟡 / 🔴 | |
| Infrastructure | 🟢 / 🟡 / 🔴 | |

## 14. Next recommended tasks
1. <highest priority>: why
2. <next>
3. <later>

_Not started automatically. Awaiting founder approval._

## 15. Handoff
- **Pick up from:** <branch, last commit>
- **Pending:** <unfinished work and state>
- **Open questions:** <for the other founder>
- **Watch out for:** <warnings, assumptions>
- **First command to run:** `<command>`
```

---

## Phase 7: Close

End with exactly these lines in the chat:

```
Wrap-up complete
Branch:   <branch>  (pushed ✓ / not pushed ✗)
Tests:    <n passed / n failed / not run>
Report:   docs/reports/<file>.md
Next:     open PR → <link>   |   or: <blocker to resolve>
```

Do not start new work after wrap-up.
