# Team seats for brands (item 13): the approved design and the build plan

**Status: Approved by Adhi on 30 October 2026 (D-148); being built on branch `feature/team-seats`, in two pieces. Not reviewed by Erode Harish (D-051).** This file is the plan the build follows; it moves to `docs/decided/` in the pull request that finishes it.

## 1. Why

A real Tamil Nadu business is rarely one person: an owner, a marketing person, an accountant, often an agency. Today one phone number is the whole brand (`brand.account_id`, unique), so staff share the owner's login and the record cannot say who did what. It changes the account model, so it lands before the frontend builds screens around one-person brands (`BACKEND_COMPLETE.md` item 13).

## 2. What competitors do (read 30 October 2026)

- **Upwork** splits a client team by job: hiring managers send offers and make contracts; a finance admin sees financial reports and approves budgets; recruiters cannot hire ([Team permissions](https://support.upwork.com/hc/en-us/articles/115000394427-Team-Permissions), [Set team roles](https://support.upwork.com/hc/en-us/articles/17979883523091--Set-team-roles)). Agencies are their own accounts with members ([Agency settings and permissions](https://support.upwork.com/hc/en-us/articles/360009646553-Agency-Settings-and-Permissions)).
- **Influencer platforms** (Sprout Social Influencer Marketing, Brandwatch Influence, influData, Modash) use owner, admin and member, priced per seat, some with access per asset ([Sprout](https://help.influencer.sproutsocial.com/en/articles/5607584-users), [Brandwatch](https://influence-help.brandwatch.com/en/articles/12414754-adding-users-and-managing-permissions), [influData](https://infludata.com/faq/seats-multi-logins), [Modash](https://modash.io/blog/announcing-multi-user-access-for-modash)).
- **How ours goes further:** roles are tied to what binds the business on a deal (sending a memo, approving proof, marking a payment), and every sealed entry on the deal record names the exact person who acted (`deal_record_entry.actor_account_id`). **Corrected 30 October 2026:** this file first said the record already did; it did not. Brand-side entries named the brand's owner whoever acted. Piece 1 fixed it: the brand access check notes the acting account on the request's session, and the record seals that account. Creators see the acting person's first name.

## 3. The decisions (D-148)

| Question | Chosen |
|---|---|
| Roles | **Owner, Admin, Campaign manager, Finance** |
| Who may approve a creator's proof (it starts the payment clock) | **Campaign manager and up** |
| What a creator sees | **The acting person's first name** with the brand's ("Sent by Ravi at Thendral Sweets"), never a phone number |
| Agencies | **One person may belong to several brands**, choosing which one they act for |

## 4. The design

### 4.1 Who is in a brand
- **The owner stays `brand.account_id`.** One truth: ownership is never stored twice. Handing ownership over moves that column, under the brand's lock.
- **`brand_member`** holds everyone else: brand, account, role (`admin`, `campaigns`, `finance`), the first name creators see, who invited them, when they joined, and `removed_at` (kept, so who acted on old deals stays known). One live membership per brand and account (a partial unique index). At most 20 live members a brand, counted under the brand's lock.
- A member's account is a brand-role account (`account.role = 'brand'`) that need not own a brand of its own. An owner is never also a member of their own brand.

### 4.2 Joining
- **`brand_invite`**: brand, role, first name, who invited, `expires_at` (7 days), `accepted_at` and by whom, `revoked_at`. **Only a keyed hash of the invited phone number is kept** (HMAC under its own label, as assistants' tokens are), never the number: the person was never asked.
- **No message is sent to the invited number.** The inviter tells the person; when that number signs in as a brand, their open invites are listed for them to accept or decline. Someone who never agreed to hear from us hears nothing; and the invite cannot be used to send spam.
- One open invite per brand and number; 20 invites a day per brand (a daily ceiling, `trust-and-safety.md` rule 2).

### 4.3 Acting for a brand
- **The brand acted for travels in a header, `Brand-Id`**, the pattern of Stripe's `Stripe-Account` for connected accounts. Without it: the account's own brand, else its only membership, else 422 `brand_choice_needed`. A brand the account neither owns nor belongs to is **404**, never 403, so membership is never revealed (`security.md` section 2).
- **One place decides access** (to be built in piece 1): a `brand_access` module in `auth` resolves the brand and the role, and a `brand_acts` module beside it lists every brand write route under one act, as `agent_scopes.py` lists routes under scopes. **Denied by default**: a brand write route not listed is refused to members until a decision lists it; reads are open to every member of the brand.
- A suspended or departed owner's brand is closed to its members too.

### 4.4 Acts by role

| Act | What it covers | Owner | Admin | Campaigns | Finance |
|---|---|---|---|---|---|
| `campaigns` | Campaigns, invitations, applications, offers, saved lists, search | ✓ | ✓ | ✓ | |
| `deals` | Memos (write, send, cancel, repeat), notes, shipments, drafts, feedback | ✓ | ✓ | ✓ | |
| `proof` | Approve proof or ask for a fix | ✓ | ✓ | ✓ | |
| `payments` | Mark paid (one or many), disputes on the brand's side | ✓ | ✓ | | ✓ |
| `profile` | The brand's name, details and domain | ✓ | ✓ | | |
| `team` | Invite, change roles, remove | ✓ | ✓ (never an admin, never the owner) | | |
| `ownership` | Hand the brand over; delete the brand's account | ✓ | | | |

Everyone in a brand reads everything of that brand. Removing anyone, and making anyone an admin, needs the owner's or admin's step-up code (`security.md` section 1), bound to that exact change.

### 4.5 What does not change
- Money still goes from the brand to the creator directly; nobody on a team touches it (constraint 1).
- Deleting the account (item 6) is the owner's, and is still refused while any deal is unfinished or money is owed (D-122, D-147). A member deleting their own account leaves the brand; the brand goes on.
- Assistants' tokens (D-138) act for their own person, within that person's role.

### 4.6 STRIDE

| Threat | What stops it | Proved by |
|---|---|---|
| **Spoofing**: someone joins a brand by guessing | Joining needs the invite's own number to sign in; invites expire in 7 days and can be revoked | API and concurrency tests |
| **Tampering**: a member raises their own role | Only owner and admin change roles; an admin can never make or change an admin; a step-up code bound to the exact change | Every role against every team route |
| **Repudiation**: "I never sent that memo" | Every sealed entry names the account that acted, and creators see the first name | Record tests |
| **Information disclosure**: a member reads another brand | Every brand route resolves through membership; a brand you are not in is 404 | The stranger test, extended to members of other brands |
| **Denial of service**: invite floods | 20 invites a day per brand; 20 members a brand; no outside message | The daily-ceiling test |
| **Elevation of privilege**: a finance member approves proof, a campaign manager marks paid | Denied by default; every brand write route walked with every role | `test_brand_acts.py` |

### 4.7 Legal (`legal.md`)
- Section 3.1: the invited number is kept only as a keyed hash until the invite ends; a member's first name and memberships are in their export and erased with their account.
- Section 3.10, **Confirm**: that a team member's act (sending a memo, approving proof, marking paid) binds the business, given the owner chose their role. Added to the validation pack's questions. The design does not wait on it: the owner chooses who acts.

## 5. The build, in two pieces

**Piece 1:** the two tables and their migration; `brand_access` and `brand_acts`; every brand loader and every service lookup of a brand by its account moved onto them; the team API (invite, list, accept, decline, change role, remove, leave); the tests: model refusals, the refusing downgrade, every brand write route against every role, the stranger test for members, concurrency on the member cap and on accepting, the daily ceiling.

**Piece 2:** the first name on the record's reads and the creator's notifications; who on a team is notified of what; the data export and account deletion for members; handing ownership over; the agent-scope and attention views; the docs (`BACKEND_COMPLETE.md`, `security.md`, `trust-and-safety.md`, `legal.md`, the OpenAPI snapshot).

**Inventory of what moves** (30 October 2026, read from the running app): about 30 brand write routes resolve the brand through `get_current_brand_profile`, `get_owned_campaign`, `get_owned_application` and `get_brand_memo`; many more act on the signed-in account and look the brand up inside a service (feedback, notes, offers, disputes, payments, reports, memo reads, `visible_memo_for_account`, `get_visible_application`, `offer_service`, `deal_memo.service`, `campaigns.service`, `suspension`, `erasure`, `admin_service`). Each moves onto `brand_access`.

## 6. Rollback
The migration only adds two tables and widens three allowed-value lists; its downgrade refuses while any membership or invite exists, since each is a record of who could act for a business, and otherwise drops them. The code change is one branch, merged only when every gate is green.
