# Frontend Blueprint → backend mapping

Every screen in the NicheConnect TN Frontend Blueprint (18 September 2026, 40 screens), and what this repository must provide for it.

Read with `docs/PRODUCT_BACKLOG.md` (build order) and `docs/PLAYBOOK_GAPS.md` (what neither document covers). Decisions live in `docs/DECISIONS.md`.

**Status words**
- **Built** — endpoints exist and are tested
- **Partial** — something exists, but the screen needs more
- **To build** — no blocker, just work
- **Blocked** — waiting on a founder decision or the validation pack

---

## 1. The honest scope picture

The blueprint tags **24 of 40 screens as MVP**. Of those 24, the backend today fully supports **5**, partly supports **4**, and has nothing for **15**.

That is not a criticism of the blueprint: it is the size of the first release, stated plainly. Three of those gaps (KYC, creator search with match scores, and the AI Copilot) are each a feature in their own right, not a screen.

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

| Screen | Route | Priority | Backend needed | Status |
|---|---|---|---|---|
| Landing page | `/` | MVP | Nothing (static). The hero's "find 3 food creators in Madurai" needs creator search | Blocked (see §5) |
| Creator Passport (public) | `/c/:handle` | MVP | Public read endpoint by handle, no login, **no contact details**; verified badge; fair-rate range | To build |
| City/niche SEO page | `/creators/:city/:niche` | v1.2 | Public creator list by city and niche, cached | To build |
| Pricing | `/pricing` | v1.1 | Nothing until billing exists | Blocked (pricing model) |
| Trust / ASCI / DPDP | `/trust` | MVP | Nothing (static content) | Blocked (validation pack) |
| Login | `/login` | MVP | `POST /auth/otp/request`, `/otp/verify` | **Built** |
| Register (role select) | `/register` | MVP | Same two endpoints; role chosen at verify | **Built** |
| Brand onboarding | `/onboarding` | MVP | `POST /brands/me` | **Built** |
| Creator onboarding + KYC | `/onboarding` | MVP | `POST /creators/me` exists. **KYC does not exist at all**: no verification state, no timer, no rejection reasons | Partial / Blocked |

---

## 4. Shared shell

| Screen | Priority | Backend needed | Status |
|---|---|---|---|
| Command palette (⌘K) | v1.1 | Search across creators, campaigns, memos | To build |
| Inbox (WhatsApp-synced) | v1.1 | Message threads per campaign; with D-022 this becomes a notification history, not a chat system | To build (reduced) |
| Notifications | MVP | Notification records, read state, deep-link targets, delivery through one interface | To build |
| Settings + DPDP privacy | MVP | `GET /auth/me` exists; export, deletion and consent log do not | Partial / Blocked (validation pack) |
| AI Copilot panel | MVP | Claude API integration, page context, action cards, confirm-before-acting, cost controls | Blocked (decision) |

---

## 5. Brand web app

| Screen | Route | Priority | Backend needed | Status |
|---|---|---|---|---|
| Home / dashboard | `/dashboard` | MVP | Counts and an activity feed across campaigns, applications and payments | To build |
| Discover creators | `/creators` | MVP | **Creator search for brands**: filter by city, niche, follower tier, fair rate, plus match scores | Blocked (matching, §7) |
| Creator profile (brand view) | `/creators/:id` | MVP | Creator read endpoint with stats and past collaborations; **contact details only after an accepted deal** | To build |
| Shortlists | `/shortlists` | v1.1 | `shortlist` and `shortlist_creator` tables | To build |
| Campaign list | `/campaigns` | MVP | `GET /campaigns` | **Built** |
| New campaign wizard | `/campaigns/new` | MVP | `POST /campaigns` exists. Missing: per-creator allocation and quota, festival templates | Partial |
| Campaign detail | `/campaigns/:id` | MVP | `GET /campaigns/{id}` exists. Missing: the 8-stage tracker, which is deal-memo state | Partial |
| Applications review | `/campaigns/:id/applications` | MVP | List, shortlist, accept, reject **with a reason** | **Built** (ranking by fit needs matching) |
| Deal memo editor | `/deal-memos/:id/edit` | MVP | `deal_memo` table, accept flow, ASCI check, milestone terms | Blocked (Phase B) |
| Deals (memos + payments) | `/deals` | MVP | Combined list with whose-turn-is-it | Blocked (Phase B) |
| Payment + reliability | `/deals/:id/payment` | v1.1 | Payment status, UPI reference matching, reliability score | Blocked (Phase B) |
| Campaign results / ROI | `/campaigns/:id/results` | v1.2 | Reach and engagement figures from the platforms | Blocked (integrations) |
| Company profile / billing | `/settings/company` | MVP | Company details exist as the brand profile. **Team members with roles do not** | Partial / Blocked (§7) |

---

## 6. Creator Android app

| Screen | Route | Priority | Backend needed | Status |
|---|---|---|---|---|
| Home / dashboard | `/home` | MVP | Action items across applications, memos and payments; match score | Partial / Blocked (matching) |
| Opportunities | `/opportunities` | MVP | `GET /campaigns/discover` with filters and paging | **Built** |
| Opportunity detail + apply | `/opportunities/:id` | MVP | `GET /campaigns/{id}`, `POST /campaigns/{id}/applications` | **Built** (fair-rate meter missing) |
| Voice pitch recorder | component | v1.2 | Audio upload, transcription, translation | Blocked (provider decision) |
| My Work | `/my-work` | MVP | `GET /applications/me` exists; memo and proof stages do not | Partial / Blocked (Phase B) |
| Deal memo — accept | `/deal-memos/:id` | MVP | Memo read and accept | Blocked (Phase B) |
| Proof upload | `/my-work/:id/proof` | MVP | Media storage, resumable uploads, proof records | Blocked (storage decision) |
| Payment confirm / dispute | `/my-work/:id/payment` | v1.1 | Payment status confirm, dispute records | Blocked (Phase B) |
| Earnings | `/earnings` | MVP | Payment history; commission links and invoices are separate features | Blocked (validation pack: GST, TDS) |
| Profile / Passport editor | `/profile` | MVP | `GET/PATCH /creators/me` exists. Missing: auto-pulled stats, rate card, portfolio | Partial |
| Portfolio / past collabs | `/profile/portfolio` | v1.1 | Portfolio items with proof links | To build |
| City leaderboard | `/leaderboard` | v1.2 | Ranking from completed deals and engagement | To build |
| Creator collectives | `/collectives` | v2 | Group applications: a real change to the application model | To build |
| Festival calendar | `/festival-calendar` | v1.2 | Campaign templates by festival and date | To build |

---

## 7. Conflicts with what is already built

### 7.1 Matching is MVP in the blueprint, Phase D in the backlog
Match scores, ranked applications and the Copilot all need matching. Either the first release ships without them, or matching moves ahead of the trust features. **Founder decision.**

### 7.2 Brand teams break the account model
"Team invite with roles (admin/editor/viewer)" means several accounts share one brand. The database currently enforces one account, one profile (D-011, D-014), and that rule is deliberate. Supporting teams means a `brand_member` table and ownership checks that ask "is this account a member of the brand that owns the object". **Schema decision.**

### 7.3 Payment milestones
The memo editor has advance and balance percentages; the Phase B recommendation was a single payment with an optional advance. Milestones mean more states, more reminders and more dispute surface. **Decide before the memo is built.**

### 7.4 KYC gates applying
Applying currently requires only a creator profile. The blueprint requires verification. Once KYC exists, `POST /campaigns/{id}/applications` must refuse an unverified creator, with a reason they can act on.

### 7.5 Fair rate with no data
A public Passport shows a fair-rate range, but nothing can be computed before real deals exist. It must say "not enough data yet" rather than invent a number (`docs/PLAYBOOK_GAPS.md` section 3).

---

## 8. What the backend should build next, given this blueprint

1. **Phase B** (deal memo → proof → payment handshake → reliability score). It unblocks 8 screens and is the product's whole point. *Blocked on five policy answers.*
2. **Notifications**, in the reduced D-022 form. Unblocks the Notifications screen and every "waiting on you" moment.
3. **Creator Passport**, public and read-only. Cheap, and the blueprint's best growth lever.
4. **KYC**, once a vendor and the DPDP answers exist.
5. **Creator search for brands**, with or without match scores depending on §7.1.
6. **The Copilot**, last: it depends on everything above having data worth asking about.
