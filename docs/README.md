# The docs, and when each is read

Every file here has one job. If two files start doing the same job, one of them goes. `CLAUDE.md` (at the root) is the only file read at the start of every session; it points here.

## 0. The bar every document meets (D-098, raised by D-139)

Adhi, 12 October 2026: every md file at the level of the best. A document meets the bar when:

1. **Its first lines** say what it is for, who reads it, and when it was last checked against the code.
2. **It is true today:** no stale number, claim or name.
3. **It is sourced:** every non-obvious rule or number cites the published practice or the measurement behind it, with a date.
4. **It weighs the twelve dimensions** (`CLAUDE.md` section 5) that apply to it, and says which do not.
9. **It is at the level of the best published practice, not above our measurements:** each standard names the strongest outside benchmark for its area (for example OWASP ASVS and MASVS, WCAG 2.2, ISO/IEC 25010, Google's SRE practice, AWS Well-Architected), says where we meet it, beat it or fall short, and raises a number only once a tool has shown it can be held (D-139).
5. **It names its own gaps:** what is weak, unmeasured, unreviewed or waiting.
6. **It is actionable:** it points to the items in `BACKEND_COMPLETE.md` and the decisions that act on it.
7. **Each fact lives in one place:** others link to it rather than copy it, so nothing drifts.
8. **It is plain and scannable,** and `tests/test_docs.py` passes: every decision number, path and link in it exists.

Dated reports, the decision log and the papers in `decided/` are records: they keep what was true when written, and get only a status line saying what became of them.

**Progress on the D-139 pass** (27 October): every md file raised again to twelve dimensions and point 9, one file at a time, each coming back to Adhi before it binds. Order: the standards (security, backend, database, testing, trust and safety, legal, frontend, ux), then the map, strategy and operations as below. None raised yet.

**Progress on the D-098 pass**, kept as the record. Raised on 12 October: `CLAUDE.md` and this index. On 14 October: `standards/backend.md`, `standards/database.md`, `standards/security.md`, `standards/testing.md`, `standards/trust-and-safety.md`, `standards/ux.md` and `standards/frontend.md`; and in the map, `BACKEND_COMPLETE.md` section 2, `ARCHITECTURE_SCALE.md` and `PERFORMANCE.md` brought up to date. Next, in this order:
1. The last standard: legal.
2. The map: `BACKEND_COMPLETE.md`, `ARCHITECTURE_SCALE.md`, `PLATFORM_AND_TECH_PLAN.md`, `PERFORMANCE.md`.
3. Strategy: the competitive landscape, the billion-dollar gap, trust, go to market, revenue, survival, the backlog.
4. Operations: the root README, `SECURITY.md`, the incident plan, the infra guide, the verify guide, the two findings files, the screen-to-API map, the commands.
5. A status line on each paper in `decided/`.

## 1. Rules: read before working in the area (binding)

| File | Read before |
|---|---|
| `standards/backend.md` | Any endpoint, service, schema, error or background job |
| `standards/database.md` | Any table, migration, index or query |
| `standards/security.md` | Anything touching login, access, secrets, personal data, rate limits or dependencies |
| `standards/trust-and-safety.md` | Anything that lets one person reach, pay, judge or be judged by another, and every way someone could scam another person or us |
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
| `FRONTEND_COMPLETE.md` | **The one list of what the website and both apps still need**: 341 items in seventeen areas (decisions, identity, design system, components, experience, journeys, screens, landing page, motion, 3D, accessibility, performance, engineering, being found, the apps, what puts us ahead, release), each with its proof and gate, counted from the tables (31 October 2026). |
| `PLATFORM_AND_TECH_PLAN.md` | The locked technology baseline (section 4.0) and the platform plan. |
| `PRODUCT_BACKLOG.md` | The original product phases A to E, kept for `assign-task`'s progress view; open items are carried in `BACKEND_COMPLETE.md`. |
| `PLAYBOOK_GAPS.md` | The 1 October gap audit; its open items are carried in `BACKEND_COMPLETE.md`. |

## 4. Research: read when the topic comes up

| File | Topic |
|---|---|
| `BILLION_DOLLAR_GAP.md` | What the best platforms have that we do not, as proposed backend items (8 October) |
| `COMPETITIVE_LANDSCAPE.md` | Every competitor, in India and worldwide, and what we have that they do not |
| `ARCHITECTURE_SCALE.md` | Scaling later: each proposal with the measured trigger that would justify it, cheapest step first |
| `research/` | The Mom Test template for interviews with real brands and creators. **No interview notes yet**: every novelty so far comes from desk research, not from users. `research/TAMIL_DESIGN_ROOTS.md`: the Tamil cultural and historical roots every visual choice must trace to, with sources (desk research, version 1). `research/FRONTEND_RESEARCH_2026.md`: the homepage prototype audited with Lighthouse and a WebGL frame counter, research across every frontend area with dated sources, the plan to raise it, and ten open decisions (28 October 2026). `research/LANDING_CULTURE_FIT.md`: each landing-page idea judged for meaning, belonging and product fit, the small Tamil details with a job, and how it is proven with real users (29 October 2026). `research/UI_STYLES_2026.md`: every current interface style (glass, Liquid Glass, bento, neumorphism, claymorphism, neo-brutalism, gradients) judged on evidence for Colyv, and the proposed direction, "granite and light" (29 October 2026; version 2 on 31 October adds Liquid Glass a year on and every other "morphism"). The frontend research set of 31 October 2026, each with dated sources and the decisions it asks for: `research/FEEL_AND_MOTION_2026.md` (what smooth is, physically, and the frame test that proves it), `research/COLOUR_PSYCHOLOGY_2026.md`, `research/INTERFACE_PSYCHOLOGY_2026.md`, `research/AESTHETICS_2026.md` (the benchmarks and a 25-point craft canon), `research/TYPOGRAPHY_2026.md` and `research/FUTURIST_FRONTEND_2026.md` (what to use now, as an enhancement, watch, or refuse) |
| `SURVIVAL_PLAYBOOK.md` | How startups like ours die and the rules that keep us alive: default alive, the numbers to watch weekly, money without selling the company, and founder pay growing step by step (10 October) |
| `GO_TO_MARKET.md` | Coimbatore first: how the pilot finds its first brands and creators |
| `PSYCHOLOGY_AND_TRUST.md` | What makes people trust a marketplace with their money and work |
| `REVENUE_RESEARCH.md` | How we could earn, never by touching deal money |
| `PERFORMANCE.md` | Measured response times against the budgets |
| `REVIEW_FINDINGS.md` | Every automated review finding, and what became of it |
| `API_CONTRACT_FINDINGS.md` | What fuzzing the API against its contract found |
| `PROPOSAL_FRONTEND_ARCHITECTURE.md` | **Proposed, 30 October 2026.** The whole frontend in one architecture: forty-one parts (identity, design system, motion, experience, engineering), the colour decision by a test with real users, signature scenes as pre-rendered frames, the landing page cut from 17 sections to 8, and the order of work. Read before any frontend build |
| `FRONTEND_BLUEPRINT_MAPPING.md` | The original blueprint's screens, mapped to the API |
| `DEAL_RECORD_VERIFY.md` | How anyone can check a deal record's seals themselves (public-facing) |
| `DESIGN_DIRECTION.md` | The first design brief ("Modern Tamil"), written before English only (D-054). Read through D-141's rule, a SaaS product first with a Tamil soul; the roots are `research/TAMIL_DESIGN_ROOTS.md` |

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
