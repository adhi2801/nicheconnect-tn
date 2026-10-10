# The docs, and when each is read

Every file here has one job. If two files start doing the same job, one of them goes. `CLAUDE.md` (at the root) is the only file read at the start of every session; it points here.

## 1. Rules: read before working in the area (binding)

| File | Read before |
|---|---|
| `standards/backend.md` | Any endpoint, service, schema, error or background job |
| `standards/database.md` | Any table, migration, index or query |
| `standards/security.md` | Anything touching login, access, secrets, personal data, rate limits or dependencies |
| `standards/legal.md` | Anything touching the law: personal data and consent, what we say about people, ranking, payments, tax, content rights, messages, minors, and every Confirm question for the lawyer and CA |
| `standards/testing.md` | Any test, CI change, or claim that something is tested |
| `standards/frontend.md` | Any web or app work (after the backend is complete) |
| `standards/ux.md` | Any design, flow or copy, and backend choices that shape them |

## 2. The record: what was decided (append-only)

| File | What it holds |
|---|---|
| `DECISIONS.md` | Every founder decision, numbered. Never edited, only added to. |
| `decided/` | The proposals and papers behind decisions already built, kept as reasoning. Index in `decided/README.md`. |
| `reports/` | Daily engineering reports, as written that day. |

## 3. The plan: what is left (kept current)

| File | What it holds |
|---|---|
| `BACKEND_COMPLETE.md` | **The one list of what the backend still needs**, with each item's gate. When it is empty, the backend is complete. |
| `PLATFORM_AND_TECH_PLAN.md` | The locked technology baseline (section 4.0) and the platform plan. |
| `PRODUCT_BACKLOG.md` | The original product phases A to E, kept for `assign-task`'s progress view; open items are carried in `BACKEND_COMPLETE.md`. |
| `PLAYBOOK_GAPS.md` | The 1 October gap audit; its open items are carried in `BACKEND_COMPLETE.md`. |

## 4. Research: read when the topic comes up

| File | Topic |
|---|---|
| `BILLION_DOLLAR_GAP.md` | What the best platforms have that we do not, as proposed backend items (8 October) |
| `COMPETITIVE_LANDSCAPE.md` | Every competitor, in India and worldwide, and what we have that they do not |
| `GO_TO_MARKET.md` | Coimbatore first: how the pilot finds its first brands and creators |
| `PSYCHOLOGY_AND_TRUST.md` | What makes people trust a marketplace with their money and work |
| `REVENUE_RESEARCH.md` | How we could earn, never by touching deal money |
| `PERFORMANCE.md` | Measured response times against the budgets |
| `REVIEW_FINDINGS.md` | Every automated review finding, and what became of it |
| `API_CONTRACT_FINDINGS.md` | What fuzzing the API against its contract found |
| `FRONTEND_BLUEPRINT_MAPPING.md` | The original blueprint's screens, mapped to the API |
| `DEAL_RECORD_VERIFY.md` | How anyone can check a deal record's seals themselves (public-facing) |
| `DESIGN_DIRECTION.md` | Modern Tamil: the design brief (on branch `docs/design-direction`) |

## 5. Reference

| File | What it is |
|---|---|
| `api/openapi.json` | The API contract the frontend builds against; tests fail if the app differs |
| `INCIDENT_RESPONSE.md` | **What to do when something goes wrong**: who acts, rotating each secret, taking the API down, telling people |
| `../infra/README.md` | How the AWS setup is created and run |
| `../README.md` | How to run the project |
| `../SECURITY.md` | How a researcher reports a vulnerability, and what we promise them |

## Keeping this true

A new doc is added to this table in the same pull request that creates it, in the one section that fits. A proposal moves to `decided/` in the pull request that builds it. Research that stops being true is updated or deleted, never left to mislead.
