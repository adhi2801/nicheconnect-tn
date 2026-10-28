# Execution plan: keeping pace with the backend

**Status: Proposed.** Written 28 October 2026. **Launch: 1 January 2027.** The build deadline of **10 December** is not yet confirmed; this plan assumes it, and shows what moves if it does not. Nothing here is approved.

## 1. Where the backend is, in Adhi's own numbers

From `docs/BACKEND_COMPLETE.md` (counted on 27 October) and the API contract on `main` at `0b2ea3d`:

- **203 API operations**, up from 78 when the frontend first looked. 126 were added and 1 removed in about four weeks.
- **102 items listed: 56 built, 46 open.** Of the 44 open in his section 3, 22 wait on something outside the code or on Harish, and 22 need only an approval.
- **Built but switched off** until an outside answer arrives: passkeys (the domain), connected Instagram and YouTube (Meta App Review, Google verification), the UPI pay link (the validation pack's consent notice), search-engine indexing of Passports, delivered push and WhatsApp (Meta business verification).
- **He ships in small, numbered, tested pieces** (one decision entry each, several per week). The frontend cannot follow by reading chat; it follows the contract.

**Not under the frontend's control, and each can stop a 1 January launch** (from `BACKEND_COMPLETE.md` section 4): the AWS account and the founder steps in `infra/README.md` (going live); the MSG91 account (real login codes; today only a local script signs anyone in); the product name and domain (items 4 and 10); the validation pack (DPDP, ASCI, TDS and GST); Meta business verification. Ask Adhi for a date on each this week. Separately, Harish should check now what the Apple and Google developer accounts and their review times require, because that sets the real last day to submit.

## 2. How the frontend keeps pace

1. **The contract is the handshake.** Design and build only against what is in `docs/api/openapi.json` on `main`. The typed client is generated from it, so it cannot drift. It was regenerated today (203 operations) and the website builds.
2. **A weekly API watch.** On Monday run `pnpm api:changes` in `frontend/`. It prints the operations and fields added or removed since the last review (the commit is in `design/api-reviewed.txt`). Read it, update `screen-plan.md`, then run `pnpm api:changes --mark`. Tested today: it reports 78 to 203 operations, 126 added, 1 removed, 22 changed schemas.
3. **Every API feature is in one of three states**, and the frontend acts on the state:
   - **Built and on:** design and build now.
   - **Built but off:** design it, build it behind a switch, keep it hidden. It needs R6 (the backend telling clients what is on).
   - **Open:** design a stub from the plan, write no code, file the request.
4. **One request list, on Fridays.** Everything the frontend needs from Adhi goes to him in one file (`docs/PROPOSAL_FRONTEND_API_REQUESTS.md`) with the screen it blocks and the fallback. He decides the order. The frontend never waits for an answer: every request has a fallback (section 5).
5. **A response change is announced.** When one of Adhi's pull requests changes a response the frontend reads, the description says so. His pull requests already name their decisions, so this is one more line.
6. **Proposed, for Adhi (CI is his):** a check that regenerates the client and fails when the generated file differs from what is committed, so a merged contract change cannot sit unnoticed.

Working split: **Harish decides the design and approves each screen. Claude builds each screen in real code, in the same pass as the design, so no throwaway mock-ups exist.** Adhi owns the backend and every approval it needs.

## 3. Dated plan: website first, then the apps

Decided by Harish on 28 October: **launch the website and the apps, website first.** The website is Next.js whichever framework the apps use, so it can start now. **The apps' framework is decided by 15 November**, after Harish has felt Expo on his own phone (a test build of the creator Today screen, viewed through Expo Go with no Xcode or Android SDK). The website's logic goes in framework-neutral modules (formatting, phone and money rules, stage labels, the message catalogue, the typed client), so an Expo app can reuse it directly.

| Phase | Dates | What | API it uses (state) | Done when |
|---|---|---|---|---|
| **0 Start the website** | 28 to 31 Oct | Design system v1 in code (colour, type, eight components with all states, a component catalogue). Sign-in and code entry. Send the request list to Adhi. | auth (built) | **Done on 28 Oct**: sign-in works end to end against a mock of the login API; see section 8 |
| **1 Web foundations** | 1 to 10 Nov | Onboarding, Today and Inbox for both roles, the app shell and navigation. The refresh-token design (a security decision) approved first. | creators and brands `me`, `/me/attention`, notifications (built) | A person signs in on the real backend and sees Today |
| **2 Web creator core** | 11 to 20 Nov | Discover, campaign, apply with offers, applications, invitations, deals, the pass, memo, send work, payment, dispute, record. | campaigns, applications, offers, deal memos, proof, payments (built; R1 needs a fallback) | A creator follows a deal from apply to the record |
| **Framework decision** | **by 15 Nov** | Phone test of Expo, then both founders decide and Adhi is shown the finished decision. | none | One recorded answer |
| **3 Web brand core, and app foundations** | 21 Nov to 3 Dec | Four-step campaign, applicants, creator profile, invite, memo editor, review work, pay, record on the web. The chosen framework's app shell, sign-in and Today. | same set (R2 needs a fallback) | A brand completes a deal on the web; the app signs in and shows Today |
| **4 Apps and safety** | 4 to 10 Dec | The Must screens in the apps for both roles. Report, block, delete account, step-up, sessions, export, preferences. All five states everywhere. Accessibility pass. | trust, me, passport (built) | Build frozen; the six core journeys run on the website and the apps |
| **5 Test and fix** | 11 to 20 Dec | Usability tests with 5 creators and 5 brands. Fix list. Performance measured on a budget phone. Store submission. | none | Task completion at least 90%, no critical confusion point (`ux.md` section 2) |
| **6 Launch readiness** | 21 to 31 Dec | Store approvals. Real devices. Go or no-go on 28 December. | live backend and real login codes (outside) | Launch on 1 January |

**The risk of website first, plainly:** the apps get about 17 days (21 November to 10 December) for the Must screens of two roles. That works only if the shared logic is written once and the app screens are thin. If the framework decision slips past 15 November, the apps shrink first. The cut line is the Should and Later lists in `screen-plan.md`, never testing, the five states or accessibility.

**If 10 December is not confirmed:** phases 5 and 6 shrink first, which is the wrong end to squeeze.

## 4. What each person does this week

- **Harish:** answer the three decisions below; give Adhi the request list; confirm scope; start the 5 and 5 test recruiting (people to talk to, not a form).
- **Adhi:** approve or reorder R1 to R6; give dates for the outside launch dependencies; decide the admin console question.
- **Claude (after the decisions):** build the design system and the sign-in journey; keep `screen-plan.md` current with the Monday API watch.

## 5. Fallbacks, so nothing waits on a request

| Request | If it is not built in time |
|---|---|
| R1 brand name on campaigns and memo lists | Discover shows the verified domain and the payment record. There is no other source of a brand's name for a creator before they deal with it, so this is the **most urgent request, needed by about 10 November** |
| R2 creator summary on applicants | One media-kit call per applicant, in parallel, with the page limited to 20. This breaks the two-calls rule (`ux.md` section 7), so it is a stopgap |
| R3 draft-first | Ship with the live link only; the deal pass has the five stages without a draft step; add it after launch |
| R4 pilot waitlist | The website's Join form is hidden until it exists; launch is by app stores and invite codes |
| R5 proof per deliverable | One proof per memo, with a note listing what it covers |
| R6 which features are on | The client carries constants and flips them with each release (an extra store release per flip if the apps cannot update over the air) |

## 6. Decisions needed, in order

1. **The apps' framework** (by 15 November, decided by Harish first and shown to Adhi once decided). Adhi's locked baseline (D-047) is Expo (React Native) with a shared TypeScript core; Harish chose Flutter on 7 October and it was never recorded. The website does not wait for it. Detail and a recommendation: `docs/PROPOSAL_FRONTEND_HOME_AND_STACK.md`.
2. **Where the frontend lives** (PR #78). The standards say a repository of its own. Harish asked for this one. This repository is **public**, so the designs and prototypes would be public too.
3. **Scope.** Accept the Must list in `screen-plan.md` sections 5 and 6b for launch.
4. **The admin console.** Adhi's admin API exists and the law gives the report queue clocks (acknowledge in 24 hours, unlawful content in 36 hours). Does a founder work that queue through a screen, and is that screen part of launch? If so it is a Must and is not planned yet.
5. **Draft-first (R3)** for launch or after.
6. **Research timing.** `ux.md` asks for conversations before a flow is final and `docs/research/` holds none. Recommended: run the 5 and 5 on the prototypes in November, alongside the build.

## 7. Risks, plainly

- **The framework decision is on the critical path for the apps, not the website.** Each week it slips shortens the apps' build.
- **126 operations in four weeks is the pace to match.** Without the weekly watch the designs go stale; the plan I first wrote was stale on the day I wrote it.
- **The outside launch dependencies are not ours.** The frontend can be finished on 10 December and still not launch on 1 January.
- **Two apps and a website in 43 days is tight.** The first things to drop are the Should list and website polish. Never the five states, accessibility or the usability tests.

## 8. Built so far (28 October 2026)

In `frontend/apps/web`, on this branch. Checked in a real browser against a **mock** of the login API that follows `docs/api/openapi.json`; the real backend has not been run.

- **Design system v1:** colour, type (Plus Jakarta Sans, Inter, JetBrains Mono) and motion tokens in `tokens/tokens.json`; eight components (button, pill, card, text field, code field, choice group, notice, skeleton) in `src/components/ui`; a catalogue at `/design` (development only). Text colours were measured and darkened where the dashboard's values fell below the 7:1 rule in `frontend.md` section 6.
- **Sign-in (screens S1 and S2):** role choice, phone, six-box code, resend timer, and every failure the contract names (wrong code, rate limit with the wait, busy, suspended, role conflict, offline). The token is held in memory only.
- **Tests:** 3 unit tests on the phone rules, run with Node's built-in runner (no new dependency). Eight browser checks of the sign-in journey, run by hand through a script that is not yet in the repository.
- **Not yet:** a refresh token (a security decision for Adhi), the app shell and Today, a test runner and browser test tool in CI (dependencies to approve), and the idempotency key on writes that take one.
