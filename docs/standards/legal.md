# Legal Standard

Applies to every feature, every word the product says, every record about a person, every outside service and every promise we make. Read it before building anything in the areas of section 3. The bar is `CLAUDE.md` section 7.0: **no regulator's letter, court notice or user complaint should ever find us unprepared.**

**What this file is, and is not.** It is our map of the Indian law that touches a brand–creator marketplace, researched from public sources and dated (10 October 2026). It is **not legal advice**, and constraint 6 still holds: wherever a rule's exact reach, wording or number decides what we build, the row says **Confirm**, and a lawyer or chartered accountant answers it in the validation pack before launch. Nothing marked Confirm is built on a guess.

Status words in this file:

| Word | Meaning |
|---|---|
| **Built** | In the code or docs, with a test or a decision |
| **Owed** | We know what to do; it is not done yet. Tracked in `docs/BACKEND_COMPLETE.md` |
| **Confirm** | A professional must answer before we rely on it |
| **Founders** | Outside the code: the company, contracts, filings |

---

## 1. Rules for everyone building (binding)

1. **Every proposal has a "Legal" line.** It names which section of this file the feature touches, what we will do, and which Confirm items it waits on. No such line, no build. A feature whose Confirm item decides its design waits; one where it only decides wording ships behind a setting that stays off (the pattern of D-070 and D-085).
2. **Persuade, never trick** (section 3.5). The thirteen dark patterns the Central Consumer Protection Authority bans are banned here, in the API's design as much as on any screen.
3. **Say only what is true and checkable.** No "guaranteed", "verified", "certified", "safe" or "instant" unless a defined check makes it so, and the check is named. The money words of constraint 1 stay banned (`tests/test_banned_terms.py`).
4. **Anything we show about a person or business is a fact from the record**: dated, with its sample size, and with the other side's answer where one exists (section 3.12). Never an adjective.
5. **Consent is an event**, stored with the time and the notice version it answered, and withdrawing it is as easy as giving it: every consent has its own withdraw endpoint (`security.md` section 7).
6. **Only what a feature needs**, kept only as long as it needs it, in the person's export or explained in `NOT_EXPORTED`.
7. **We never hold, move or route money** (constraint 1). A design that would put us in the flow of funds stops here; payment-aggregator regulation (section 3.9) is the reason, not only our principle.
8. **Each law has an owner and a date.** This file is re-checked once a quarter and whenever a new rule is notified. Each row's sources carry the date they were read.

---

## 2. The company itself (founders, before the first real user)

| Item | Why it matters | Status |
|---|---|---|
| **Incorporate** (private limited company or LLP), with a registered office | Terms, privacy notice, grievance officer, GST and every contract need a legal person to name. A sole founder's name on them makes the founder personally liable | Founders |
| **Founders' agreement** with vesting, and every founder and contributor **assigning their code, designs and name rights to the company** | Most early-stage lawsuits are between founders, or over who owns the code. Every investor's lawyer asks for this first | Founders |
| **Trademark search, then filing** for the product's name in classes 9, 35 and 42 | Launching under a name someone else registered invites a cease-and-desist and a forced rename. The name (Colyv) is itself still awaiting both founders' agreement | Founders |
| **Startup India (DPIIT) recognition** | Tax and compliance relief, and cheaper trademark filing for startups | Founders |
| A separate company bank account | We never hold users' money, but the company's own income must never mix with a founder's | Founders |

---

## 3. The law, area by area

### 3.1 Personal data: the Digital Personal Data Protection Act, 2023, and the DPDP Rules, 2025

**When.** Rules notified 13–14 November 2025, in three phases: the Data Protection Board at once; consent managers (Rule 4) after 12 months, **13–14 November 2026**; **every core duty of a business** (notice, consent, security, breach notice, retention, erasure, children, grievances: Rules 3, 5–16, 22–23) after 18 months, **13–14 May 2027**. Penalties reach ₹250 crore per breach of duty.

| Duty | What we do | Status |
|---|---|---|
| Notice before consent, in plain English, listing the data, the purpose and how to withdraw (Rule 3) | Every consent records the notice version it answered (D-036, D-055, D-085). The wording itself comes from the validation pack | Built (mechanism); **Confirm** (wording) |
| Consent free, specific, withdrawable as easily as given | A withdraw endpoint for every consent | Built for the Passport, rate card and UPI ID |
| Reasonable security safeguards (Rule 6) | `security.md`, ASVS level 2 | Owed: the items `security.md` lists |
| Breach: tell the Data Protection Board and every affected person (Rule 7) | `docs/INCIDENT_RESPONSE.md` section 5. Sources describe a detailed report to the Board within 72 hours; the exact clock is a Confirm item | **Confirm** |
| Erase when the purpose is served or consent is withdrawn; publish retention periods (Rule 8) | Account deletion (E8) waits on the retention answer | **Confirm**, then Owed |
| **Children (under 18): verifiable parental consent; no tracking, behavioural monitoring or targeted advertising** (Section 9, Rule 10) | Adults only (D-086, section 3.10) | Built; **Confirm** |
| A contact for privacy questions and grievances, published (Rule 14) | The grievance officer of section 3.3 can serve both | Owed (founders name the person) |
| Processors on contract: AWS, Sentry, MSG91, Anthropic | Data processing terms with each, kept with the validation pack | Founders |
| Data leaving India | Allowed unless the government restricts a country; Sentry and Anthropic process outside India | **Confirm** |

### 3.2 Security incidents: CERT-In Directions of 28 April 2022 (in force 28 June 2022)

They apply to **every body corporate**, not only large ones.

| Duty | What we do | Status |
|---|---|---|
| **Report listed cyber incidents to CERT-In within 6 hours of noticing them** | `docs/INCIDENT_RESPONSE.md` section 5 | Built (10 October 2026) |
| **Keep the logs of all ICT systems for 180 days, within India** | CloudWatch in Mumbai, kept 180 days, and OpenTofu refuses less (`log_retention_days`, D-086) | Built |
| Synchronise clocks with NIC or NPL time, or a source that does not deviate from them | ECS and RDS use the Amazon Time Sync Service | **Confirm** that it satisfies the direction |
| Name a point of contact with CERT-In | A founder | Founders |

### 3.3 Hosting what users post: the IT Act, 2000, section 79, and the Intermediary Rules, 2021 (amended 10 February 2026)

We host pitches, briefs, notes, proof links and screenshots. Protection from liability for them (safe harbour) holds only while we do our due diligence.

| Duty | What we do | Status |
|---|---|---|
| Publish terms of use, a privacy policy and the rules users must follow | Drafted by a lawyer; served by the frontend | **Founders** + **Confirm** |
| A grievance officer, named and published; **acknowledge within 24 hours, resolve within 7 days** (cut from 15 by the 2026 amendment); unlawful-content complaints within 36 hours, intimate images within 2 hours | Reports (D-061) are the mechanism. Their queue needs the clocks above, visible to the admin | Owed |
| **Remove content within 3 hours of a court order or government notice** (cut from 36 by the 2026 amendment) | The admin can suspend accounts; a takedown of one item of content is owed | Owed |
| Label synthetically generated **audio, image or video** | Our AI produces text only (proof reading, D-070), which the definition excludes. If we ever generate images or video, labels and metadata come first | Not applicable today |

### 3.4 Selling services online: the Consumer Protection Act, 2019, and the E-Commerce Rules, 2020

A platform where brands find and book creators' services is very likely a **marketplace e-commerce entity** (**Confirm**). As reported, the Amendment Rules, 2026 were notified 9 September 2026 and take effect **1 January 2027** (**Confirm** the text).

| Duty | What we do | Status |
|---|---|---|
| Show the company's name, address and contact details, and a customer-care contact | Frontend, once incorporated | Founders |
| Grievance officer: **acknowledge within 48 hours, resolve within one month**, give the complainant a copy | Shared with section 3.3, and the stricter clock wins | Owed |
| **Explain publicly the main parameters that rank sellers and services, in descending order of importance** (Rules 5(3)(d) and, from 2027, 5(3)(f)) | Creator search, a campaign's matches and campaigns-for-me all rank people. A public page must say, in plain words, what moves someone up (for example: free on the date asked, niche, city, delivery record), in order. It changes in the same pull request as the ranking code | **Owed** |
| **Sponsored listings labelled clearly** | We sell no placement today. If we ever do, it is labelled in the API (a field), not only on screen | Rule for the future |
| **Yearly dark-pattern self-audit, with the result displayed** | Section 3.5; the first audit before launch | Owed |
| Do not use what the marketplace learns to promote ourselves or one seller over others without consent | Matching ranks on the brief and the record, never on who pays us | Built (D-052), kept |
| No unfair trade practice; no misleading advertisement (sections 2(47) and 2(28)) | Rule 3 of section 1 | Ongoing |

### 3.5 Persuasion, not manipulation: the Guidelines for Prevention and Regulation of Dark Patterns, 2023

Notified 30 November 2023. The Consumer Protection Authority's advisory of June 2025 asked platforms to self-audit within three months, and from 2027 the E-Commerce Rules make the audit yearly.

**Honest persuasion is legal, and we use it.** Showing a real fact at the moment it helps, a default that serves the user, a true count of how many others did something, a reminder before a real deadline. **Deception is not, and we never use it,** however well it converts. The thirteen banned patterns, and our rule for each:

| Banned pattern | Our rule |
|---|---|
| False urgency | A deadline or a "spots left" count only when it is real and comes from the record (a campaign's closing date, its invitation limit) |
| Basket sneaking | Nothing is ever added to what someone buys or agrees to without their own action |
| Confirm shaming | Declining, withdrawing and opting out are worded as neutrally as accepting |
| Forced action | No feature requires an unrelated action (sharing contacts, publishing a Passport) to use another |
| Subscription trap | When we charge, cancelling is one action, as easy as subscribing, and no card is taken for a "free" trial |
| Interface interference | The choice that is better for us is never styled to look like the only choice |
| Bait and switch | The terms shown are the terms applied; a memo once accepted does not change, and the deal record proves it (D-057) |
| Drip pricing | Every charge is shown before commitment, in full, never revealed at the last step |
| Disguised advertisement | Anything paid for is labelled; creators' content carries its ad disclosure (section 3.7) |
| **Nagging** | Notifications obey each person's preferences and quiet hours (D-079). A reminder repeats only on a real change or a real deadline |
| Trick question | Consent and settings questions are worded so that "yes" means yes |
| SaaS billing | No silent renewals or charges after a free period without a clear, timely notice |
| Rogue malware | Never: no hidden code, no misleading download |

Every screen design is checked against this table (`ux.md`), and `docs/PSYCHOLOGY_AND_TRUST.md` uses only the left side's allowed versions.

#### The growth levers we use, hard and on purpose (Adhi, 10 October 2026: "we need to, to survive, in legal ways")

Persuasion is not the enemy; deception is. Every lever below is legal **because the fact behind it is true**, and each one works harder for being true: a marketplace lives on trust, and one fake "3 spots left" found out costs more users than it ever won. The column on the right is the line; crossing it turns the lever into a banned pattern.

| Lever | How we use it | The line |
|---|---|---|
| **Social proof** | "14 food creators in Coimbatore applied this week", "Brands paid on time in 92% of 38 deals" | Real counts from the record, with the sample size; never invented, rounded up or borrowed from elsewhere |
| **Scarcity** | A campaign's real closing date; "25 invitations, 3 left"; "booked until 20 Nov" | Only limits that exist in the product; never a timer that resets |
| **Urgency** | Reminders before a real deadline: memo answer, proof review, payment due | Only real deadlines, and within each person's notification settings (D-079); never nagging |
| **Loss aversion** | "Your 4 finished deals are not on your Passport yet", "This payment becomes late tomorrow" | True statements about their own account; never guilt or shame ("No thanks, I don't want more deals" is confirm-shaming) |
| **Reciprocity** | Free tools that help before we ask for anything: fair-rate guidance, the media kit, the deal record | Free means free; any later charge is shown before commitment, in full |
| **Commitment, one step at a time** | Profile, then Passport, then first application; progress shown truthfully | Every step can be undone; no step is forced to use another feature |
| **Endowment** | A creator's record and Passport grow in value the more they deliver, a reason to stay that they earned | Their data stays theirs: the export is always one call (DPDP), so the switching cost is value, never lock-in |
| **Defaults that serve the person** | A repeat deal arrives pre-filled; reminders start on, and turn off in one tap | A default never spends their money, publishes them, or shares their data |
| **Anchoring** | Fair-rate guidance shows the real range for their niche and city before they quote (D-056) | Real market data with its sample size; null below the floor |
| **Status** | Badges for verifiable facts only: "10 deals delivered on time" | Never bought, never given by us by hand, never for anything unchecked |
| **Referrals** | Invite codes credit who brought whom (D-080) | Any reward is disclosed in full, with its abuse limits designed first (`trust-and-safety.md`) |
| **Speed** | One tap to repeat, accept, decline or pay | The same one tap to cancel, withdraw or leave |

### 3.6 Reviews and ratings: IS 19000:2022

The Bureau of Indian Standards' standard for online consumer reviews has applied since 25 November 2022. It is described as **voluntary** as of July 2025, and the government has consulted on making it mandatory. We meet it anyway: our ratings and records come only from real deals between the two parties; they are never bought, never written by us, never hidden for being negative; each shows its date and how many deals it rests on (D-038).

### 3.7 Advertising by creators: ASCI and the Consumer Protection Authority

| Rule | What it means for us | Status |
|---|---|---|
| ASCI Influencer Advertising Guidelines (in force 14 June 2021, updated since): a clear label (#ad, #sponsored, the platform's paid-partnership label) in the first lines or seconds. **Addendum of 7 April 2025:** finance and health creators disclose their qualifications. Virtual influencers say they are not human | The memo carries `disclosure_required`; the creator confirms disclosure when submitting proof. The content pre-check (item 39) flags, never decides | Built (confirmation); Owed (item 39) |
| The Consumer Protection Authority's Endorsement guidelines (January 2023); under the Act, **a creator who endorses misleadingly can be fined up to ₹10 lakh, ₹50 lakh for a repeat, and barred from endorsing** | We tell creators this plainly, and we never pressure anyone to drop a disclosure | Owed (copy, from the validation pack) |
| Brand and creator are both responsible for the disclosure | We are neither, but our records show who agreed to what | Built (deal record) |
| Our own marketing must be truthful and substantiated (ASCI code) | Rule 3 of section 1 | Ongoing |

### 3.8 Tax

**The Income-tax Act, 2025 replaced the 1961 Act on 1 April 2026.** Old section numbers survive in common use, but the law now cites the table in section 393.

| Rule | Why it touches us | Status |
|---|---|---|
| **TDS by an e-commerce operator** (old section 194O, now section 393(1), table item 8(v)): 0.1% on the gross amount of services facilitated through the platform, **even where the buyer pays the seller directly**, which the law deems paid by the operator | Brands pay creators directly through us as a facilitator. Whether we count as an "e-commerce operator" for these deals, from what threshold, and how a platform that never holds the money can deduct, decides our whole payment design | **Confirm, before launch, first priority** |
| **TDS on benefits** (old 194R, now 393(1) item 8(iv)): 10% when barter goods kept by a creator exceed ₹20,000 in a year from one giver (CBDT Circular 12 of 2022: not due if the product is returned) | This is the brand's duty, not ours. Item 33 tracks the running total so neither side is surprised | **Confirm** (wording), then Owed (item 33) |
| GST TCS by an e-commerce operator (CGST Act section 52) | Due only where the operator collects the consideration. We never do, so it appears not to apply | **Confirm** |
| Our own GST on what we charge, once turnover crosses the threshold | Founders, with a CA | Founders |
| Invoices and yearly statements for users (E6) | Waits on the GST and TDS answers | **Confirm** |

### 3.9 Payments: RBI and NPCI

| Rule | What it means for us | Status |
|---|---|---|
| The RBI's payment aggregator rules regulate anyone who receives and settles money for merchants | We receive and settle nothing (constraint 1), so they do not reach us. The UPI pay link (D-085) only opens the brand's own UPI app with the creator's ID filled in | Built, kept |
| NPCI's September 2026 privacy direction: mask phone-number UPI IDs, and offer chosen names | We refuse phone-number UPI IDs outright (D-085) | Built |
| UPI person-to-person limit: ₹1 lakh in 24 hours from one bank account | No pay link above it; the brand pays by bank transfer (D-085) | Built |

### 3.10 Contracts, and who can make them

| Rule | What it means for us | Status |
|---|---|---|
| Indian Contract Act, 1872, with the IT Act section 10A: a contract made electronically is valid | The deal memo is the brand's and creator's contract, and we are not a party to it. The terms of use are ours with each user. A lawyer drafts both | **Confirm** |
| **A minor cannot contract** (section 11; a contract with a minor is void, and a guardian cannot sign a service contract on a minor's behalf: *Raj Rani v. Prem Adib*, Bombay High Court) | **Adults only (D-086).** Creating a profile takes a date of birth, checked against today in Tamil Nadu; only the time of the confirmation is kept, never the date. Nothing is built for minors | Built; **Confirm** that this is enough |
| Stamp duty on agreements (Indian Stamp Act and Tamil Nadu's rates) | Whether an accepted memo is an "agreement" that needs stamping | **Confirm** |
| Disputes: governing law, courts (Coimbatore), and arbitration in the terms of use | We record, we never adjudicate (disputes, D-028, D-035) | **Confirm** |

### 3.11 Content and intellectual property

| Rule | What it means for us | Status |
|---|---|---|
| Copyright Act, 1957, sections 19 and 30: a licence must be in writing, signed by the owner; with no stated duration it is **deemed five years**, and with no stated territory, **India** | Our memo states usage rights in days, explicitly. **Whether a click-accepted memo counts as "signed"**, or needs an electronic signature (item 35, eSign), is the question | **Confirm** |
| The creator owns their content; a brand gets only what the memo licenses | Never described as a transfer of ownership | Built (memo wording) |
| Trademarks and logos a brand uploads are theirs to use | The terms of use say so | **Confirm** |

### 3.12 What we say about people and businesses: defamation

Criminal defamation is now section 356 of the Bharatiya Nyaya Sanhita, 2023, in force since 1 July 2024; civil claims run alongside. A public record that a brand paid late is lawful when it is **true and in the public good**, so it must be both, every time:

- only facts the record holds, with dates (`unpaid` is "not marked paid by day N", never "a defaulter");
- the sample size beside every figure, and `null` below the floor (D-038);
- the other side's account beside a dispute (D-028, D-035), and "unresolved is a fact about the dispute, not a finding about either of you";
- no adjectives about a person, ever.

### 3.13 Login codes and messages: TRAI

| Rule | What it means for us | Status |
|---|---|---|
| TRAI's commercial-messaging regulations (TCCCPR 2018): every SMS from a business goes from a registered sender, with a template registered on DLT; variable tags required on new templates from 14 January 2026 | Login codes go by WhatsApp first (MSG91, D-058). **Any SMS fallback needs DLT registration first** | Founders (DLT), with MSG91 |
| WhatsApp's business policy: people opt in to business messages | Login codes are requested by the person; anything else waits for E1 and its opt-in | Owed with E1 |

### 3.14 Accessibility

The Rights of Persons with Disabilities Act, 2016 requires accessible information and communication technology. We hold the frontend to WCAG 2.2 AA (`frontend.md`). **Confirm** which standard binds a private platform.

### 3.15 Open-source licences

Every dependency's licence is known before it is added (`security.md`); a copyleft licence (GPL, AGPL) in the served app needs a decision. Syft's SBOM lists every licence in the API image on each CI run, and **CI fails on any licence not on the approved list** (D-086): permissive licences, plus LGPL-3.0 and MPL-2.0 for libraries used unchanged.

### 3.16 Our own AI features

| Rule | What it means for us | Status |
|---|---|---|
| The AI provider processes personal data for us (DPDP) | Proof reading is off until the validation pack answers (D-070) | Built (off) |
| A decision with real effect on a person is never taken by the AI alone | AI flags and suggests (proof reading, item 39 pre-check, item 40 briefs); a person decides | Rule |
| The 2026 rules on synthetic media | Text only today; see section 3.3 | Not applicable today |

### 3.17 Creators are independent

Creators are independent professionals contracting with brands, never anyone's employees, and never ours. We do not set their hours, supervise their work or pay them; nothing in the product or its words suggests otherwise.

---

## 4. Questions for the validation pack (lawyer and CA), by priority

**Before any code depends on them:**

1. **Income-tax Act 2025 section 393(1) item 8(v) (old 194O):** are we an e-commerce operator for deals brands pay directly, and if so, how does a platform that never holds the money comply?
2. **Under-18 creators:** confirm that adults-only, with a declared date of birth, satisfies DPDP section 9 and contract law, or say what does.
3. **Are we a marketplace e-commerce entity** for services under the E-Commerce Rules, and which of the 2026 amendments apply from 1 January 2027?
4. **Click-accepted usage rights:** do they satisfy Copyright Act section 30, or must the memo be e-signed?

**Before launch:**

5. DPDP: the notice wording for each consent; retention periods; the breach clock; cross-border processors.
6. CERT-In: does the Amazon Time Sync Service meet the clock-synchronisation direction?
7. Stamp duty on an accepted memo, in Tamil Nadu.
8. GST TCS (section 52) not applying, confirmed in writing.
9. TDS on benefits (old 194R): the wording we show brands and creators.
10. Terms of use, privacy policy, grievance process, and governing law and arbitration.
11. The accessibility standard that binds a private platform.

---

## 5. Sources (read 10 October 2026)

- DPDP Rules phases and duties: [Wikipedia, DPDP Rules 2025](https://en.wikipedia.org/wiki/Digital_Personal_Data_Protection_Rules,_2025); [DPDP Rules, all 22 rules with effective dates](https://dpdpa.dcomply.in/rules/); [EY: DPDP Act and Rules](https://www.ey.com/en_in/insights/cybersecurity/transforming-data-privacy-digital-personal-data-protection-rules-2025)
- CERT-In Directions 2022: [DataGuidance](https://www.dataguidance.com/news/india-cert-issues-cybersecurity-direction-mandating); [Siri Law: the 6-hour mandate](https://sirilawllp.com/a-comprehensive-guide-to-indias-cert-in-6-hour-cyber-incident-reporting-mandate/)
- IT Rules amendment 2026: [Khaitan & Co](https://www.khaitanco.com/thought-leadership/MeitY-notifies-the-IT-Amendment-Rules-2026); [DSCI](https://www.dsci.in/resource/content/it-amendment-rules-2026); [MeitY: IT Rules 2021 as updated](https://www.meity.gov.in/static/uploads/2024/02/Information-Technology-Intermediary-Guidelines-and-Digital-Media-Ethics-Code-Rules-2021-updated-06.04.2023-.pdf)
- E-Commerce Rules and the 2026 amendment: [Trilegal: E-Commerce Rules 2020](https://trilegal.com/knowledge_repository/consumer-protection-e-commerce-rules-2020/); [Argus Partners: Amendment Rules 2026](https://www.argus-p.com/updates/updates/overview-of-the-consumer-protection-e-commerce-amendment-rules-2026/); [Bar & Bench](https://www.barandbench.com/law-firms/view-point/consumer-protection-e-commerce-amendment-rules-2026-from-consumer-disclosure-to-platform-governance)
- Dark patterns: [Department of Consumer Affairs press release, June 2025](https://consumeraffairs.gov.in/public/upload/admin/cmsfiles/pressRelease/Central_Consumer_Protection_Authority_issues_advisory_to_E-Commerce_Platforms_for_self-audit_within_3_months_to_detect_Dark_Patterns_and_ensure_its_resolutionpress_release.pdf); [IAPP](https://iapp.org/news/a/india-s-ccpa-guidelines-on-dark-patterns-welcome-signal-but-law-is-still-soft)
- Reviews: [PIB: BIS standard for online reviews](https://www.pib.gov.in/Pressreleaseshare.aspx?PRID=1882828&reg=3&lang=2)
- ASCI: [ASCI social media disclosure guidelines](https://www.ascionline.in/social/guidelines/); [Khaitan & Co on the 2021 guidelines](https://www.khaitanco.com/thought-leaderships/ASCI-releases-influencer-advertising-guidelines-for-digital-media-Effective-14-June-21-onward)
- Tax: [TaxGuru: TDS under the Income Tax Act 2025](https://taxguru.in/income-tax/tds-rates-income-tax-act-2025-1-april-2026.html); [TDSMAN: e-commerce TDS, section 393(1)](https://blog.tdsman.com/2026/07/tds-on-e-commerce-transactions-section-3931-194o/); [ClearTax: section 194O](https://cleartax.in/s/section-194o); [TaxGuru: CBDT circular on 194R](https://taxguru.in/income-tax/assessment-cbdt-circular-section-194r-tds-benefits-perquisites.html); [TaxTMI: no GST TCS without collecting consideration](https://www.taxtmi.com/article/detailed?id=16412)
- UPI: [Google Pay help: UPI limits](https://support.google.com/pay/india/answer/7359498?hl=en); [NPCI UPI masking, September 2026](https://www.techpillow.co/blog/npci-upi-phone-number-masking-privacy-dpdp-2026)
- Minors: [India Legal: the child who clicked "I agree"](https://indialegallive.com/cover-story-articles/il-feature-news/social-media-children-minor-contract-invalid-supreme-court/); [K&S: children's data under DPDP](https://ksandk.com/data-protection-and-data-privacy/child-data-protection-under-dpdp-act-parental-consent-rules/)
- TRAI DLT: [WebEngage: TRAI DLT regulations](https://docs.webengage.com/docs/trai-sms-dlt-regulations-india); [SMS Gateway Center: variable tagging from January 2026](https://www.smsgatewaycenter.com/blog/trai-dlt-mandatory-variable-tagging-sms-templates/)
