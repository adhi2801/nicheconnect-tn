# Team seats for brands (item 13): the approved design and the build plan

**Status: Approved by Adhi on 30 October 2026 (D-148); built on branch `feature/team-seats` in two pieces, piece 1 on 31 October to 4 November and piece 2 on 4 November 2026. Not reviewed by Erode Harish (D-051).** Kept here as the reasoning behind the build; section 5 says what was built and where it differs from the plan.

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

**Piece 1 as built (31 October 2026, not yet reviewed or merged):**
- One check, in `auth/brand_dependencies.py`, so every module above `auth` reaches a brand the same way: `find_brand_access` by the `Brand-Id` header, and `acts_for_brand_of` for a route whose deal or application names the brand. Campaigns answer 409 with no brand at all, the brand's own profile 404, as before.
- Moved onto it: every brand loader, the saved lists, "more like my best", my payments, my memos, attention, every deal read and dispute (`party_memo` replaced `visible_memo_for_account`), applications and offers, a draft campaign's read, the brand profile and its domain. `get_brand_for_account` is gone. Search filters blocks by the brand's owner, as saved lists already did, so a member never finds a creator who blocked the brand; blocks of the brand's own are piece 2.
- **Corrected on the way:** the daily ceiling was per inviting person, not per brand as 4.2 says, so a brand with admins could send more than 20 a day. It is now counted per brand under the brand's lock (`team_invites_daily_limit`, 429), and the per-person limit stays.
- Left on the owner's account on purpose: the data export and erasure (piece 2 gives members their own), admin views of an account, and who is notified (piece 2).
- Proven: `tests/modules/auth/test_brand_acts.py` (every brand route found by walking the app; every write listed or the owner's alone; every listed route really checked; every role against every act; the stranger test's real world walked as each member role and as a member of another brand), `tests/modules/me/test_team_concurrency.py` (the cap, one invite accepted at once, the day's ceiling), and the team API tests. Nine rules broken on purpose, each caught.

**Piece 2 as built (4 November 2026, not reviewed by a second person):**
- **Who acts, noted once.** The brand check (`auth/brand_dependencies.py`) notes who acts on the request's session (`auth.brand_access.Acting`: the account, the brand, a member's first name) **only on a write**, and every request starts with none (`auth.dependencies._authenticate`), so a read names nobody and a session that outlives a request cannot carry one person's name onto another's act. The record seals that account, as piece 1 did.
- **What creators see.** A creator's notice of a member's act shows `details.acting_first_name`, for the notices that are one person's act (`auth.brand_acts.NAMED_TO_CREATORS`, denied by default): never for the owner, whose brand's name stands for them, and never for the deal's own rules, even when the clock's approval is noticed inside a member's request. The notice keeps the membership's id, never the name, and the name is read when the notice is, so erasing a member erases it from every notice too. The record's reads add `actor_first_name` to each brand-side entry: read when the record is, not sealed, so the seal is unchanged; a member who left keeps theirs; the owner has none.
- **Who on a team hears what.** A notice to a brand's owner about the work is copied, in the same transaction, to every live member whose role holds that work's act (`auth.brand_acts.NOTICE_ACTS`: applications, invitations and offers to `campaigns`; memo answers, cancellations, notes, goods received and feedback to `deals`; work and drafts sent to `proof`; a confirmed payment to `payments`; a withheld or restored profile to `profile`), never to whoever on the team did it, nor to a member whose account is suspended or gone, with `for_brand_id` and `for_brand_name` so someone in several brands knows which. Anything not listed (a session, a passkey, a deletion, the team itself) stays the owner's alone. Two queries more at most, and only when a member acts or the notice is one a team hears.
- **A brand's blocks are the brand's.** Blocking and unblocking go through the brand check (the `campaigns` act: owner, admin, campaign manager) and are stored as the owner's, the account every block check of a brand reads, so a member's block stops the whole brand, and the whole team reads the brand's list. Finance reads it and cannot change it. The owner is read under a share of the brand's row lock, so a block placed as the brand is handed over waits and lands on the new owner. Blocks a brand account placed while in no brand stay its own and do nothing while it acts for someone else's; they become its brand's if it later owns one.
- **Handing the brand over.** `POST /api/v1/brands/me/team/ownership`, under the `ownership` act, so the owner's alone: **from a login at least a week old unless the owner has a passkey** (D-109), so a SIM swapper's or a stolen session's fresh login cannot turn a short takeover into the brand's for good; a step-up code for `change_team` bound to `ownership:<member_id>`; the member must be live, own no brand (`owns_a_brand`, answered by the unique index on `brand.account_id`, the one check, so a brand taken at that moment is caught too) and have an account that stands (`cannot_take_brand` when suspended or being deleted, without saying which, read under a lock a deletion request or a suspension waits on). After the code, under the brand's lock (the phone's lock, then the brand's, as erasure takes them; removing and changing roles now spend their codes first too, so the owner's two changes at once never wait in a circle): the member's membership ends, `brand.account_id` moves, the former owner joins as an admin under the first name they give, every block placed by or against the brand moves to the new owner's account in place, keeping its id and when it was placed, and the brand's takedowns move to the new owner, who then sees them and is told when one is lifted (the admin log keeps who was told before). Both are told by `team_role_changed`, which nobody can mute: the new owner with the role `owner`, the former with `admin`, so the owner's other sessions see it. No new notice type and no migration. 5 a minute and 10 a day.
- **Changed from the plan, and why:** (1) a missing code answers 401 `step_up_required`, as every other step-up does; the test written before the code said 400 or 403. (2) A suspended or departing member cannot take the brand: either would close it to everyone, the former owner included. (3) Blocks move on a hand-over: without it every creator who blocked the brand would see it again. (4) An old enough login, a lock on the taker's account, and the brand's takedowns moving: all from the independent review (below). (5) **Left on the former owner's account on purpose**: their own notices, sessions, passkeys and assistants' tokens, which are the person's.
- **Already done in piece 1:** the data export and erasure for members (`brand_member` in the export; erasure ends a member's memberships).
- **The independent review** (a separate reviewer told to find faults, 4 November 2026) found 13 faults; each is fixed, with a test that fails without the fix, or answered here: (1, High) a hand-over could make a short account takeover permanent: an old enough login, and the former owner told; (2) the taker's deletion or suspension at that moment: read under a lock; (3) a block placed at that moment lost: the brand's owner read under a lock; (4) the clock's approval named a member: only a person's act names them; (5) the name kept in creators' notices outlived erasure: the membership is kept and the name read; (6) tests that could not fail: replaced, and concurrency tests added for two hand-overs of one brand, two brands to one person, a deletion at that moment and a block at that moment; (7) the owner's removal and hand-over at once could deadlock: every code is spent before the brand's lock (proven by reading, not by a test); (8) moved blocks changed their ids: moved in place; (9) takedowns stayed with the former owner: moved; (10) the notice's new keys were undocumented: in the contract; (11) any refusal on that flush read as `owns_a_brand`: only the unique index on `brand.account_id` does; (12) a member's own earlier blocks: answered above; (13) copies to suspended members: stopped. **Not built, a decision first:** telling a brand's creators with unfinished deals that it changed hands needs a new notice type, so a migration (Adhi chose it as the next build, D-150); and a waiting period before a hand-over takes effect, with the owner able to cancel it, as a new UPI ID waits 24 hours.
- **Proven:** `tests/modules/me/test_team_piece2_api.py`, `test_team_concurrency.py` (the four races above), the team blocks in `tests/modules/safety/test_block_api.py`, `test_brand_acts.py` with the new routes (the blocks found through `find_brand_access_of_any`, the hand-over under `ownership`); 25 rules broken on purpose, each caught (one first survived, and gained the test that catches it); the list of changes from the review is D-150.

**Inventory of what moves** (30 October 2026, read from the running app): about 30 brand write routes resolve the brand through `get_current_brand_profile`, `get_owned_campaign`, `get_owned_application` and `get_brand_memo`; many more act on the signed-in account and look the brand up inside a service (feedback, notes, offers, disputes, payments, reports, memo reads, `visible_memo_for_account`, `get_visible_application`, `offer_service`, `deal_memo.service`, `campaigns.service`, `suspension`, `erasure`, `admin_service`). Each moves onto `brand_access`.

## 6. Rollback
The migration only adds two tables and widens three allowed-value lists; its downgrade refuses while any membership or invite exists, since each is a record of who could act for a business, and otherwise drops them. The code change is one branch, merged only when every gate is green.
