# UX Standard

Applies to research, flows, the design system, copy and accessibility, and to **backend choices that shape the experience** (error messages, status names, what data exists, how fast things respond), which follow this file now. The bar is `CLAUDE.md` section 7.0.

**Timing (D-053, amending D-004):** research, flows and the design system may be worked on now. No frontend code starts until the backend is complete. Designs are checked against `docs/api/openapi.json`: a screen that needs a field the API does not answer is a backend request, not a frontend decision.

---

## 1. Principles

1. **Trust first.** Brands and creators risk money and reputation. Every screen makes clear who is who, what was agreed, what happens next, and whose move it is (the deal's `stage` and `waiting_on`, D-076).
2. **Facts, never verdicts.** Records show what happened with its date and source ("self-reported, as of 3 Oct", "marked as paid by the brand on 12 Oct"); "not enough to say" is a designed state, never a zero (D-027, D-038).
3. **Clear over clever.** Plain words, obvious actions, no mystery icons.
4. **Local by default.** Built for Tamil Nadu: Indian formats (₹, lakh and crore, DD Mon), the patterns people already use, such as WhatsApp. English only (D-054); every string in a message catalogue so a second language needs no rewrite.
5. **Fast to value.** A brand posts a first campaign, and a creator applies to a first campaign, in under 5 minutes.
6. **Calm, and persuasive only with the truth.** None of the thirteen dark patterns the Consumer Protection Authority bans: no fake urgency, hidden costs, confirm-shaming or nagging. The growth levers we do use (real social proof, real deadlines, honest defaults) and the line each must not cross are in `docs/standards/legal.md` section 3.5. Night-time pings wait for morning unless a deadline is running (D-079).
7. **Honest about money.** Payment status says what each side reported, never implying the platform moved or holds money (constraint 1).
8. **Safe by design.** Nobody can be scammed through what we built: money requests and contact details are flagged where they appear, links show where they go, and anyone can block anyone (`docs/standards/trust-and-safety.md` section 5).

The design direction (Modern Tamil, DESIGN_DIRECTION.md on the branch docs/design-direction) is proposed and awaits both founders.

## 2. Research and validation

- Before designing a flow: at least 5 conversations with real target users (brands and creators separately), notes in `docs/research/`, using the Mom Test template in `docs/research/README.md`.
- **The five-second test** on any visual direction: what is this, and would you trust it with a deal? 10 brand owners and 10 creators.
- Every core journey is usability-tested with at least 5 users before it is built, and again before launch.
- **Measured success** (Google's HEART framework, on the core journeys):
  - task completion of at least 90%;
  - no critical confusion point;
  - time to first campaign and first application under 5 minutes;
  - after launch: retention, repeat deals, and payment confirmation time.

## 3. Core journeys (designed and tested first)

1. Creator sign-up and profile, Passport published by choice
2. Brand sign-up and first campaign
3. Creator finds and applies to a matching campaign
4. Brand reviews applicants: Passport, delivery record, fair-rate range, response times
5. Deal memo sent, revised and accepted
6. Work submitted, reviewed (or approved by the clock), with the approval window always visible
7. Brand marks the payment as sent (by UPI pay link where it can, D-085); creator confirms receipt or raises a dispute
8. Brand invites a creator from search, and "work together again" on a finished deal (D-084); the creator accepts or declines with a reason
9. Either side blocks or reports the other, from anything they sent
10. Sign-up confirms the person is 18 or over (D-086), asking for the date of birth once and saying it is not kept

## 4. Design system

- One token source (W3C Design Tokens format) for web and both apps: colour, type, spacing, radii, elevation, motion (`frontend.md` section 8).
- Every component documented in every state: default, pressed, focus, disabled, loading, error, empty.
- No one-off styles. A missing component is added to the system first.

## 5. Every screen

- Handles loading (skeleton within 100 ms), empty (with a helpful next action), error (what happened and how to fix it), success, and **"not enough to say"** where a figure can be null.
- Has one primary action.
- Works from 360 px wide to large desktop, at 200% text size.
- Meets WCAG 2.2 AA (`frontend.md` section 6). Motion respects "reduce motion".
- Shows the 429 wait time and keeps what the person typed on any error.
- **Shows every `text_flags` warning beside the text it is about**, never hides the text, and shows the author the same warning before sending (item 60).
- **Never turns another person's text into links.** A link field shows its host before it opens.
- Shows a record's figures beside **how many different partners they rest on** (`distinct_brands`, `distinct_creators`, item 61), so twelve deals with one partner never look like twelve across nine.

## 6. Writing (microcopy)

- Buttons say what happens: "Send deal memo", not "Submit".
- Errors say what went wrong and how to fix it, without blame or jargon: "This campaign closed on 15 Sep. Browse open campaigns."
- Every date is unambiguous: "due 12 Oct", "approves itself at midnight on 9 Oct".
- Payment language states facts only: "marked as paid", "confirmed received", "disputed". The four banned money words never appear (a test enforces it).
- **Safety lines, at the moment they matter**, in these words or better:
  - "You never pay to get a deal."
  - "You never enter your PIN to receive money."
  - "Check your own bank app, not a screenshot."
  - "Check the name your UPI app shows before you pay."
  - "We never ask for your login code."
- Copy lives in message files, reviewed by a fluent speaker.

## 7. What this means for the backend now

- Error `code` values and messages (`backend.md` section 3) are written so a screen can show them directly.
- Status values are user-meaningful (`shortlisted`, `awaiting_confirmation`), not internal jargon.
- Every state change has a timestamp, so a screen can show "what happened when".
- **A screen needs at most two calls.** If it needs more, the backend adds what is missing (the deal stage, the payments list and the campaign summary were built this way, D-075 and D-076).
- Every list meets the performance budgets and supports the filters the core journeys need.
