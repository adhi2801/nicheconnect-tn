# Trust and Safety Standard

**For:** anyone building a feature that lets one person **reach, pay, judge or be judged by** another, or that someone could use to cheat us; read in full before the first file (`CLAUDE.md` section 6). **Last checked against the code: 14 October 2026**, on branch `docs/standards-bar`. Every row below was re-checked then. Three claims that had stopped being true were corrected; they are listed in section 7.

**The bar** is `CLAUDE.md` section 7.0: **nobody on this platform should be able to scam anyone else, or us, through anything we built**, and where a scam happens outside the platform, what they did here must help them see it coming. `security.md` keeps attackers out of the system. This file is about people **inside** it, with real accounts, using the product as built to harm someone. Both apply.

**Status words:** **Built** (in the code, with the test named), **Owed** (an item in `docs/BACKEND_COMPLETE.md`), **Frontend** (the backend is ready; the screen must do its part, `ux.md`).

**The ten dimensions** (`CLAUDE.md` section 5), and where this standard serves each:

| Dimension | Here |
|---|---|
| Trust and safety | All of it |
| Quality | Every Built row names its test; a route that reaches someone is checked for its daily ceiling and its block |
| Security | Links checked against phishing shapes (section 4); the attacker outside is `security.md` |
| Privacy and law | Flags are worked out, never stored; flagging shared networks waits on a legal decision (3.3); reports and the IT Rules' clocks, `legal.md` section 3.3 |
| Novelty | Upwork and Fiverr hide contact details before a contract; Meta publishes its fraud rules. Ours flags fee requests aimed at creators, the scam they do not name, and counts distinct counterparties so a pumped record reads as one partner (sections 3, 4) |
| Design | What the screens must say and show, section 5 |
| Business | A marketplace where creators are not scammed is the one they recommend; every scam that works here costs both sides and us |
| Research | Section 8 |
| Architecture, performance | Not here: flags are a pure function on read (`app/core/text_flags.py`); blocks are a condition in each query (`security.md` section 2) |

---

## 1. Rules for everyone building (binding)

1. **Map who can reach whom.** Every proposal lists each way the feature lets one account reach another: a notification, text they read, a link they open, a record about them. Each one gets a row in section 3, with its protection and its test. *(review only)*
2. **Every way of reaching someone has a daily ceiling per account**, not only a per-minute rate limit. A per-minute limit stops a script, not a person spamming by hand for an hour. **Enforced by** `tests/modules/test_daily_ceilings.py`, which lists every such route and fails if one loses its ceiling; a new route that reaches someone is added to it in the same change.
3. **Free text another person reads is untrusted.** It is stored and returned as plain text, never rendered as HTML, and the frontend never turns it into links. A link we accept as a field (proof, evidence) is checked against a list of hosts we know (section 4).
4. **Money talk stays on the record.** Nothing in the product ever asks anyone to pay anyone except the brand paying the creator the agreed fee, through their own bank. **A creator never pays to get a deal**: any brief, note or memo text asking a creator for money is flagged (section 4).
5. **Proof of payment is the receiver's own bank, never a screenshot.** Only the creator can confirm money arrived (D-027), and every screen that asks them says to check their own bank app.
6. **Records about people resist being gamed.** A figure that makes someone look good or bad counts things that are hard to fake, says how many it rests on (D-038), and never counts the same pair of accounts as independent evidence (section 3.3).
7. **Everyone can say no and be left alone**: decline, withdraw, mute (D-079), report (D-061), and block (item 59). A new way of reaching someone respects blocks in the same change, with a test in `tests/modules/safety/test_block_api.py`.
8. **We never ask for a login code, a UPI PIN or a password**, in any message, ever. The login message must say so; its wording waits on the MSG91 template (item 62).
9. **A report is answered, in time.** Each report is acknowledged when it is filed, with the time it will be answered by: the IT Rules' clock for its category, 2 hours for impersonation and intimate content, 36 hours for content the rules prohibit, 7 days otherwise (item 51, D-103). The admin queue is nearest deadline first, and every admin is warned 30 minutes before a deadline and when one passes. The reporter sees each report, its deadline and its outcome (`GET /api/v1/reports/mine`) and is notified when one is resolved, never with the admin's note (item 102, D-100).

---

## 2. The scams that actually happen

Researched 10 October 2026, sources in section 8.

| Scam | Who is hurt | How it works |
|---|---|---|
| **Pay-to-collab** | Creators | A fake brand offers a deal, then asks for a "registration", "verification", "shipping" or "security deposit" fee, and vanishes. Fake accounts impersonating Nykaa asked ₹2,000–5,000; Mamaearth look-alikes asked ₹500–1,500 "shipping" |
| **Brand impersonation** | Creators, and the real brand | Stolen logos and look-alike names make a fake brand look real |
| **Off-platform move** | Both | "Let's talk on WhatsApp", where nothing is on the record and the scam happens. Upwork and Fiverr both ban it before a contract for this reason |
| **Fake "payment done"** | Creators | An edited screenshot, a fake UPI app, or a made-up 12-digit reference. Only a credit in the receiver's own bank or UPI app is proof |
| **Collect-request and QR tricks** | Creators | "Scan this to receive your payment" or "enter your PIN to receive": both actually pay the scammer. You never enter a PIN to receive money |
| **Phishing links** | Both | A link presented as a campaign brief, a proof post or evidence leads to a fake login page |
| **Fake support** | Both | Someone posing as the platform asks for the login code "to verify" the account |
| **Bought audiences** | Brands | Around 58% of Indian Instagram profiles audited had over 60% spurious followers (Business Standard, 2024); engagement pods, ghost accounts, inflated screenshots |
| **Fake proof** | Brands | A link to someone else's post, an old post, or an edited insights screenshot |
| **Take the product and vanish** | Brands | Barter goods received, no content |
| **Pumped records** | Brands, creators, us | Two accounts controlled by one person run fake deals to build a perfect record |
| **Harassment by volume** | Both | Endless invitations, applications, reports or disputes against one person |

---

## 3. Every way one person reaches another, and what protects them

### 3.1 Brand → creator

| Way | Protection | Status |
|---|---|---|
| A campaign brief (title, description, deliverables) | Plain text; open campaigns from a suspended brand disappear (D-061); report a campaign (D-061) | Built |
| An invitation, with a note | 25 waiting per campaign (D-084), and 100 a day per brand across all campaigns, repeats likewise; creator declines in one tap; plain text | Built: `tests/modules/campaigns/test_invitation_api.py`, its concurrency test, and the daily-ceiling test |
| A rejection reason and note | Reason is a code; note ≤ 500 characters, plain text | Built: the database refuses a longer note (`tests/modules/test_database_refusals.py`) |
| A deal memo, its extra terms | Accepted terms never change, and the deal record proves it (D-057); the creator can ask for changes or decline | Built: `tests/modules/deal_memo/` |
| A revision request on proof | One change restarts the clock (D-025); note plain text | Built |
| Marking a payment sent | Only the creator can confirm it arrived (D-027); the reference shape is checked; a dispute holds the record short of unpaid | Built: the payment tests, with properties over every state |
| **Payment requests disguised in text** ("pay ₹2,000 registration") | `text_flags` on a campaign's description and deliverables, invitation and rejection notes, memo deliverables and extra terms, and revision notes: a request for a fee or deposit is flagged, while ordinary pay ("we pay ₹5,000 per reel") is not (`app/core/text_flags.py`). A campaign's **title** is not checked (gap 2) | Built: `tests/core/test_text_flags.py`, its property tests, and `tests/modules/test_text_flags_api.py` |
| **A brand name copying a famous brand** | **A verified domain** (item 74, D-106): a brand proves it controls its website's DNS with a TXT record, checked by two resolvers and again daily, and creators see the domain itself, since when, and when the registry says it was registered, on every campaign and the brand's payment record. A real brand stands apart from an impersonator with only a name. **It is a fact about a domain, never a verdict on the brand**: a look-alike domain (`nykaa-collabs.in`) can be verified too, which is why the domain and its age are shown, not a badge. **Look-alike names** (item 75, D-118): a name that reads as a protected brand's (Unicode's confusable test, filler words such as "official" and "collabs" dropped, one slip allowed) or mixes Latin with Cyrillic or Greek letters is flagged beside the name on every campaign and the payment record, and cannot publish a campaign until it verifies that brand's domain, or an admin clears that exact name after looking at the business (D-119, in the admin log with a note; a rename is held again); a look-alike domain does not count. Business identity from GST (item 36) is still owed | Built: `tests/modules/profiles/test_brand_domain_api.py`, `test_brand_domains.py`, `test_brand_domain_concurrency.py`, `test_brand_names.py`, `test_brand_names_properties.py`, `tests/modules/campaigns/test_brand_name_flag_api.py`, `tests/core/test_confusables.py`; **Owed** (item 36) |
| Contact details in text, pulling the creator off the record | Phone numbers, emails, UPI IDs and WhatsApp or Telegram links flagged in briefs, pitches and notes until the deal is agreed (D-086: flagged, not hidden) | Built: the same text-flag tests |
| Repeated contact after a no | **Block** (`POST /me/blocks`): once either side blocks, no invitation, repeat or application starts in either direction, and neither appears in the other's search, matches or discovery. Agreed deals carry on; the blocked side is never told, and every refusal reads as not found | Built: `tests/modules/safety/test_block_api.py` |
| A campaign alert, when a published campaign fits a creator's saved terms (item 43, D-130) | Only creators who asked, by an alert of their own; at most 20 a Tamil Nadu day per creator, so a brand publishing over and over cannot flood anyone, and creating campaigns has its own daily ceiling. Never across a block either way, never from a suspended, deleted or withheld brand or of a campaign withheld or closed before its turn, never to a suspended, deleted or withheld creator, and never to the brand's own other side (D-126). Mutable; quiet hours (D-079) apply to its delivery, which waits on push (E1). The notice carries only the campaign's id, so the brief is read with its text flags | Built: `tests/modules/campaigns/test_campaign_alert_sending.py`, `test_campaign_alert_concurrency.py`, the block test |

### 3.2 Creator → brand

| Way | Protection | Status |
|---|---|---|
| An application, with a pitch and quote | One per campaign (unique); 20–1,000 characters; plain text; 30 a day per creator | Built: the database refuses a second application and a pitch out of range (`tests/modules/test_database_refusals.py`); the daily-ceiling test |
| A counter-offer on a quote, with a note (item 44, D-123) | Either side of a waiting application, at most 3 each and one open at a time, 100 a day per account; never on barter; across a block it reads as not found; the note is plain text, at most 500 characters, flagged for fee requests when the brand writes it and for contact details either way; the application cannot be accepted while one waits, so the agreed price is never in doubt, and a different memo fee is shown beside the agreed figure | Built: `tests/modules/campaigns/test_offer_api.py`, `test_offer_properties.py`, `test_offer_concurrency.py`, the daily-ceiling and block tests |
| Proof: a link and screenshots | Screenshots are cleaned of hidden data and sealed (D-065, D-066); readings check the handle and the date (D-070). The link must be on a known content platform, and look-alike hosts, names before an @, ports and punycode are refused (`app/core/links.py`) | Built: `tests/core/test_links.py`, the proof-file and proof-reading tests |
| A change request on a memo | One message ≤ 1,000 characters, only with a request | Built |
| A channel link on the rate card | Only the platform's own hosts (`app/modules/profiles/rate_card_service.py`) | Built: the rate card tests |
| **Bought audiences** | Results read from proof (D-070); connected accounts with platform numbers (items 29–31): built, switched off until Meta and Google approve the apps (D-134); brands see the platform's count beside the stated one, never instead, since bought followers inflate both, and the public Passport shows no count at all (D-135) | Partly built; **Owed** (30, 31) |
| **A channel that is not theirs** | Proof readings check the handle on the screenshot matches the channel. A connected account (item 29, D-134) proves the creator can sign in to it, and one platform account belongs to one creator (`uq_connected_account_platform_user`), so two people cannot claim one channel; a sign-in works once, for the account that began it, so nobody can bind their channel to someone else. Built, switched off until the apps are approved | Built (off): `tests/modules/profiles/test_connections_api.py`, `test_connection_model.py`, `test_connection_concurrency.py` |
| Take the goods and vanish | The delivery record counts it (D-038); cancellation kinds (D-026). The goods themselves are on the record (item 68, D-131): the brand records the courier and tracking number, only the creator says they arrived, both sealed, so "I never got it" is answered by the creator's own dated word. A correction before arrival is sealed too; after it nothing changes. 100 a day per account; the number is shown as text, never fetched or linked | Built: `tests/modules/deal_memo/test_delivery_record.py`, `test_barter_shipment_api.py`, `test_barter_shipment_model.py`, `test_barter_shipment_concurrency.py`, the daily-ceiling test |
| Repeated contact after a no | Block, both ways (above) | Built |

### 3.3 Anyone → the records (and so → everyone who reads them)

| Way | Protection | Status |
|---|---|---|
| A dispute, with entries and evidence links | Both sides on the record; we never judge (D-028, D-035). Evidence links only to known platforms and file hosts (`app/core/links.py`); uploaded evidence is the better end. Dispute events are fingerprinted in the deal record and sealed like it: nothing can change or remove one (item 99) | Built: `tests/modules/disputes/`, `tests/modules/test_database_refusals.py` |
| A deal note, either way (item 17, D-128) | Only the deal's two parties, from the memo being sent until the deal ends; plain text up to 1,000 characters; a brand's note flagged for fee requests; 200 a day per account. Each note is sealed onto the deal record by its fingerprint and the table refuses any change, so neither side can rewrite what they said, and `notes_unchanged` shows a rewrite made behind the database's back | Built: `tests/modules/deal_memo/test_deal_notes_api.py`, `test_deal_notes_model.py`, `test_deal_notes_concurrency.py`, the daily-ceiling test |
| A report | One open report per reporter per subject (D-061); 10 an hour and 30 a day per account; a person cannot report their own thing; the reporter is told the outcome, the reported side is not (item 102). A 2-hour category could be filed falsely to jump the queue: the deadline only changes how fast an admin looks, never what is decided, and the reported side is told nothing (item 51) | Built: `tests/modules/admin/test_reports_api.py`, `test_report_clocks_api.py`, `test_report_clock_warnings.py` |
| **Pumped records: deals between accounts one person controls** | Records show how many **different** counterparties they rest on: `distinct_brands` on a creator's delivery record, `distinct_creators` on a brand's payment record, so a perfect record built with one partner reads as exactly that. Flagging pairs of accounts that share a device or network at sign-up would need storing sign-up addresses, which is personal data: a founder and lawyer decision first (`legal.md` section 3.1) | Counts built: `test_delivery_record.py`, `tests/modules/payment_status/test_reliability.py`; network flag **Owed** (item 61, a decision) |
| Reviews or ratings bought or invented | None exist except records from real deals (`legal.md` section 3.6) | Built |
| Feedback after a deal, used to retaliate or to pump a record (item 77, D-136) | Only the two sides of a finished deal answer, once, within 14 days; neither sees the other's answer, nor does anyone else, until both answered or the window closed, so nobody answers in return for what was said. Answers are sealed: nothing can be edited or removed, so nothing is quietly buried. Figures count only revealed answers, are null below three, and say how many partners they rest on, so a record pumped with one partner reads as one. A brand's note is flagged for fee requests; 50 answers a day per account | Built: `tests/modules/deal_memo/test_deal_feedback_api.py`, `test_deal_feedback_model.py`, `test_deal_feedback_concurrency.py`, `test_feedback_rules.py` |
| **A report used to take a rival offline** | Nothing is hidden by a report alone (item 52, D-104, option A): only an admin withholds an item, on a legal order or after looking at a report. The owner is always told (`content_withheld`, never mutable), keeps their account and sees the item, and their agreed deals carry on; a lift tells them again. The night-time cost: a 2-hour report at 3 a.m. waits for an admin to wake (D-103) | Built: `tests/modules/admin/test_takedowns_api.py`, `tests/modules/safety/test_takedown_visibility_api.py` |

### 3.4 Anyone → us

| Way | Protection | Status |
|---|---|---|
| Many accounts from one person | One account per role per phone number (`uq_account_phone_role`, D-126): a brand and a creator account of one person may share a number, and those two never deal with each other (applying, inviting and repeating read as not found); login-code limits per phone and network (`security.md` sections 1 and 5) | Built |
| Scraping creators | Search and matching are signed-in brands only, 30 a minute and 600 a day per account; no contact details anywhere. A saved list (item 66, D-129) and "like my best" (item 65, D-133) are read under the same ceiling, so neither is a way round it | Built: the matching, search and creator-list tests, the daily-ceiling test |
| A saved list as a way round a block, a takedown or a suspension (item 66, D-129) | A list is its brand's alone and the creator is never told. It shows, counts and accepts a creator only while the brand could find them in search (`search_service.visible`): unpublished, suspended, deleted, withheld or blocked either way, they drop out of view, and saving one is refused as not found. At most 50 lists of 200, each cap counted under a lock | Built: `tests/modules/matching/test_creator_lists_api.py`, `test_creator_lists_model.py`, `test_creator_lists_concurrency.py`, the stranger-routes test |
| Running up our AI bill | Daily ceiling on proof reading (D-070) | Built |
| Using our domain checks to query someone's DNS over and over | 5 checks a minute and 10 a day per brand; a check asks two fixed resolvers about one name, never a URL anyone gives us (item 74) | Built: `test_checks_are_limited_per_brand` |
| Abusing invite attribution | It carries no reward. **Any reward is designed with its abuse limits first** | Built (no reward) |
| An admin misusing access | Every view and action in the append-only admin log (D-061), sealed by the database, and the app's own login may only read and add to it (item 97). A takedown (item 52) is in the log with the admin's note, names who withheld and who lifted it, cannot be backdated (the server sets `withheld_at`), and cannot be deleted by the app's login. A rogue admin can still withhold an item; the log shows it afterwards. **Someone else in an admin's account** needs both the admin's phone and their authenticator (item 101, D-105), and every admin is told of every admin sign-in and every refused second factor, so between two founders each sees the other's logins | Built: `tests/modules/admin/test_admin_models.py`, `tests/modules/test_app_role.py`, `tests/modules/safety/test_takedown_model.py`, `tests/modules/admin/test_admin_login_api.py` |
| Impersonating us ("support") | We never ask for codes, PINs or passwords (rule 8). **The login message's wording must say so: Confirm the MSG91 template**. It matters more since item 82: a code now also guards where a creator is paid | **Owed** (item 62) |
| **Someone inside a creator's account, changing where they are paid** | A code sent to the phone for each risky change, good only for that exact UPI ID (item 82, D-107), so a stolen session cannot do it. A SIM swap gets the code too, so a new UPI ID waits 24 hours, brands keep seeing the one before, and the creator is told (a notification nobody can mute, first on their attention list) and can cancel it without a code. The export and logging out everywhere need a code too, so a stolen session can neither take the file nor throw the owner out Replacing an ID already in effect also needs a login at least a week old (D-109), which a SIM swapper never has | Built: `tests/modules/payment_status/test_upi_hold_api.py`, `tests/modules/me/test_step_up_api.py`, `test_upi_step_up_concurrency.py`, `tests/modules/me/test_established_login_api.py`. **Not stopped**: a SIM swap left unnoticed for over a week, or one joined by malware holding the creator's own old login, with the creator not opening the app in the wait (E1) |
| **Someone signed in to an account, unseen** | Every session is listed with what its app said it is and when and how it signed in, and the owner ends one at once; ending another needs a code bound to that session, so an intruder with a stolen session cannot throw the owner out (item 81, D-114). A sign-in from another device leads the owner's attention list for 7 days, unless an earlier device of theirs says "it was me" (D-120); an intruder cannot vouch for their own first sign-in | Built: `tests/modules/me/test_session_list_api.py`, `test_new_sign_in_attention_api.py`, `tests/modules/auth/test_session_end_concurrency.py`. **Not stopped**: an intruder holding the number can ask for the code too; the owner still sees their session and, with a passkey, only the owner can end it |
| **Someone deleting another person's account, or a brand leaving to avoid paying** | Deleting needs a step-up code for `delete_account`, so a stolen session cannot (item 6, D-122). A SIM swapper gets the code, but the deletion waits 30 days: the owner is told by a notice nobody can mute, it leads their attention list, and any of their sessions cancels it with no code. A brand cannot leave mid-deal: asking is refused while any deal is unpaid, unconfirmed or disputed, and a deal begun in the 30 days holds the erasure. Nothing new starts with someone who left, and the other side keeps each finished deal, with "someone who left" | Built: `tests/modules/me/test_account_deletion_api.py`, `test_account_deletion_erasure.py`, `test_account_deletion_concurrency.py`. **Not stopped**: an owner who never opens the app in 30 days (E1) |
| **A SIM swapper, however long they hold the number** | Passkeys (item 79, D-113): once an account has one, only it proves a risky change, and with passkey-only sign-in on, a code cannot even log in; adding a first passkey needs a week-old login, and every later one a passkey; losing them all means a 7-day reset any passkey sign-in cancels. Built, **off until the domain exists** | Built: `tests/modules/me/test_passkey_api.py`, `test_passkey_concurrency.py` |
| **Someone moving an account onto their own number**, to keep it for good | A code from the current number, bound to the new one, and a code from the new number (item 80, D-108), so a stolen session cannot. A SIM swapper also lacks a login a week old, which the change needs (D-109); and even with one, the new number waits 72 hours: the old number still logs in, the owner is told (a notification nobody can mute, first on the attention list) and cancels with no code, from any session. Then every session ends. A number left behind and reissued by the carrier finds a new account, never the old one. An admin's number changes only by script | Built: `tests/modules/me/test_phone_change_api.py`, `test_phone_change_concurrency.py`, `test_established_login_api.py`. **Not stopped**: a swap unnoticed for about 10 days, or one joined by malware holding the owner's own old login, with the owner not opening the app (E1). A lost number moves only from a login 30 days old, waits 7 days, and any login with that number cancels it (D-110); admins never move a number, which is written down (`security.md` section 1), so there is no help desk to talk round |

---

## 4. Text and link checks (`app/core/text_flags.py` and `app/core/links.py`, built 10 October 2026)

One module, used by every place free text from one person reaches another:

- **Money requests in text a creator reads**: phrases like "registration fee", "deposit", "pay to", "send ₹", "shipping charge", and a UPI ID or payment link in the text. They are **flagged**, never silently rewritten. The flag is a field the app shows as a warning beside the text ("we never ask creators to pay; if a brand does, report it"), and the brand is told before sending.
- **Contact details before a deal is agreed**: phone numbers in every common Indian shape (property tests found `987 654 3210` and `09876543210` slipping past, now fixed: D-090), emails, UPI IDs, and wa.me, t.me or similar links. Flagged the same way, **not hidden** (D-086): hiding them before a memo is accepted, as Upwork and Fiverr do, needs an in-app chat to talk through instead, which we do not have yet. Revisit when one exists.
- **Links we accept as fields** (proof `content_url`, dispute `evidence_url`; item 57): https only, a host on a published list (content platforms for proof, plus well-known file hosts for evidence), and every phishing shape refused: look-alike hosts, a name before an @, ports, punycode and non-Latin letters.
- Flags are worked out on read, from the text, so a better rule applies to old text too ("worked out, never stored", `backend.md` section 2). Every flag pattern has a test with real Tamil Nadu examples, and every false positive found becomes one. The text flags are under nightly mutation testing (D-091).

---

## 5. Frontend duties (the backend is ready; the screen must do its part)

- At the moment money is involved, say it plainly:
  - "You never pay to get a deal."
  - "You never enter your PIN to receive money."
  - "Check your own bank app, not a screenshot."
  - "Check the name your UPI app shows before you pay." (D-085)
- Show flags (section 4) as warnings next to the text, never hidden.
- Never turn user text into links. Show a link field's host before it opens.
- Report and block are one tap from anything another person sent.
- **A new UPI ID waiting its 24 hours is shown at the top of the creator's screens, with its time and one-tap "This wasn't me: cancel"**, which needs no code (item 82). The code prompt says: "Enter this code only here, in the app. We will never ask you to read it out or send it to anyone, even someone who says they are from us."
- **A new phone number waiting its 72 hours is shown at the top of every screen, brands' and creators', with when it takes over and one-tap "This wasn't me: cancel"**, which needs no code (item 80). The change screen says that every device will be logged out when it is made, and that the old number will then reach a new account, not this one. The lost-number screen (D-110) says to move the account within days, since a lost number is reissued to someone else after 90 days and its next holder could log in; and that we will never move a number on anyone's word, so nobody claiming to be us can.
- **A sign-in from another device (`new_sign_in`) is shown first, with its device, time and how it signed in, and one tap to "End this session"** (item 81). The sessions screen shows each label beside its sign-in time and method, never alone: a label is whatever the app sent.
- **A look-alike name is said as facts beside the name** (`brand_name_flag`, item 75): "looks like Nykaa; this account has not verified nykaa.com", never "fake" or "scam". A mixed-alphabet name is said as that.
- **A brand's verified domain is shown as the domain itself and its age** ("controls smallshop.in, checked today; registered March 2019"), never only a badge or the word "verified" (item 74, `legal.md` rule 3). A domain registered days ago is said plainly: it is what scams use.

---

## 6. How this file is kept true

- Re-checked against the code whenever it is read for work, and at least monthly with `docs/PLATFORM_AND_TECH_PLAN.md`'s review. The scams in section 2 are re-researched at least every six months: they move faster than the code.
- A new way of reaching someone gets its row in section 3 in the same change that builds it (rule 1).
- A row found untrue is corrected in the same change (`docs/README.md` section 0).

## 7. Gaps, named

**Corrected on 14 October:** rule 8 said every login code already warns against sharing it (the wording waits on item 62); rule 9 said the reporter learns the outcome (nothing tells them: item 102), and implied the IT Rules' clocks were on the queue (item 51); the text-flag row listed "briefs" where only a campaign's description and deliverables are checked, not its title.

**Closed the same day** (D-100): a reporter never told the outcome (item 102), and the app's database login able to unseal the records (item 97). **Closed on 15 October** (D-103): the queue had no legal clocks (item 51). **Closed on 16 October** (D-104): one item could only be taken down by suspending its whole account (item 52).

| # | Gap | Risk | Acting on it |
|---|---|---|---|
| 1 | **Only a domain is checked, not the business behind it** (item 74 built 17 October); brands without a website of their own have nothing to show | The pay-to-collab scam starts with a believable fake brand; a look-alike domain can be verified | Item 36 (GST), email proof once our domain exists. Look-alike names of the brands we protect are held since D-118; a brand on neither list is not protected, and the curated list is hand-made |
| 2 | **A campaign title is not checked for fee requests** | A short line such as "₹500 registration, DM us" in a title is not flagged | Add the title to the brief's flagged fields; small, in the next change to the campaign schema |
| 3 | **The login message does not yet say we never ask for it** | Fake support works on people who were never told | Item 62 |
| 4 | **Shared devices or networks at sign-up are not flagged** | Pumped records between one person's accounts are only visible as "one partner" | Item 61, a legal decision first |

## 8. Sources

Read on 10 October 2026, and checked to exist on 14 October; the two Upwork pages refuse automated checks, so they were last read on 10 October.

- [Storyboard18: scams surge in the creator economy](https://www.storyboard18.com/brand-makers/scams-surge-in-creator-economy-as-fake-brands-fraud-agencies-target-influencers-78864.htm)
- [IdentityKit: fake brand collaboration scams in India, 2026](https://www.identitykit.in/blog/fake-brand-collaboration-scams-india-2026)
- [Razorpay: fake payment screenshot scam, 2026](https://razorpay.com/learn/fake-payment-screenshot-scam/); [PhonePe Business: fake UPI payment scams](https://business.phonepe.com/articles/fake-upi-payment-scams-how-to-identify-and-prevent-fraud)
- [Business Standard: share of fake followers on Indian Instagram profiles](https://www.business-standard.com/india-news/what-part-of-insta-influencers-followers-are-fake-answer-will-shock-you-124041900840_1.html)
- [Upwork: how to identify scams, 2026](https://www.upwork.com/resources/upwork-scams); [Upwork: how to stay safe](https://support.upwork.com/hc/en-us/articles/211067668-How-to-stay-safe-on-Upwork)
- [Meta: fraud, scams and deceptive practices policy](https://transparency.meta.com/policies/community-standards/fraud-scams/): how the largest platform writes the rule down.
- Report a fraud in India: [cybercrime.gov.in](https://cybercrime.gov.in), or call 1930.
