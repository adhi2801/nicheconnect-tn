# Telling creators when a brand changes hands (item 13, D-151)

**Status: Approved by Adhi on 4 November 2026 (D-151): "Yes, as the next build (Recommended)", then "don't ask me, do it yourself". Built the same day on `feature/hand-over-notice`. Not reviewed by Erode Harish (D-051).** Kept as the reasoning behind the build.

## 1. Why

Since D-148 and D-150 a brand's owner can hand the brand to a member of its team. The deals, the payment record and the blocks go with the brand, so nothing a creator agreed changes. But the person holding the business's account does, and a creator in the middle of a deal had no way to know. Someone owed money, or waiting on an approval, should hear that the account on the other side has a new holder, from us, at once, rather than find out when a stranger answers.

## 2. What is built

- **One notice, `brand_changed_hands`, to each creator with a deal still unfinished with the brand** at the moment it is handed over: unfinished as account deletion counts it (`deal_memo.unfinished`: not finished, declined or cancelled, or a dispute open, or money still owed, D-122, D-147). One notice per creator, however many deals; it says how many.
- **What it carries:** the brand's id and name, the number of the creator's unfinished deals with it, and the new owner, by the membership they held until that moment. The first name shown is read from that membership when the notice is read (as D-150 does for a member's act), so erasing that person's account erases the name from the notice too; never a phone number.
- **Nobody can mute it**: who holds the business account on a deal in progress is the kind of change a muted alert would hide (`URGENT_TYPES`, beside the team notices). Creators with only finished deals are not told: nothing of theirs is open.
- **In the same transaction as the hand-over**, so a hand-over can never happen without its notices, and a refused one sends none.

## 3. The twelve dimensions (D-098, D-139)

| Dimension | |
|---|---|
| Quality | API tests: told with an unfinished deal; not told with only finished ones; one notice for two deals, counting both; the name read live and gone with the membership; a refused hand-over tells nobody. Each rule broken on purpose and caught. The migration's round trip in CI |
| Novelty | Upwork, the strongest comparable, lets a client company's owner transfer ownership to an admin from Account settings and emails a confirmation; its help page describes no notice to the freelancers on the company's contracts ([Edit your company information](https://support.upwork.com/hc/en-us/articles/211063348-Edit-Your-Company-Information), read 4 November 2026). Ours tells every creator with something open, at once, in a notice they cannot mute, naming who now holds the account |
| Architecture | `me.team_service.hand_over` (layer 7) reads `deal_memo.unfinished` (layer 4) and records through `notifications` (layer 3): only downward imports. `ARCHITECTURE_SCALE.md` unchanged |
| Research | Unfinished as D-122 and D-147 define it, so one rule decides both "held from deletion" and "told of a hand-over"; unmutable as D-107's alerts are |
| Security | Spoofing: only a real hand-over sends it (a write under the brand's lock, after the owner's code and week-old login). Tampering: the creator cannot change it. Repudiation: the team's own rows record it (the new owner's membership ended, the former owner's begun, at the same moment), and each notice its time. Disclosure: a first name and the brand's public name, nothing else. Denial of service: hand-overs are 5 a minute and 10 a day per owner; one notice per creator. Elevation: none: a notice grants nothing |
| Privacy & law | The new owner's first name, already shown to creators beside the brand when they act (D-148); read live, so erased with them (legal.md 3.1). No consent beyond joining the team, which the D-148 Confirm item already asks the validation pack |
| Trust & safety | Stops a quiet swap: a brand cannot change hands mid-deal without the creator knowing. A creator cannot use it against anyone: they only receive it |
| Performance | The hand-over gains the unfinished-deal check (four queries at most), one query for the creators, and one statement writing every creator's notice, however many (`notifications.record_many`; the ORM would write one per row, since the database makes the ids). The same batching now writes a brand's team copies (D-150). Proven by statement counts; p95 in `docs/PERFORMANCE.md` |
| Design | One notice type for the creator's list; its wording renders from `brand_name`, `unfinished_deals` and `new_owner_first_name`. No new call |
| Business | Keeps the promise the marketplace rests on: the record follows the brand, and the creator always knows who they deal with. Costs nothing per notice (in-app) |
| Reliability | No outside call; one transaction, so all or nothing. A creator erased since gets nothing (no account) |
| Maintainability | One new notice type, an additive contract change. The downgrade refuses while any of these notices exist (each is a record that a creator was told), otherwise reverses the check |

## 4. Rollback

The code is one branch. The migration only widens the allowed notification types; its downgrade refuses while any `brand_changed_hands` notice exists, and otherwise narrows the check back.
