# UX Standard

**Status: for later**, with one exception. UI/UX design starts after the backend is complete (D-004). But **backend decisions that shape the experience** (error messages, status names, what data exists, how fast things respond) follow this file now.

---

## 1. Principles

1. **Trust first.** Brands and creators are risking money and reputation. Every screen makes clear who is who, what was agreed, and what happens next.
2. **Clear over clever.** Plain words, obvious actions, no mystery icons.
3. **Local by default.** Built for Tamil Nadu: Indian formats, familiar patterns such as WhatsApp for updates. **The product speaks English only** (D-054, 23 September 2026); it was to be bilingual, and that was dropped.
4. **Fast to value.** A brand posts a first campaign, and a creator applies to a first campaign, in under 5 minutes.
5. **Honest status.** Payment status shows exactly what's known: "Brand marked as paid on 12 Sep", never implying the platform moved or holds money.

## 2. Research and validation

- Before designing a flow: 5+ conversations with real target users (brands and creators separately), recorded in `docs/research/`.
- Every major flow is usability-tested with at least 5 users before it's built, and again before launch.
- Success is measured: task completion rate ≥ 90% and no critical confusion points on core journeys.

## 3. Core journeys (designed and tested first)

1. Creator sign-up and profile setup
2. Brand sign-up and first campaign post
3. Creator discovers and applies to a matching campaign
4. Brand reviews applicants and shortlists
5. Deal memo sent, reviewed and accepted by both sides
6. Brand marks the payment as sent; creator confirms receipt or raises a dispute

## 4. Design system

- One token-based design system for web and mobile: colour, typography, spacing scale, radii, elevation and motion.
- Components are documented with every state: default, hover/pressed, focus, disabled, loading, error.
- No one-off styles in screens. A missing component gets added to the system first.

## 5. Every screen

- Handles loading, empty (with a helpful next action), error (what happened and how to fix it) and success.
- Has one primary action.
- Works at 360 px wide (common Android width) up to large desktop.
- Meets the accessibility rules in `frontend.md` section 5.

## 6. Writing (microcopy)

- Buttons say what happens: "Send deal memo", not "Submit".
- Errors say what went wrong and how to fix it, with no blame and no technical jargon: "This campaign closed on 15 Sep. Browse open campaigns."
- Payment language describes facts only: "marked as paid", "confirmed received", "disputed". Never language suggesting the platform handles or protects money (see CLAUDE.md section 2).
- Copy is English and reviewed by a fluent speaker. It lives in message files (`messages/en.json`), never written into a component, so a second language stays possible later without a rewrite (D-054).

## 7. What this means for the backend now

- Error `code` values and messages from `backend.md` section 3 are written so the UI can show them directly.
- Status values have clear, user-meaningful names (`shortlisted`, `marked_paid_by_brand`), not internal jargon.
- Timestamps are returned for every state change so the UI can show "what happened when".
- List endpoints support the filters the core journeys need, and meet the performance budgets.
- Nothing in the API forces the UI to make many calls to render one screen. If it does, raise it.
