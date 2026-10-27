# Creator Passport (public page) — design spec

**Route:** `/c/:handle`
**Status:** Proposed. Design only; no frontend code exists or starts here (D-053).
**Contract checked against:** `docs/api/openapi.json` (`GET /api/v1/creators/by-handle/{handle}`), read 2 October 2026.
**Not reviewed by a second person.** Written in a session with one founder present (D-051).

---

## 1. Job of the page

A stranger opens a creator's link. In a few seconds they should know who this person is, what they make, where to see their work, and, if the creator chose to publish prices, what they ask. One next step: sign in to work with them.

Two audiences arrive here without being signed in:

| Visitor | Wants | Gets |
|---|---|---|
| A brand that was sent the link | To judge whether this creator fits | Identity, niches, channel links, optional asking prices |
| The creator, checking their own page | To see what the world sees | The same page, exactly as published |

## 2. What the page can and cannot show

The public endpoint is deliberately narrow. Anything not in the left column is a **backend request**, not a design decision.

| Section | API field | Rule |
|---|---|---|
| Name | `display_name` | Always |
| Handle | `handle` | Shown as `@handle`; lowercase, as returned |
| City | `city` | Always |
| Niches | `niches[]` | Chips; may be several |
| Content languages | `languages[]` | Plain list. This is what the creator makes content in, not the product's language (D-054) |
| Bio | `bio` (nullable) | Omit the block when null; no placeholder text |
| Member since | `member_since` (`2026-09`) | Render as "September 2026" |
| Channels | `channels[].platform`, `profile_url` | **Links only. Never a follower count** (D-042) |
| Asking prices | `packages[]` | Only when the creator published them (D-055). Empty list means "not published" and the section is hidden entirely |

**Cannot be shown on this page (needs sign-in, so belongs to the brand's view of a creator):**

| Wanted | Why not here |
|---|---|
| Follower counts, average views | Public page never carries them (D-042). They are self-reported and live in `GET /creators/{id}/media-kit` for signed-in brands |
| Delivery record | `GET /creators/{id}/delivery-record` needs a brand or the creator themself |
| Fair-rate range | `GET /rate-guidance` needs sign-in |
| "Verified" badge | No such field exists. KYC does not exist in the backend and the word "verified" is deliberately absent (D-055). Do not draw a badge |
| Phone, email, any contact detail | Never in the response, by design. Contact opens only after an accepted deal |

## 3. Layout

Designed at 360 px first (common Android width), then widened. One column on phones; on desktop a profile column beside the prices.

1. **Identity block:** display name, `@handle`, city, member-since.
2. **Niches and languages:** chips, then a single line of languages.
3. **Bio:** only if present. Plain text, line length near 65 characters.
4. **Channels:** one row per channel, each an external link ("Instagram", "YouTube") that opens the creator's own profile in a new tab. Show the host and path from `profile_url`, so the visitor sees where the link goes.
5. **Asking prices:** only if published. One card per package.
6. **Primary action:** "Sign in to work with {first name}". Sticky bar on phones, in the page flow on desktop.
7. **Secondary action:** copy page link.
8. **Footer line:** what the page is and is not (see section 5).

### Package card

| Element | Source | Format |
|---|---|---|
| Title | `title` | As written by the creator |
| Platform and format | `platform`, `format` | "Instagram · Reel". `other` renders as "Other" |
| Price | `price_paise`, `currency` | Divide by 100, Indian digit grouping: ₹8,000. Never show paise unless non-zero |
| Delivery | `delivery_days` | "Delivered in 3 days" |
| Usage rights | `usage_rights_days` | "Usage rights: 30 days". When null, omit the line (open question 4) |
| Description | `description` (nullable) | Omit when null |

Packages stay in the order the API returns them (the creator's order). Do not sort by price.

## 4. States

| State | Trigger | What the visitor sees | Primary action |
|---|---|---|---|
| Loading | Request in flight | Skeleton of the identity block, no spinner on its own | none |
| Full | 200, packages present | Everything above | Sign in to work with {first name} |
| No prices | 200, `packages` empty | Same page without the prices section. No "prices hidden" message: absence is the creator's choice | Same |
| Not found | 404 | "This page isn't available." One neutral message for a handle nobody has taken and for a creator who has not published, so the page cannot reveal who opted out (D-036). Never "this creator unpublished" | "Go to the home page" |
| Bad handle | 422 | Same screen as Not found | Same |
| Too many requests | 429 | "Lots of people are looking at this page right now. Try again in {Retry-After} seconds." | "Try again" (disabled until the wait ends) |
| Network or server error | fetch fails, 5xx | "We couldn't load this page. Check your connection and try again." Shows the request ID if the error body carries one | "Try again" |

Empty bio, empty niches, and a missing channel are not error states; the section is simply left out.

## 5. Copy rules

- English only (D-054). All strings in `messages/en.json`, none inside a component.
- Prices are labelled **"Asking prices, set by the creator. The fee for a deal is agreed in a deal memo."** They are not quotes and not agreed fees (D-056).
- No claim about money handling anywhere on this page. Payment status is a different screen.
- No word that implies checking: not "verified", "vetted", "trusted", "top". Channels are "links to the creator's own profiles".
- Buttons say what happens: "Sign in to work with Priya", "Copy page link", "Try again".

## 6. Accessibility and performance

- WCAG 2.2 AA, per `docs/standards/frontend.md` section 5 (to be re-read before build).
- Chips and channel links are real links or plain text, reachable by keyboard with a visible focus ring.
- External links announce that they open a new tab.
- Prices read correctly aloud: "8,000 rupees", not a symbol the screen reader skips.
- Works from 360 px to large desktop with no horizontal scroll. Respects `prefers-reduced-motion` and light/dark preference.
- The response carries an `ETag`; the client should send `If-None-Match` on revisit and treat 304 as "unchanged".
- **Measured, not claimed:** no performance or accessibility numbers are given here. They come from tools after a build exists.

## 7. Open questions for the backend and for founders

1. **Cache versus takedown.** The endpoint is cached for 5 minutes, but D-036 says unpublishing "takes the page down at once". Does an unpublish clear that cache? Not verified here; if it does not, a creator can be visible for up to 5 minutes after withdrawing consent, and the creator-facing copy must not say "immediately".
2. **Avatar or photo.** The contract has no image field. The design works without one (initials). Adding one is a backend request with its own consent and storage questions.
3. **Social previews.** A shared link will want a title and description. These can be built from `display_name`, `niches` and `city`, but who renders them (server or client) is a frontend decision for later.
4. **`usage_rights_days` null.** Does null mean "none included" or "not stated"? The spec omits the line; the API description does not say. Needs an answer before the wording is final.
5. **Product name.** The rename to Colyv and its domain (CLAUDE.md section 0, item 14) is not recorded as agreed here. The footer uses a placeholder.
6. **Sign-in return.** After "Sign in to work with…", should the brand come back to this page or go to the creator's brand-view page? Depends on the next screen.

## 8. Checks before anyone builds this

- [ ] Five or more conversations with brands and creators about this page, recorded in `docs/research/` (`ux.md` section 2).
- [ ] A contract test confirms the live response matches section 2 (D-042 already requires proof that no follower count appears).
- [ ] Open questions 1 and 4 answered.
