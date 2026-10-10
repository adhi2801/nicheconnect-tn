# Trust and Safety Standard

Applies to every feature that lets one person **reach, pay, judge or be judged by** another, and to every way someone could cheat us. Read it before building any of them. The bar is `CLAUDE.md` section 7.0: **nobody on this platform should be able to scam anyone else, or us, through anything we built**, and where a scam happens outside the platform, what they did here must help them see it coming.

`security.md` keeps attackers out of the system. This file is about people **inside** it, with real accounts, using the product as built to harm someone. Both apply.

Status words: **Built** (in the code, with a test), **Owed** (tracked in `docs/BACKEND_COMPLETE.md` section 3.10), **Frontend** (the backend is ready; the screen must do its part, `ux.md`).

---

## 1. Rules for everyone building (binding)

1. **Map who can reach whom.** Every proposal lists each way the feature lets one account reach another: a notification, text they read, a link they open, a record about them. Each one gets a row in section 3, with its protection and its test.
2. **Every way of reaching someone has a daily ceiling per account**, not only a per-minute rate limit. A per-minute limit stops a script, not a person spamming by hand for an hour. `tests/modules/test_daily_ceilings.py` lists every such route and fails if one loses its ceiling; a new route that reaches someone is added to it in the same change.
3. **Free text another person reads is untrusted.** It is stored and returned as plain text, never rendered as HTML, and the frontend never turns it into links. A link we accept as a field (proof, evidence) is checked against a list of hosts we know (section 4).
4. **Money talk stays on the record.** Nothing in the product ever asks anyone to pay anyone except the brand paying the creator the agreed fee, through their own bank. **A creator never pays to get a deal**: any brief, note or memo text asking a creator for money is flagged (section 4).
5. **Proof of payment is the receiver's own bank, never a screenshot.** Only the creator can confirm money arrived (D-027), and every screen that asks them says to check their own bank app.
6. **Records about people resist being gamed.** A figure that makes someone look good or bad counts things that are hard to fake, says how many it rests on (D-038), and never counts the same pair of accounts as independent evidence (section 3.3).
7. **Everyone can say no and be left alone**: decline, withdraw, mute (D-079), report (D-061), and block (item 59). A new way of reaching someone must respect blocks in the same change, with a test in `tests/modules/auth/test_block_api.py`.
8. **We never ask for a login code, a UPI PIN or a password**, in any message, ever. Every login code says so, and so does the app.
9. **A report is answered.** Reports reach the admin queue with the clocks of the IT Rules (`legal.md` section 3.3), and the reporter learns the outcome.

---

## 2. The scams that actually happen

Researched 10 October 2026, sources in section 6.

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
| An invitation, with a note | 25 waiting per campaign (D-084), and 100 a day per brand across all campaigns, repeats likewise; creator declines in one tap; plain text | Built |
| A rejection reason and note | Reason is a code; note ≤ 500 characters, plain text | Built |
| A deal memo, its extra terms | Accepted terms never change, and the deal record proves it (D-057); the creator can ask for changes or decline | Built |
| A revision request on proof | One change restarts the clock (D-025); note plain text | Built |
| Marking a payment sent | Only the creator can confirm it arrived (D-027); the reference shape is checked; a dispute holds the record short of unpaid | Built |
| **Payment requests disguised in text** ("pay ₹2,000 registration") | **Flag money requests in brief, note, memo and message text** (section 4) | **Owed** |
| **A brand name copying a famous brand** | Verified business from GST (item 36). Until then, no "verified" mark of any kind | **Owed** (item 36) |
| Contact details in text, pulling the creator off the record | Flag phone numbers, emails, UPI IDs and messaging links in text the other side reads before a deal is agreed (section 4) | **Owed** |
| Repeated contact after a no | **Block** (`POST /me/blocks`): once either side blocks, no invitation, repeat or application starts in either direction, and neither appears in the other's search, matches or discovery. Agreed deals carry on; the blocked side is never told, and every refusal reads as not found | Built |

### 3.2 Creator → brand

| Way | Protection | Status |
|---|---|---|
| An application, with a pitch and quote | One per campaign (unique); 20–1,000 characters; plain text; 30 a day per creator | Built |
| Proof: a link and screenshots | Screenshots are cleaned of hidden data and sealed (D-065, D-066); readings check the handle and the date (D-070). The link must be on a known content platform, and look-alike hosts, names before an @, ports and punycode are refused (`app/core/links.py`) | Built |
| A change request on a memo | One message ≤ 1,000 characters | Built |
| A channel link on the rate card | Only the platform's own hosts (`rate_card_service.py`) | Built |
| **Bought audiences** | Results read from proof (D-070); connected accounts with platform numbers (items 29–31) | Partly built; **Owed** (29–31) |
| **A channel that is not theirs** | Proof readings check the handle on the screenshot matches the channel; real ownership needs connected accounts (item 29) | Partly built |
| Take the goods and vanish | The delivery record counts it (D-038); cancellation kinds (D-026) | Built |
| Repeated contact after a no | Block, both ways (above) | Built |

### 3.3 Anyone → the records (and so → everyone who reads them)

| Way | Protection | Status |
|---|---|---|
| A dispute, with entries and evidence links | Both sides on the record; we never judge (D-028, D-035). Evidence links only to known platforms and file hosts (`app/core/links.py`); uploaded evidence is the better end | Built |
| A report | One open report per reporter per subject (D-061); 10 an hour and 30 a day per account | Built |
| **Pumped records: deals between accounts one person controls** | Records show how many **different** counterparties they rest on, and a figure resting on one or two counterparties says so. Pairs of accounts sharing a device or network at sign-up are flagged to the admin, never shown publicly | **Owed** |
| Reviews or ratings bought or invented | None exist except records from real deals (`legal.md` section 3.6) | Built |

### 3.4 Anyone → us

| Way | Protection | Status |
|---|---|---|
| Many accounts from one person | One account per phone number (unique); login-code limits per phone and network (`security.md` section 5) | Built |
| Scraping creators | Search and matching are signed-in brands only, 30 a minute and 600 a day per account; no contact details anywhere | Built |
| Running up our AI bill | Daily ceiling on proof reading (D-070) | Built |
| Abusing invite attribution | It carries no reward. **Any reward is designed with its abuse limits first** | Built (no reward) |
| An admin misusing access | Every view and action in the append-only admin log (D-061) | Built |
| Impersonating us ("support") | We never ask for codes, PINs or passwords (rule 8). **The login message's wording must say so: Confirm the MSG91 template** | **Owed** |

---

## 4. Text and link checks (owed, one design for all of them)

One module, used by every place free text from one person reaches another:

- **Money requests in text a creator reads** (briefs, invitation notes, memo terms, revision notes): phrases like "registration fee", "deposit", "pay to", "send ₹", "shipping charge", and a UPI ID or payment link in the text. They are **flagged**, never silently rewritten. The flag is a field the app shows as a warning beside the text ("we never ask creators to pay; if a brand does, report it"), and the brand is told before sending.
- **Contact details before a deal is agreed**: phone numbers, emails, UPI IDs, and wa.me, t.me or similar links. They are flagged the same way. They are **flagged, not hidden** (D-086): hiding them before a memo is accepted, as Upwork and Fiverr do, needs an in-app chat to talk through instead, which we do not have yet. Revisit when one exists.
- **Links we accept as fields** (proof `content_url`, dispute `evidence_url`): **Built** (`app/core/links.py`, item 57). https only, a host on a published list (content platforms for proof, plus well-known file hosts for evidence), and every phishing shape refused: look-alike hosts, a name before an @, ports, punycode and non-Latin letters.
- Flags are worked out on read, from the text, so a better rule applies to old text too ("worked out, never stored", `backend.md` section 2). Every flag pattern has a test with real Tamil Nadu examples, and every false positive found becomes one.

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

---

## 6. Sources (read 10 October 2026)

- [Storyboard18: scams surge in the creator economy](https://www.storyboard18.com/brand-makers/scams-surge-in-creator-economy-as-fake-brands-fraud-agencies-target-influencers-78864.htm)
- [IdentityKit: fake brand collaboration scams in India, 2026](https://www.identitykit.in/blog/fake-brand-collaboration-scams-india-2026)
- [Razorpay: fake payment screenshot scam, 2026](https://razorpay.com/learn/fake-payment-screenshot-scam/); [PhonePe Business: fake UPI payment scams](https://business.phonepe.com/articles/fake-upi-payment-scams-how-to-identify-and-prevent-fraud)
- [Business Standard: share of fake followers on Indian Instagram profiles](https://www.business-standard.com/india-news/what-part-of-insta-influencers-followers-are-fake-answer-will-shock-you-124041900840_1.html)
- [Upwork: how to identify scams, 2026](https://www.upwork.com/resources/upwork-scams); [Upwork: how to stay safe](https://support.upwork.com/hc/en-us/articles/211067668-How-to-stay-safe-on-Upwork)
- Report a fraud in India: [cybercrime.gov.in](https://cybercrime.gov.in), or call 1930.
