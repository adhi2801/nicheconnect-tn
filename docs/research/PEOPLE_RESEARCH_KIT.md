# The people research kit: ready to run, one session at a time

**For:** the founders, who are the only people who can run these sessions; this kit makes each one a single job with nothing to prepare but the people. **Version 1, 31 October 2026.** It turns the research `docs/standards/ux.md` section 2 requires (and every research file in this folder names as its open question) into scripts, numbers and a write-up format. Desk research cannot replace any of it.

**What it settles**, item by item in `docs/FRONTEND_COMPLETE.md`'s experience section: the five conversations per side, the five-second tests, the task tests, the colour test, and the sessions with people who use assistive technology.

---

## 1. Who, where and how many

- **Where:** Coimbatore first (D-071), in the pilot's three niches: food and cafés, fashion and textiles, beauty and salons (`docs/GO_TO_MARKET.md`). CODISSIA member meetings are the first route to brand owners.
- **Brand owners:** small and mid-size businesses that have paid, or thought about paying, a creator. **Creators:** people who post for brands now or want to, any size, on Android.
- **How many** (`ux.md` section 2): **conversations**, at least 5 per side before a flow is final; **five-second tests**, 10 brand owners and 10 creators per visual direction; **task tests**, at least 5 people per core journey, before it is built and again before launch. Five people find most of the usability problems in one round of task testing (Nielsen's long-standing guidance); first-impression tests need more people, which is why `ux.md` asks for ten.
- **Mixed on purpose:** different ages, at least two women per side, at least one person who uses a screen reader or large text.

## 2. What is never collected

- **No phone numbers, emails or contact details in any write-up**: a first name or a description is enough (`docs/research/README.md`; `docs/standards/legal.md` section 3).
- **No audio or video recording, and no photos of people**, until the validation pack confirms what consent wording recording needs (constraint 6: compliance is asked, never guessed). Notes only, taken by the second founder or written straight after.
- **Ask permission to take notes** at the start, in the person's language, and stop if they say no.

## 3. The conversation (before any screen is shown)

Use the Mom Test template in `docs/research/README.md` as it stands: their life, specific past events, no pitching, commitments over compliments. The questions that matter most for the frontend:
- "Show me how you found the last creator (or brand) you worked with." (Which apps, which screens they already trust.)
- "What did you look at to decide whether to trust them?"
- "What happened the last time a payment was late?" (The worst moment, `docs/research/INTERFACE_PSYCHOLOGY_2026.md` section 4.)
- "Which phone do you use for this?" (Check against `docs/research/REFERENCE_DEVICES_2026.md`.)

## 4. The five-second test

**Material:** the landing page's opening, Today for a creator, Today for a brand: each as a still on the person's own phone where possible, else the budget reference phone.

**Script:**
1. "I'll show you a screen for five seconds, then ask a few questions. There are no wrong answers; I'm testing the screen, not you."
2. Show it for exactly five seconds (a phone timer), then hide it.
3. Ask, in this order, without hints:
   - "What is this for?"
   - "Who is it for?"
   - "What would you do first?"
   - "Would you trust it with a deal worth ₹10,000? Why, or why not?"
   - "What do you remember seeing?"

**Pass mark, set before running:** at least 8 of 10 say what it is for and who it is for in their own words; at least 7 of 10 name the right first action. Below that, the screen changes before it is built.

## 5. The colour test

Both accents (burgundy and green) on the same three screens: the landing opening, a deal memo, a payment. Half the people see burgundy first.
- "Which would you trust with a payment? Why?"
- "On this screen, what does this colour mean?" (pointing at the accent, then at a state colour)
- "Is anything here hard to read?"

**Recorded:** the preference with the reason, and every misreading of a colour's meaning. A misread state colour counts more than a preference (`docs/research/COLOUR_PSYCHOLOGY_2026.md` sections 3 and 8).

## 6. The task tests

One journey per session, on a clickable prototype or the real build, on a phone. Tasks are given as goals, never as instructions:
- **Creator:** "Find a food campaign in Coimbatore that pays at least ₹5,000 and apply to it." "The brand sent you a deal. Check what you're agreeing to and accept it." "You finished the work. Send it." "The brand says it paid you. Check and confirm."
- **Brand:** "Post a campaign for three Instagram reels for your new product." "Pick the best applicant and offer them a deal." "Approve the work you received." "Mark two creators as paid."

**Measured per task** (`ux.md` section 2, HEART): completed or not, time taken, every point of confusion (where they hesitated, tapped the wrong thing, or asked a question), and one sentence on how it felt. **Target:** at least 90% completion and no critical confusion point; first campaign and first application each under five minutes.

**The moderator only says:** "What would you do next?", "What are you looking for?", "What did you expect to happen?" Never the answer.

## 7. Sessions with people who use assistive technology

At least one per side, on their own phone with their own settings (TalkBack, large text, high contrast). Same tasks as section 6. Every place they could not continue is a release-blocking bug (`docs/standards/frontend.md` section 6).

## 8. Writing it up

- One file per session in this folder, named as `docs/research/README.md` says (`YYYY-MM-DD-brand-<short name>.md` or `YYYY-MM-DD-creator-<short name>.md`), using its template plus, for tests, a table of tasks with completed, time, confusion points.
- **Within a day of the session**, while it is fresh.
- After each round, one summary file: what changes, which finish-line items it settles, and what it did not answer.

## 9. A round, in time

| Step | Time |
|---|---|
| Arrange 5 brand owners (one CODISSIA meeting) and 5 creators | About a week |
| Conversations, 30 minutes each | Two days |
| Five-second and colour tests, 10 minutes each, with 10 + 10 people | Two days |
| Task tests, 45 minutes each, 5 per journey | Per journey, as its prototype is ready |
| Write-ups and the round summary | A day |

## 10. Decision

| # | Decision | Recommended |
|---|---|---|
| 1 | Run the first round (conversations, five-second and colour tests) before the landing page and Today are built | Yes |

## Sources

`docs/standards/ux.md` section 2 (the numbers), `docs/research/README.md` (the Mom Test and the template), `docs/GO_TO_MARKET.md` (Coimbatore and CODISSIA). Five-second test practice: [Maze guide](https://maze.co/guides/ux-research/five-second-test/), [LogRocket](https://blog.logrocket.com/ux-design/step-by-step-guide-five-second-testing-ux) (read 31 October 2026).
