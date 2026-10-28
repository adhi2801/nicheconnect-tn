# Proposal: where the frontend lives, and which framework the apps use

**Status: Proposed.** Nothing here is approved or a decision, and no decision entry is written. Written 28 October 2026 for both founders. Erode Harish asked for the frontend to live in this repository (PR #78) and chose Flutter for the apps on 7 October. Adhi's locked baseline (D-047, `frontend.md`) says a repository of its own and Expo (React Native). Both founders have to agree on one answer, so this lays out the two decisions and what each costs.

**A correction first.** On 28 October the design side was told Flutter was the right choice for the apps. That was said before `frontend.md` and D-047 were read, and the recommendation below is different for that reason.

---

## 1. Where the frontend lives

```
DECISION NEEDED: The frontend's repository
Context:      CLAUDE.md sections 0 and 1 and frontend.md say a repository of its own,
              never this one (D-053). Harish asked for it here, under frontend/, so
              frontend and backend are easy to connect. PR #78 does it.
Option A:     In this repository, under frontend/.
              | + the contract file is read directly (the copy is already gone); one
                  pull request can change API and client; CI can fail when they differ
              | - this repository is PUBLIC, so the designs and prototypes are public;
                  Python CI and tooling now share a repository with Node and mobile builds;
                  it reverses D-053 and needs CLAUDE.md, frontend.md and ux.md edited
              | effort S (done on a branch)
Option B:     A separate repository, private.
              | + keeps the designs private until launch; matches the standards as written;
                  separate CI and release
              | - the contract is copied or fetched across repositories
              | effort S (the earlier private repository, harishnetflexglitched/colyv-frontend,
                  already exists with the same history)
Recommended:  A if the founders accept that the designs are public; otherwise B. The
              technical case for A is real, and the cost is the public repository.
Risk & rollback: A is undone by moving frontend/ out with its history (git subtree split).
→ Approve A, B, or modify?
```

## 2. The apps' framework

```
DECISION NEEDED: Expo (React Native) or Flutter for the Android and iPhone apps
Context:      D-047 locked Expo for both apps and Next.js for the website, one shared
              TypeScript core (frontend.md section 2). Harish chose Flutter on 7 October
              for smoothness and visual control; that was never recorded. The website is
              Next.js either way. frontend.md says a rule written twice is a bug waiting
              to disagree with itself.
Option A:     Expo and Next.js, one TypeScript core. (The locked baseline.)
              | + one language across website and apps: the API client, the form
                  validation generated from the contract, the rupee and date formatting
                  and the deal-stage logic are written once
              | + Expo UI renders real SwiftUI and Jetpack Compose controls, so iPhone
                  gets the platform's own look and Android its own (frontend.md section 8)
              | + the tokens file we already built feeds both
              | + an existing standard, test and release plan (Maestro, PowerSync)
              | - the signature look (springs, bento cards) is built with animation
                  libraries instead of an engine that owns every pixel
              | - the 3 Flutter screens already built become design reference, not code
              | effort: foundations start from zero in the app, but the website is shared
Option B:     Flutter for the apps, Next.js for the website.
              | + total control of every pixel and the same look on both platforms
              | + 3 screens and the token pipeline to Dart already exist
              | - a second language: the API client, validation, formatting and stage
                  logic are written twice and must be kept in step, so a Dart client
                  generator is a new dependency decision and shared test data becomes
                  mandatory
              | - reverses a locked baseline (the upgrade rule in D-047 asks for evidence
                  it helps us); no shared code with the website
              | effort: more total work, more places for the two founders' rules to drift
Recommended:  A, Expo, for a 1 January launch with two people: one language, one core,
              and an already-written standard. This is a recommendation, not a
              measurement. The smoothness of either on a budget Android phone is
              measured on the reference device in phase 5, not claimed now.
Risk & rollback: Choosing A first costs little: screens are planned stack-neutral and the
              tokens and plan carry over. Choosing B costs the shared core.
→ Approve A, B, or modify?
```

## 3. Edits to the shared documents, once both decisions are made

These are written here and **not applied**, because applying them would record Harish's choices as settled before Adhi has agreed (`CLAUDE.md` sections 5 and 10). They are ready to apply in one commit with the decision entry.

| File | Edit if A (here) | Edit if the framework is Flutter |
|---|---|---|
| `CLAUDE.md` sections 0 and 1 | Replace "frontend code still waits ... this repository still holds none" and "This repo contains no frontend code" with: the frontend lives under `frontend/`, work starts as scoped by the screen plan, and the backend's own gates are unchanged | none |
| `docs/standards/frontend.md` header and section 1 | Drop "in a repository of its own, never this one" | none |
| `docs/standards/frontend.md` section 2 | none | Replace Expo with Flutter; remove "one shared core in TypeScript" for the apps; add the Dart client generator and shared test data as decisions |
| `docs/standards/ux.md` timing note | Drop "No frontend code starts until the backend is complete" | none |
| `docs/PLATFORM_AND_TECH_PLAN.md` section 4.3 | none | Rewrite the Apps and Native look rows |

Draft decision entry, **not added to `docs/DECISIONS.md`**:

```
## D-1xx: Where the frontend lives, and the apps' framework
- Date: <date>
- Approved by: <pending: Adhi and Erode Harish>
- Context: Harish asked for the frontend in this repository and chose Flutter (7 Oct); D-047 and D-053 say Expo and a repository of its own.
- Options considered: see docs/PROPOSAL_FRONTEND_HOME_AND_STACK.md
- Chosen: <pending>
- Reason: <pending>
- Consequences / follow-ups: the edits in section 3, and the public-repository disclosure if A.
```
