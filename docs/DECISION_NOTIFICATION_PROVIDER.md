# Decision needed: how a login code reaches a phone

**Status: needs Adhi's decision (D-051).** Researched 23 September 2026.
Nothing here is in the code, and no account has been opened anywhere.

## Why this one first

**Nobody can log in outside a developer's laptop.** No provider is chosen, so
the OTP sender refuses outside local and test. Every endpoint built in Phases
A, B and C — 64 of them — is unreachable by a real person. This is the single
decision that turns the backend from a demo into something a creator in
Madurai can use, and it also unblocks E1 (notifications) and C5 (usage-rights
reminders).

It is a decision and not a task: it costs money, it needs an account in the
company's name, and some of it is paperwork only a founder can sign.

## Three constraints that decide this, before any price

**1. SMS in India is blocked without DLT registration.** TRAI requires every
business sending transactional SMS to register as a DLT Principal Entity with
a telecom operator, and to register its sender ID (header) and every message
template. Unregistered routes are **blocked by Jio, Airtel, Vi and BSNL**, and
an unregistered template can draw a reported ₹50,000 fine per instance. This
is paperwork with a lead time, not a code change. **If SMS is wanted at all,
start the registration now**, because nothing else on this page takes as long.

**2. Android 17 delays ordinary OTP SMS by three hours.** For apps targeting
API level 37, an SMS containing a one-time code is withheld for three hours:
the `SMS_RECEIVED_ACTION` broadcast is suppressed and the SMS database is
filtered. Exempt are the default SMS app, assistant apps, and **apps already
using the SMS Retriever or SMS User Consent APIs**. So if we send SMS, the
message must be in SMS Retriever format, carrying the app hash, or the code
will not fill in by itself on a current Android phone. That constraint belongs
in the provider choice, because the template is registered under DLT and
changing it later means re-registering it.

**3. The WhatsApp account must be registered in India.** Meta charges an
authentication message at the domestic Indian rate only when the WhatsApp
Business Account is itself registered in India. From outside, the same message
to the same Indian number costs about **22 times more**. This is a
company-registration detail that is expensive to get wrong and awkward to
change afterwards.

## What each channel costs

Per delivered login code, at pilot volume. **GST is quoted from the sources
below and is exactly the sort of figure `CLAUDE.md` constraint 6 says belongs
in the validation pack — confirm it there before it goes in a budget.**

| Channel | Meta or carrier rate | With 18% GST | Notes |
|---|---|---|---|
| **WhatsApp** authentication, India-registered account | **₹0.1150** | ₹0.1357 | Most BSPs add 10–30% on top |
| WhatsApp authentication, account outside India | ₹2.4971 | ₹2.9466 | The 22× trap in constraint 3 |
| **SMS** transactional OTP | **₹0.12–0.20** typical (range ₹0.10–0.45) | — | MSG91 ≈ ₹0.15, Gupshup ≈ ₹0.17. Falls toward ₹0.10 above ~1 lakh/month |

**At pilot scale the price is not the deciding factor.** A thousand logins a
month is about ₹136 on WhatsApp or ₹150–200 on SMS. Neither number should
choose this. Reach, delivery and setup time should.

**One timing note:** the plan records that WhatsApp service replies inside the
24-hour window become billable from **1 October 2026**, which is eight days
away. That does not change the authentication rate above, but it does mean any
quote taken today should be re-checked at signup.

## The options

**A. WhatsApp first, SMS as a fallback later.** *Recommended.*
Cheapest per message, no DLT, no Android 17 problem (it is not SMS), and the
product already plans WhatsApp for updates (D-022), so the account is needed
regardless. Creators in Tamil Nadu are on WhatsApp. The gap is the person who
does not have it, or whose WhatsApp is on a different number — which is why
SMS follows rather than never arrives.

**B. SMS first, WhatsApp later.**
Reaches every phone with no app at all, which is the strongest argument
anyone can make here. But it needs DLT before a single code is delivered, it
needs SMS Retriever formatting to survive Android 17, and it costs more per
message.

**C. Both from day one, behind the one interface E1 already describes.**
The right end state and roughly twice the setup. Worth it only if we believe
WhatsApp-only would lock out enough creators to matter — which is a question
about the pilot's users, not about the technology, and you know that better
than I do.

**D. A managed login provider** (Truecaller one-tap, silent network
authentication). Already on the plan's open list. Cheaper for the user, and
Truecaller receives usage data, which needs a privacy review before it can be
considered.

## Recommended: A, with the SMS paperwork started in parallel

Pick **one BSP that carries both WhatsApp and SMS** so the second channel is a
configuration change and not a second integration. MSG91 and Gupshup both do,
and both were quoted above; I have not used either and am not endorsing one on
price alone.

Then:

1. Open the WhatsApp Business Account **registered in India** (constraint 3).
2. Get the authentication template approved — it is a fixed-format message,
   which is why it is cheap.
3. **Start DLT registration the same day**, even though SMS comes second. It
   is the only item with a lead time measured in weeks.
4. Build behind the one interface E1 describes, so the channel is a setting.

## What this unblocks

Real logins, therefore real users, therefore a pilot at all. Then E1, then C5
and the reminder work, and eventually E2, WhatsApp actions.

## What I cannot answer

- **The GST treatment and anything DPDP** — constraint 6. These are validation
  pack questions and I have quoted, not decided, them.
- **Which BSP is actually good.** Published rate cards are marketing. Two
  quotes from named companies, against our real volume, would beat this page.
- **Whether WhatsApp-only is enough for the pilot**, which is a question about
  the creators you intend to onboard.

→ **Approve A, B, C or D, and say whether to start the DLT paperwork now.**

## Sources

- [WhatsApp Business API Pricing in India 2026](https://myoperator.com/blog/whatsapp-business-api-pricing-india-2026)
- [WhatsApp API Pricing Explained (2026) — Authgear](https://www.authgear.com/post/whatsapp-api-pricing/)
- [WhatsApp Business API Pricing in India 2026 (Per Message)](https://chatmaxima.com/whatsapp-api-pricing/india/)
- [SMS OTP Pricing in India 2026 — Message Central](https://www.messagecentral.com/en-in/blog/sms-otp-pricing-india)
- [Transactional SMS Service India: Complete 2026 Guide (Pricing, DLT, OTP)](https://metareachmarketing.com/transactional-sms-service-india-complete-guide-2026.php)
- [Gupshup SMS Pricing India 2026](https://codingclave.com/blog/gupshup-sms-pricing-india-2026)
- [Behavior changes: Apps targeting Android 17 or higher — Android Developers](https://developer.android.com/about/versions/17/behavior-changes-17)
- [Android 17 second beta expands privacy controls — Help Net Security](https://www.helpnetsecurity.com/2026/02/27/android-17-beta-privacy-updates/)
