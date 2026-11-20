# Contributing to NicheConnect TN

**What this is:** how a change gets from your machine to `main`, for anyone writing code or docs here: a founder, a new teammate, or an AI assistant working for one. **Who reads it:** everyone, before their first change. **Checked against the code on 19 November 2026.** The rules themselves live in `CLAUDE.md` and `docs/standards/`; this page only says where to find them and what the machine will check, so it cannot drift from them.

## 1. Before you write anything

1. **Read `CLAUDE.md` in full once.** Its section 2 lists the non-negotiable constraints (we never hold money; no personal data in embeddings; schema only through migrations; every public endpoint rate limited; tested or not done; no guessed compliance; never claim work that did not happen).
2. **Read the standard for the area you are touching, in full**, before the first line. The table is `docs/README.md` section 1: `docs/standards/backend.md`, `database.md`, `security.md`, `trust-and-safety.md`, `legal.md`, `testing.md`, `frontend.md` (with `docs/research/TAMIL_DESIGN_ROOTS.md`) and `ux.md`.
3. **Get the change approved before building it** if it is a feature or touches a gate (`CLAUDE.md` section 5: dependencies, database, security, payments or matching, architecture, infrastructure, scope). A feature's proposal weighs the twelve dimensions in `CLAUDE.md` section 5. Approved decisions are recorded in `docs/DECISIONS.md`, in the same change as the work.

## 2. How a change reaches `main`

`main` is protected by the GitHub ruleset "main protection" (id 27525028, read back from GitHub's API on 19 November 2026). Nothing reaches it except through these steps:

1. **A branch of your own**, named `feature/<name>`, `fix/<name>`, `chore/<name>` or `docs/<name>` (`CLAUDE.md` section 6). Never commit to `main`.
2. **Small commits** in Conventional Commits style, for example `feat(campaigns): close applications at midnight in Tamil Nadu`.
3. **A pull request to `main`**. It needs:
   - **every required CI job green** on a branch up to date with `main`: `test`, `frontend`, `image`, `infrastructure` and `repository-settings` (`.github/workflows/ci.yml`), and CodeQL with no open alert of error severity and no security alert of high severity or above;
   - **an approving review from a code owner** (the CODEOWNERS file in `.github/`, which names Adhi for the whole repository; it lands with pull request #131), from someone other than the last person who pushed;
   - **approval of the latest push**: a new push dismisses earlier approvals, so the pull request is approved again after every change;
   - every review conversation resolved.
4. **No force-push to `main`, and `main` is never deleted.** Rewriting shared history is refused.

Only the repository admin can bypass the ruleset, and only to merge work whose CI is already seen green on the exact commit (`CLAUDE.md` section 6, D-101). A bypass is said in the pull request, with the reason.

## 3. What "done" means

A change is done only when it meets `CLAUDE.md` section 8. In short:

- **Tested for real**: the tests `docs/standards/testing.md` section 1 requires for that kind of change, run and passing; every new rule or guard broken on purpose and seen to fail its test, then restored.
- **Measured, not claimed**: speed against the budgets (`docs/PERFORMANCE.md` for the API, `frontend.md` section 4 for pages), from a tool.
- **The whole job in one change**: code, tests, the decision entry, the OpenAPI snapshot if the API changed, and every document it makes untrue.
- **Reviewed**: an independent review (the `fault-finder` brief, `.claude/agents/fault-finder.md`) reads the whole change and every finding is fixed or answered.
- **Honest**: the pull request says what was not done, not measured or not reviewed.

## 4. Running the checks yourself

Developers use Windows PowerShell 5: one command per line, never joined with `&&`.

**Backend** (Python 3.14 through uv, `CLAUDE.md` section 4):

```powershell
docker compose up -d
uv sync
uv run alembic upgrade head
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run lint-imports --no-cache
```

**Frontend** (from `frontend/`, pnpm through Corepack):

```powershell
corepack pnpm install --frozen-lockfile
corepack pnpm --filter web lint
corepack pnpm --filter web test
corepack pnpm --filter web build
corepack pnpm --filter web e2e
```

CI runs more than these (the secret scan, migration round trip, API fuzzing, image scan, the design tokens' contrast, the API types against `docs/api/openapi.json`); `.github/workflows/ci.yml` is the full list, each step commented with the rule it enforces.

## 5. The frontend in particular

- **Screens are built against the committed contract**, `docs/api/openapi.json`. A screen that needs a field the API does not answer is a backend request, never a workaround in the client (`CLAUDE.md` section 0).
- **Every string lives in the message catalogue**, never in a component; every colour, size and duration comes from the tokens in `frontend/tokens/`.
- **Every screen designs five states** (loading, empty, error, success, offline), works at 360 px and on a laptop, in light and dark, by keyboard and screen reader (`frontend.md` sections 5, 6 and 14).
- **Every visual choice traces to a root** in `docs/research/TAMIL_DESIGN_ROOTS.md` or `docs/PSYCHOLOGY_AND_TRUST.md`, and nothing reads as the BJP's: no lotus, no saffron or orange (D-143, `frontend.md` section 8a). Other parties' marks are not banned; a sunrise appears only as natural light in a scene, never as an emblem.

## 6. Words we never use

Anywhere, including commit messages: the four money words in `CLAUDE.md` constraint 1. We never receive, hold or move campaign money; brands pay creators directly. `tests/test_banned_terms.py` fails the build if one appears.

## 7. Gaps, named

- This page names the checks; it cannot make anyone read a standard. The checks in CI and the review are what hold the bar.
- Several rules in the standards are still checked by review rather than by machine; each standard names its own (`testing.md` section 11, `frontend.md` section 12's "still owed" list).
