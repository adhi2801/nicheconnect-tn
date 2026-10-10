# Frontend Blueprint → backend mapping

**Updated 10 October 2026, every status checked against the API contract (`docs/api/openapi.json`).** The 1 October version still marked deal memos, proof, payments, search, matching, notifications and the Passport as blocked; all of them are built. The mapping still assumes a creator Android app and a brand web dashboard; the direction since is three clients each serving both roles (D-046, proposed, awaiting Erode Harish), English only (D-054). For platforms read `docs/standards/frontend.md` and `docs/PLATFORM_AND_TECH_PLAN.md` section 2.

Every screen in the NicheConnect TN Frontend Blueprint (18 September 2026, 40 screens), and what the API answers for it. **What is left to build is listed once, in `docs/BACKEND_COMPLETE.md`;** this file only maps screens to it.

**Status words**
- **Built** — the endpoints exist, are tested, and are in the contract
- **Partial** — something exists, but the screen needs more (named)
- **To build** — no blocker, just work
- **Blocked** — waiting on a founder decision, the validation pack, or an outside review

---

## 1. The honest scope picture

Of the **32 screens tagged MVP** below, the API fully answers **25**, partly answers **5**, and **2** wait on something outside the code: the trust page (the validation pack) and the AI Copilot (a founder decision). The 32 include four screens this file adds for what was built since (what needs me, invitations twice, block and report). On 18 September it fully answered 5 of 24.

What the screens still lack is mostly outside the code: legal wording from the validation pack, platform numbers from Meta and Google review, and the frontend itself.

---

## 2. WhatsApp: a deliberately small role (D-022)

The blueprint's flow 2.3 runs the whole journey inside WhatsApp: apply, accept, upload proof, confirm payment. That is dropped, for two reasons:

1. **If everything happens in WhatsApp, the app has no reason to exist.** The Passport, earnings, fair-rate meter and history are what make a creator install and return.
2. **Every duplicated action doubles the work**: two code paths, two sets of rules, two sets of tests, and a permanent risk of the two disagreeing about what happened.

**What WhatsApp does instead**

| Keep | Why |
|---|---|
| Alerts with a deep link into the app: new opportunity, memo waiting, proof approved, payment marked paid, payment reminder | Tier 2/3 creators live in WhatsApp; this is how they find out anything happened |
| Login code delivery, if WhatsApp is chosen over SMS | Cheaper and more reliable than SMS in India |
| At most two one-tap replies: **accept memo** and **confirm payment received** | The two moments where opening an app is a real barrier, and both are a single yes |

**What WhatsApp does not do:** applying, pitches, proof upload, disputes, browsing, editing a profile.

**Backend effect:** the notifications module needs outbound templates plus one inbound webhook for those two replies, not a conversation engine. Roughly a quarter of the work in flow 2.3, and the app stays the single source of truth.

---

## 3. Marketing and auth

| Screen | Route | Priority | API | Status |
|---|---|---|---|---|
| Landing page | `/` | MVP | Static. Real city numbers for the hero: `GET /cities`, `GET /cities/{city}/figures` (public, five or nothing, D-078) | **Built** |
| Creator Passport (public) | `/c/:handle` | MVP | `GET /creators/by-handle/{handle}`: no login, **no contact details**, published by choice (D-036), rate card when published (D-055), fair-rate range (`GET /rate-guidance`, D-056) | **Built** |
| City/niche SEO page | `/creators/:city/:niche` | v1.2 | City figures are built (D-078). A public list of creators by city is not, deliberately: figures, not a directory | **Partial** |
| Pricing | `/pricing` | v1.1 | Nothing until billing exists | Blocked (pricing model) |
| Trust / ASCI / DPDP | `/trust` | MVP | Static content; the legal map is `docs/standards/legal.md`, the wording comes from the validation pack | Blocked (validation pack) |
| Login | `/login` | MVP | `POST /auth/otp/request`, `/otp/verify`, `/auth/refresh`, `/auth/logout`, `/auth/logout-all` | **Built** |
| Register (role select) | `/register` | MVP | Role chosen at verify; invite codes credited at sign-up (D-080) | **Built** |
| Brand onboarding | `/onboarding` | MVP | `POST /brands/me`, with a date of birth: adults only (D-086) | **Built** |
| Creator onboarding + KYC | `/onboarding` | MVP | `POST /creators/me`, adults only (D-086). **ID verification (KYC) does not exist**: it waits on the validation pack (plan D4); a verified business from GST is item 36 | **Partial**, KYC blocked |

---

## 4. Shared shell

| Screen | Priority | API | Status |
|---|---|---|---|
| Command palette (⌘K) | v1.1 | No search across creators, campaigns and memos at once | To build |
| Inbox | v1.1 | A notification history (D-022, D-023): `GET /notifications`, read, read-all, unread count. Messages delivered by WhatsApp wait on Meta verification (E1) | **Built** (in-app) |
| Notifications | MVP | Same, with preferences: quiet hours, digest, muting, urgent never held (`/me/notification-preferences`, D-079) | **Built** |
| What needs me | MVP | `GET /me/attention`: everything waiting on the person, most urgent first | **Built** |
| Settings + DPDP privacy | MVP | Export (`GET /me/export`), log out everywhere, notification preferences, blocks (`/me/blocks`), UPI ID with consent (`/creators/me/upi`, D-085), invite code. **Account deletion** waits on the validation pack (E8) | **Partial** |
| AI Copilot panel | MVP | Not built; the brief builder (item 40) and an MCP server for people's own assistants (item 41) come first | Blocked (decision) |

---

## 5. Brand web app

| Screen | Route | Priority | API | Status |
|---|---|---|---|---|
| Home / dashboard | `/dashboard` | MVP | `GET /me/attention`, `GET /payments/mine` and totals (D-075), `GET /campaigns/{id}/summary` (D-076) | **Built** |
| Discover creators | `/creators` | MVP | `GET /creators` (filters: city, niche, platform, followers, price, format, free on a date) and `GET /campaigns/{id}/matches` with the reasons for each (Phase D, D-083) | **Built** |
| Creator profile (brand view) | `/creators/:id` | MVP | The Passport, `GET /creators/{id}/media-kit`, `/delivery-record` (with how many brands it rests on), `/response-times` (D-077). **Contact details are never shown**, before or after a deal (D-036); the UPI ID only on the pay screen (D-085) | **Built** |
| Shortlists | `/shortlists` | v1.1 | Shortlisting inside a campaign is built; saved lists across campaigns are not | **Partial** |
| Campaign list | `/campaigns` | MVP | `GET /campaigns` | **Built** |
| New campaign wizard | `/campaigns/new` | MVP | `POST /campaigns`, publish. Per-creator quotas and festival templates (E5) are not built; the brief builder is item 40 | **Partial** |
| Campaign detail | `/campaigns/:id` | MVP | `GET /campaigns/{id}` and `/summary`: applications by status, deals by stage, Complete (D-076) | **Built** |
| Applications review | `/campaigns/:id/applications` | MVP | List, shortlist, accept, reject **with a reason**; each carries `text_flags` (item 60) | **Built** |
| Invite a creator; work together again | from search or a finished deal | MVP | `POST /campaigns/{id}/invitations`, `POST /deal-memos/{id}/repeat`, withdraw (D-084) | **Built** |
| Deal memo editor | `/deal-memos/:id/edit` | MVP | Create, edit, send (D-024 to D-027, D-039). One payment per deal (D-027); milestones are not built | **Built** |
| Deals (memos + payments) | `/deals` | MVP | `GET /deal-memos/mine`, each with its stage and whose move it is (D-076) | **Built** |
| Payment + reliability | `/deals/:id/payment` | v1.1 | Payment record, mark paid (single and bulk), the brand's reliability record (D-034); UPI pay details (D-085, switched off until the notice exists) | **Built** |
| Campaign results / ROI | `/campaigns/:id/results` | v1.2 | Results read from proof (D-070, switched off until the validation pack); platform numbers wait on Meta and Google (items 29 to 31); a campaign report is item 47 | Blocked |
| Company profile / billing | `/settings/company` | MVP | The brand profile is built. Team members with roles: the agency workspace (item 46, both founders). Billing: the pricing model | **Partial**, teams blocked |

---

## 6. Creator Android app

| Screen | Route | Priority | API | Status |
|---|---|---|---|---|
| Home / dashboard | `/home` | MVP | `GET /me/attention`; `GET /applications/me/feedback`, why applications are not turning into deals (D-041) | **Built** |
| Opportunities | `/opportunities` | MVP | `GET /campaigns/discover` and `/discover/for-me` with reasons (Phase D) | **Built** |
| Opportunity detail + apply | `/opportunities/:id` | MVP | `GET /campaigns/{id}`, apply; the fair-rate meter is `GET /rate-guidance` (D-056) | **Built** |
| Invitations | in My Work | MVP | `GET /applications/me?status=invited`; accept, or decline with a reason (D-084) | **Built** |
| Voice pitch recorder | component | v1.2 | Audio upload and transcription | Blocked (provider decision) |
| My Work | `/my-work` | MVP | `GET /applications/me`, `GET /deal-memos/mine` with stage and whose move | **Built** |
| Deal memo — accept | `/deal-memos/:id` | MVP | Read, accept, decline, request a change | **Built** |
| Proof upload | `/my-work/:id/proof` | MVP | Signed uploads straight to storage; files cleaned of location and hidden data and sealed (D-065 to D-067) | **Built** |
| Payment confirm / dispute | `/my-work/:id/payment` | v1.1 | Confirm received; a dispute with a shared timeline (D-028, D-035) | **Built** |
| Earnings | `/earnings` | MVP | `GET /payments/mine` and totals (D-075). Invoices and tax statements wait on the validation pack (E6) | **Partial** |
| Profile / Passport editor | `/profile` | MVP | Profile, channels, packages, rate card and Passport switches, availability (D-083), UPI ID (D-085). Platform-verified stats wait on items 29 to 31 | **Built** |
| Portfolio / past collabs | `/profile/portfolio` | v1.1 | The delivery record is built (D-038); portfolio items are not | **Partial** |
| City leaderboard | `/leaderboard` | v1.2 | Not built. Any ranking must be explained publicly (item 50, `docs/standards/legal.md` section 3.4) | To build |
| Creator collectives | `/collectives` | v2 | Group applications (E5) | To build |
| Festival calendar | `/festival-calendar` | v1.2 | Campaign templates by festival (E5) | To build |
| Block and report | from anything another person sent | MVP | `POST /me/blocks`, `POST /reports` (item 59, D-061) | **Built** |

---

## 7. The conflicts this file once raised, and how each ended

| Conflict (18 September) | Outcome |
|---|---|
| 7.1 Matching was MVP in the blueprint and Phase D in the backlog | **Resolved**: matching is built both ways, every match with its reasons (Phase D) |
| 7.2 Brand teams break one account, one profile | **Open**: the agency workspace (item 46) needs both founders |
| 7.3 Payment milestones | **Decided**: one payment per deal, due 7 days after approval (D-027); milestones are not built |
| 7.4 KYC gates applying | **Open**: ID verification waits on the validation pack; until it exists, applying needs only a profile |
| 7.5 Fair rate with no data | **Resolved**: five creators or nothing, with the sample size shown (D-056) |

---

## 8. What the backend builds next

Not here: **`docs/BACKEND_COMPLETE.md` is the one list**, with each item's gate, so this file and that one can never disagree again.
