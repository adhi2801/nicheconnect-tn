---
description: Review real progress, explain where the project stands in plain words, and give each founder one clear, non-overlapping task for today.
---

# Assign task

A founder typed `assign task`. Produce today's plan for **both** founders.

This is a **read-and-plan command**: don't write code, don't change source files, don't commit and don't push. The only file you may create is today's assignment file (Phase 5).

Write for someone who is still learning the codebase: plain English, no unexplained jargon, and always say **why** a task matters, not only what to do.

---

## Phase 1: Look at what is actually there

Never assign from memory. Gather evidence first:

```
git fetch origin
git branch -a
git log --oneline -20 origin/main
git log --oneline -10
git status --short
```

Then read:

- `docs/reports/` — the two or three most recent daily reports (what was last done, what was blocked)
- `docs/DECISIONS.md` — what is already decided, and what is still open
- `docs/assignments/` — the most recent assignment file, to see what was assigned last time
- `CLAUDE.md` sections 1 and 7, and the relevant `docs/standards/` files
- The repository itself: which modules exist, which have routers, models, tests; which migrations exist

Also run, if the environment allows it:

```
pytest -q
```

If the tests can't run (Docker off, for example), say so and mark the test state "not run" instead of guessing.

## Phase 2: Work out where the project stands

Map what exists against the phase plan (Phase 1 foundation, Phase 2 core schema and auth, Phase 3 marketplace endpoints and privacy, Phase 4 API hardening, Phase 5 matching, Phase 6 deal memo, payment status and notifications, Phase 7 deployment).

For each phase, decide **Done / In progress / Not started**, and say what evidence proves it. Never mark something done because it was assigned; it's done when the code, the tests and a merged pull request exist.

## Phase 3: Choose today's two tasks

Pick exactly **one main task per founder**, plus at most one small stretch task each.

Rules for choosing:

1. **Right size.** A task should take one focused session, roughly 2–4 hours, and end with something merged.
2. **Unblocks the next step.** Prefer work the other phase depends on. Say what it unblocks.
3. **Respects the tracks.** API work goes to Adhi, data work to the other founder (CLAUDE.md section 1).
4. **No overlapping files.** List each task's files and check the two lists share nothing. If they must share a file, keep the file with one founder and give the other founder a different task today.
5. **One migration in flight.** If the data task adds a migration, no other migration is assigned today.
6. **Decisions first.** If a task needs an open decision (login method, money type, sync vs async), the task for today is to *present the options and get the decision*, not to build on a guess.
7. **Don't assign work that needs an unmerged pull request.** Say "waiting on PR #N" instead.

## Phase 4: Print the plan in the chat

Use exactly this shape:

```
ASSIGN TASK · <date>

WHERE WE ARE (plain words)
<4–6 short lines: what the backend can do today, what it still can't, what merged
since the last assignment, and anything broken. No jargon.>

PROGRESS
| Phase | State | Evidence |
|---|---|---|
| 1 Foundation | Done / In progress / Not started | <commit, file or test> |
| … | | |

Backend completion: roughly <N>% — <one line on how that was judged>

─────────────────────────────────────────

ADHI (API track)
Task:        <one sentence>
Why:         <what this unblocks, and why it matters to brands or creators>
Files:       <exact files to create or change>
Branch:      feature/<name>
Steps:       1. … 2. … 3. …   (small, in order)
Done when:   <checkable result, e.g. "POST /api/v1/campaigns returns 201 and 4 tests pass">
Standards:   <which docs/standards/ file to read first>
Needs approval on: <anything gated, or "nothing">
Estimated:   <hours>
Start with:  "<the exact prompt to paste into Claude Code>"

ERODE HARISH (Data track)
Task:        …
Why:         …
Files:       …
Branch:      feature/<name>
Steps:       …
Done when:   …
Standards:   …
Needs approval on: …
Estimated:   …
Start with:  "<the exact prompt to paste into Claude Code>"

NO OVERLAP CHECK
<List both file sets and state plainly that they don't touch the same files.
If either task later needs a file from the other list, stop and re-plan.>

TOGETHER (15 minutes, before you start)
- <decisions to settle, PRs to review for each other, anything to agree on>

WATCH OUT FOR
- <risks, gotchas, things that broke last time>

IF YOU FINISH EARLY
- Adhi: <small next thing>
- Erode Harish: <small next thing>

END OF DAY
Each of you: type `wrap up`, then open your pull request and review the other's.
```

## Phase 5: Save it

Write the same content to `docs/assignments/<YYYY-MM-DD>.md`, creating the folder if needed, so both founders and the next session can see what was assigned. Don't commit it; the next `wrap up` will.

If an assignment file for today already exists, read it first and produce an **update** rather than a duplicate: what got done since, what stays, what changes.

## Rules

- Never invent progress. Every claim points to a commit, a file, a test result or a report.
- Never assign both founders the same file, the same module or two migrations.
- If a founder has uncommitted work or an unmerged pull request, the first task of the day is to finish that.
- If the project is blocked on a founder decision, say so at the top and make the decision the task.
- Keep the whole output shorter than two screens. Depth goes into the reasons, not into length.
