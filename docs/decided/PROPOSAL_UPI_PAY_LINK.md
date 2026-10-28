# The UPI pay link (item 32, D-085)

**Built 10 October 2026, off until the validation pack supplies the consent notice.** Approved by Adhi as item 32 of `docs/BILLION_DOLLAR_GAP.md` ("approve all", 8 October), which named its gate as a founder decision on storing UPI IDs, and confirmed on 10 October ("carry on working next") after the plan to store them was put to him.

## What it does

Today a brand pays a creator by copying an amount and a UPI ID by hand: the most error-prone step in a deal. Now:

1. The creator gives their UPI ID once, after reading a notice, with explicit consent (`PUT /api/v1/creators/me/upi`). They can remove it at any time (`DELETE`), even while adding one is closed.
2. When the work is approved and the payment is open, the brand on that deal asks for the pay details (`GET /api/v1/deal-memos/{id}/payment/pay-details`). It gets the creator's UPI ID, the amount and a `upi://pay` link, NPCI's own deep link.
3. The brand's own UPI app opens with everything filled in. It shows the payee's name **as their bank holds it**, and the brand approves with its PIN.
4. The brand marks the payment sent with the UPI reference, as before (D-027).

**The money goes from the brand's bank to the creator's bank. It never passes through us, and nothing here could make it** (constraint 1). This is why the RBI's payment-aggregator rules do not reach us (`docs/standards/legal.md` section 3.9).

## Choices

| Choice | Why |
|---|---|
| A table of its own, `creator_upi`, not a column on `creator` | Search, matching and the embedding text read `creator`; a UPI ID never comes near them (constraint 2) |
| **Phone-number UPI IDs refused**, by the API and by a database check | `9876543210@ybl` would show a brand the creator's phone number, which we never share. NPCI's privacy direction of September 2026 asks UPI apps to mask such IDs and to offer chosen names, so every creator can make one |
| **No link above ₹1 lakh** | UPI between people allows ₹1 lakh from one bank account in 24 hours (Google Pay's help, read 10 October 2026). Above it the transfer would fail at the bank, so the answer says `above_upi_limit` and the brand pays by bank transfer |
| Only the person-to-person fields: `pa`, `pn`, `am`, `cu`, `tn` | `tr` and `mc` are merchant fields, and a creator is not a registered merchant |
| Shown **only to the brand on the deal, only while the payment is open** | Collect only what is needed, show it only when it is needed. Once marked paid, the ID is not shown again |
| Consent with a notice version, renewed on every change, and refused if the creator read an older notice | DPDP Rule 3 and `security.md` section 7: consent is an event, tied to what was read |
| **Off until the notice exists** (`UPI_NOTICE_VERSION` unset → 503 `upi_not_open_yet`) | The notice's wording comes from the validation pack (constraint 6). Switching it on is setting one variable |
| No encryption in the application beyond RDS's encryption at rest | A UPI ID is shared to be paid and printed on shop QR codes; the risk is moderate. App-level encryption would need a key service on every read. Revisit if the threat changes |

## Threat model (`security.md` section 4)

| STRIDE | Who could abuse it, and how | What stops it | Proven by |
|---|---|---|---|
| Spoofing | Someone sets a UPI ID on another creator's profile | Only the signed-in creator, under `/me`, sets their own | Brand gets 403; no route takes another creator's id |
| Tampering | A taken-over creator account swaps in the attacker's UPI ID just before payment | `upi_id_set_at`, and `upi_id_changed_recently` for 24 hours, so the app warns the brand. The brand's UPI app shows the bank's name for the payee before the PIN, and the app tells the brand to check it. **The last line is the bank's name, not ours**: a notification to the creator would reach the attacker too while WhatsApp alerts (E1) are not built | `test_a_fresh_upi_id_is_flagged_to_the_brand` |
| Repudiation | A creator says they never gave that UPI ID | `consented_at` and `notice_version` on the row; the export shows them | `test_changing_it_gives_consent_again`, the export test |
| Information disclosure | Another brand, or anyone, reads a creator's UPI ID; a phone number leaks through it | `BrandMemo` (404 for any other brand); only while the payment is open; phone-number IDs refused twice; a lower rate limit; never logged; Sentry scrubs `upi`/`upi_id` (D-074) | `test_another_brand_cannot_see_the_upi_id`, `test_once_marked_paid…`, the phone tests, the database tests |
| Denial of service | Hammering pay details to harvest IDs | 20 a minute per account, below the 60 for other reads; and each answer is one deal's own creator | `test_pay_details_are_rate_limited_harder_than_other_reads` |
| Elevation of privilege | A creator reading pay details as if a brand | `BrandMemo` requires a brand profile | `test_the_creator_does_not_read_pay_details` |

## Owed, outside the code

- **The notice wording** and its version, from the validation pack; then set `UPI_NOTICE_VERSION`.
- **Try the link on real phones** with Google Pay, PhonePe, Paytm and BHIM before launch. Some apps add their own risk checks to links that pay people rather than merchants, and only a real payment shows how each behaves. Until then this is built and tested in code, not proven in the field.
