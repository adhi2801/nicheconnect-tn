---
description: Short handover so the other founder can continue this work immediately. Read-only, no commits.
---

# Handoff

Read-only. Don't modify, commit or push anything. If there are uncommitted or unpushed changes, say so at the top and recommend running `wrap up` first.

Collect evidence first:

```
git branch --show-current
git status --short
git log --oneline -10
git log --oneline @{u}..HEAD
```

Also check the latest file in `docs/reports/` and recent entries in `docs/DECISIONS.md`.

Print this in the chat. Keep it under one screen and use plain English.

```markdown
# Handoff: <branch> · YYYY-MM-DD

⚠️ <Only if relevant: "3 files uncommitted / 2 commits not pushed. Run wrap up first.">

**Goal of this branch:** <one line>

**Done**
- <item> (Tested / Implemented / Proposed)

**Not done yet**
- <item>: <current state>

**Open decisions** (need a founder)
- <decision>: options A / B

**Blockers**
- <blocker>: <what unblocks it>

**Watch out for**
- <gotchas, assumptions, fragile areas>

**To continue**
1. `git fetch origin`
2. `git checkout <branch>`
3. `git pull`
4. `docker compose up -d`
5. `pytest`  → expect <n> passed
6. Next task: <specific next step>

**Suggested first prompt for Claude Code**
> I'm continuing branch <branch>. <Done summary>. Next: <task>. Follow CLAUDE.md learning format.
```
