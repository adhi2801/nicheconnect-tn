# Automated review findings, and what became of each

**Checked against the code on 4 October 2026.** Two review bots are connected to this repository, ChatGPT Codex and CodeRabbit, and their comments had never been answered. This file is the answer to every one of them, with the evidence. Nothing here was marked done because it was assigned: each was checked against the code, and every bug was first reproduced by a failing test.

## The finding behind the findings: most of the code was never reviewed by a bot

- **Codex ran out of credits from PR #12 on.** It reviewed PRs #4, #5, #6, #7, #9, #10, #11 and the first commits of #34 and #35, and posted "out of credits" on 28 others: everything from 21 September onward, including payments, the deal record, the admin side, proof files and results from proof.
- **CodeRabbit has never reviewed anything.** Each of its 40 comments says the repository "does not receive automatic reviews because it has fewer than 10 stars"; a review must be triggered by hand.
- No second founder has reviewed that code either (D-051; D-069 relays approval of decisions, not a reading of the code).

So the code since 21 September has had one reader: the session that wrote it. See "What next" at the end.

## The 22 findings

**Status words:** *Fixed now* (reproduced by a failing test, then fixed, this time); *Already fixed* (fixed earlier, with the commit and a passing test); *Docs fixed*; *Needs a decision*.

### High (P1)

| # | PR | Finding | Status | Evidence |
|---|---|---|---|---|
| 2 | #5 | One account could be linked as both a brand and a creator, or as the wrong role | Already fixed | `fe07f52` (18 Sep, D-014): each profile references the account by id **and** role; 30 tests, one proving a raw SQL insert cannot bypass it |
| 5 | #7 | A failed login-code send could log the phone and the code | Already fixed | `5208683` (17 Sep): only the error's type is logged; a test makes the provider's error contain both and checks neither reaches the log |
| 7 | #9 | A brand could request changes forever, restarting the approval clock each time | **Fixed now** | `f978a3a`. The reviewer suggested refusing a second request; **D-025 allows it but gives no more time**, so that is what is built: only the first request restarts the clock |
| 12 | #10 | `CLAUDE.md` listed `campaigns` as approved before Erode Harish confirmed D-016 | Already resolved | D-016 records his confirmation on 19 September |
| 14 | #11 | Two closes of one dispute at once both succeeded, last outcome silently winning | **Fixed now** | `77dd21e`: four simultaneous closes left four "closed" events, 5 runs in 5; now one wins and three get a conflict |
| 15 | #11 | Evidence could be added after a dispute closed | **Fixed now** | `77dd21e`: an entry followed the close in the deal record's sequence, 5 runs in 5; no longer |
| 19 | #34 | Proof uploads were not reachable from the API | Already fixed | `833ea7c` (30 Sep): the upload and submit-with-files endpoints, the very next commit after the one reviewed |

### Medium (P2)

| # | PR | Finding | Status | Evidence |
|---|---|---|---|---|
| 1 | #4 | Tests on an unmigrated database fail with UndefinedTable and no explanation | **Fixed now** | `ded827e`: pytest checks the migration first and stops with one line naming the fix; proved by migrating one step down |
| 3 | #6 | D-004 still says `Approved by: <founder name>` | Resolved | D-073: Adhi approved it (4 Oct); the log is append-only, so the new entry completes the old one |
| 4 | #6 | "Every read checks the caller owns the object" would forbid legitimate shared reads | Docs fixed | `ded827e`: `CLAUDE.md` now says the owner, a party, or public by design |
| 6 | #7 | The per-phone limit on wrong guesses could be dodged across IP addresses | Already fixed | D-018: guesses are counted per phone in the database, whatever the address; 4 tests |
| 8 | #9 | The approval deadline counted 24-hour blocks, not calendar days ending at midnight IST | **Fixed now** | `f978a3a`, as D-025 requires; 23:00 and 00:30 submissions now share a deadline |
| 9 | #9 | Two simultaneous memo creations: one got a 500 | **Fixed now** | `a3528fe`: three of four raised a raw IntegrityError, 3 runs in 3; now one memo and clean conflicts |
| 10 | #9 | Proof can be submitted without the ad-disclosure confirmation when the memo requires it | **Needs a decision** | Working as D-024 decided ("the system records the creator's confirmation, it does not judge it"); the record shows the creator's "no". Blocking submission instead would be a new rule |
| 11 | #9 | Two simultaneous proof submissions: one got a 500 | **Fixed now** | `a3528fe`, same pattern as #9 |
| 13 | #10 | `assign-task` measured progress against a phase plan the repository does not hold | Docs fixed | `ded827e`: it uses the backlog's phases A to E and `docs/BACKEND_COMPLETE.md` |
| 16 | #11 | Retrying a lost approval returned 409 instead of the original success | Already fixed | D-040 (`f047a6e`): a test retries an approval with one key and gets the original 200; another checks every write accepts a key |
| 17 | #35 | The handle check cannot judge a YouTube `/channel/` link | Already handled; docs fixed | The check is left empty, never failed; `ded827e` adds the test and states the rule in `docs/decided/PROPOSAL_PROOF_RESULTS.md` |
| 18 | #35 | The post-date check has no defined end | Already handled; docs fixed | It is on or after acceptance and not in the future, in IST; the optional due date is not a bound. Stated in the proposal, `ded827e` |
| 20 | #34 | A finished upload never submitted would stay in the bucket forever | Already fixed | `8ab4f0b` (1 Oct): the bucket expires anything in `proof-files/incoming/` after a day |
| 21 | #34 | A creator at nine packages adding two at once ended with eleven | **Fixed now** | `bc34345`: four simultaneous adds gave thirteen packages, 3 runs in 3; now exactly ten |
| 22 | #34 | Two first saves of a channel at once: one got a 500 | **Fixed now** | `bc34345`: three of four raised a raw IntegrityError; now all four succeed as one row |

**Totals:** 10 fixed now, 9 already fixed or resolved, 2 documentation fixes, 1 for a decision; and 5 more races found by the audit below, all fixed.

## How the race conditions were proved

Six of the ten fixes are races: two requests at once both pass a check before either writes. A race test that passes proves nothing if the requests never overlapped, and here they mostly did not: each request finished in a few milliseconds. So each test holds the moment between check and write open (0.1 to 0.4 seconds, as a slow network or a busy database would in production), which makes the bad ordering certain. Every one failed every run on the old code before its fix, and passes every run after. All six fixes are the same: lock the parent row and read it again before the check.

## Beyond the 22: the same bug, found everywhere it was

Every race above was one pattern: check, then write, with no lock. Rather than wait for a reviewer to find each case, every service function that refuses a move ("already", "limit", "conflict") was listed with whether it locks first. Of 21, these were unsafe, and all are now fixed (`db.refresh(..., with_for_update=True)` on just the attributes each check reads, so a caller's unsaved changes are never discarded):

| Where | What two requests at once could do | Proof |
|---|---|---|
| Proof: approve vs. ask for changes | Both succeed: **a payment clock running on proof sent back** | Test fails every run on the old code; passes with the fix |
| Memo: accept vs. decline | Both succeed; the last status silently wins | Same |
| Application: accept vs. reject | Both succeed | Same |
| Campaign: close vs. cancel | Both succeed | Same |
| A deal's unfinished uploads (cap 20) | Four at once from 19 left 23 | Same |

Checked and found safe: applying to a campaign twice (the unique rule's error is already caught and returned as "already applied"); opening a dispute twice (an existing concurrency test proves it); an admin suspending an account twice (the account is already read with its row locked). Every other listed function already locked first.

## What next

1. **The decision above** (#10). #3 was answered by D-073.
2. **A review of everything since 21 September**, which no bot and no second founder has read: trigger CodeRabbit by hand on the open pull request (a comment `@coderabbitai review`), and run a full review in a session. The check-then-write pattern has now been searched for across the whole codebase (above); other kinds of bug have not.
3. **Codex's credits** are a founder's decision: restore them, or rely on the other two.

## Still true on 10 October 2026

Nothing in "What next" has happened. The unreviewed code has grown, with only the session that wrote it as its reader:
- adults only, availability, invitations and repeat deals;
- the UPI pay link;
- blocking, daily ceilings, the link and text checks;
- the legal and trust-and-safety standards.

What has caught real bugs since is the automated net:
- **CI**, run on a fresh database: a block filter that read every campaign's brand (`docs/standards/testing.md` section 2);
- **mutation testing by hand**: two text-flag guards that each hid the other;
- **the new document check**: a decision cited eleven times and never made, and a file `CLAUDE.md` required that never existed.

None of that is a second reader. Step 2 above is still the most valuable review there is: comment `@coderabbitai review` on the open pull request, and have Erode Harish read it before it merges.
