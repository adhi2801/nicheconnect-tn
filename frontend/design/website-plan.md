# The website: every page as structure, with slots for the designs

**Status: Approved by Harish, 27 November 2026 (D-202). Home is built first and waits for his approval; the rest is not built yet.** Harish's decisions behind it are HD-001 to HD-006 in `frontend/design/DESIGN_DECISIONS.md`.

## 1. What is being built

Every page of the website, public and signed-in, built now as **structure**: what each page shows, in what order, its layout at phone and laptop widths, and every state (loading, empty, error, done). The structure is drawn in a calm neutral look (HD-004). Each place a planned design goes (the temple scene, kolam, the boarding pass, illustrations, the logo) is a **design slot**: a reserved space whose size is fixed now. When a design is dropped into a slot later, nothing outside that space moves or changes, and a test proves it (section 3).

The bar is the one `docs/standards/frontend.md` section 8a already names: Stripe, Linear, Vercel, Mercury and Apple. Each page is set beside its named benchmark before Harish sees it.

## 2. Every page

**Public** (anyone, no sign-in):

| Route | Page | Its job | Design slots |
|---|---|---|---|
| `/` | Home | Say what Colyv is and who it is for in one screen; show how a deal goes, the payment record, trust; two ways in (creator, brand) | `home.hero` (the temple scene), `home.journey`, `section.divider` |
| `/creators` | For creators | Why a creator should join: real pay shown up front, a record that travels, no middleman on money | `creators.hero` |
| `/brands` | For brands | Why a brand should post: creators by city and niche, clear deals, a payment record that builds trust | `brands.hero` |
| `/how-it-works` | How it works | The five steps of a deal, from campaign to record | `deal.pass` (the boarding pass) |
| `/trust` | Trust and safety | What is checked, what is recorded, how to report or block, what Colyv never does with money | `section.divider` |
| `/about` | About | Who is building it and why Tamil Nadu | `about.portrait` |
| `/help` | Help | Questions and answers | none |
| `/legal/privacy`, `/legal/terms` | Privacy, Terms | Structure only. The words come from the validation pack (CLAUDE.md constraint 6) and stay "Being written" until then | none |
| `/c/{handle}` | Public Passport | A creator's public page; one action: sign in to work with them | `passport.cover` |
| `/sign-in` | Sign in | Number, code, done | `signin.art` |
| `/pilot` | Join the pilot | The form; no endpoint yet (request R4), so it says so | none |
| (any) | Not found, Something went wrong, Offline | Calm, with one way back | `empty.calm` (kolam) |

**Signed in, both roles:** onboarding (creator, 2 steps) and brand setup; Today; Inbox; Deals; a deal's pass (`/app/deals/{id}`, holding the memo, the work, the payment, any dispute and the record as sections, with each action in a sheet); Account.

**Creator:** Discover; a campaign and Apply; My applications; Me (Passport, About you, Channels, Rate card).

**Brand:** Campaigns; New campaign (4 steps); a campaign's applicants; a creator's profile; suggested creators; write and send a memo; review work; pay creators; brand profile.

About 42 pages in all. Their contents come from `frontend/design/screen-plan.md` section 6, which stays the spec; only the look and the shell change.

**The shells.** Public pages: a top bar (logo slot, four links, Sign in) and a footer. Signed-in pages: a sidebar on laptops, and on phones a top bar with a menu button that opens the navigation as a full-screen sheet. **No app-style tab bar** (HD-003).

## 3. How the design slots work

1. **One list of slots.** `src/design/slots.ts` names every slot, its purpose, and its size at each width (an aspect ratio or a height). A page writes `<DesignSlot id="home.hero" />` and never sizes it itself, so a slot cannot grow by accident.
2. **One place designs plug in.** `src/design/registry.ts` maps a slot to its design. Today it is empty. Adding a design is one line there plus the design's own folder under `src/design/art/`. No page file changes.
3. **A design cannot reach outside its slot.** The slot's box is fixed (CSS `contain: strict`, `isolation: isolate`, clipped overflow), so nothing it draws can push or cover the page. A design's styles live in its own CSS module, and a check fails the build if a design file writes a global style.
4. **A design cannot slow other pages.** It loads only on the page that shows it, and only when its slot comes near the screen. The existing Lighthouse ratchet and download-size checks still judge every page (D-198). With motion off, or JavaScript off, the slot shows its still image or placeholder.
5. **While empty.** On the live site an empty slot is a quiet neutral surface, so nothing looks broken. Locally, `?slots=1` on any page outlines every slot with its name and size, so Harish can see where each design will go.
6. **The look lives in one file.** Every colour, font, size, space, radius, shadow and motion comes from `frontend/tokens/tokens.json`. A check fails the build if a component writes a raw colour. The neutral look is one theme there. The warm heritage look will be a second theme, switched for the whole site at once.
7. **Proven, not claimed.** A browser test fills every slot with a deliberately loud test design (bright colour, oversized text, an attempt at a global style) and checks that every pixel outside the slots, and the position of every other element, is unchanged at phone and laptop widths. This is HD-002, written as a test. It is broken on purpose (a slot without containment) to show it fails.

## 4. The look (HD-004, refined by HD-007 on 28 November 2026)

Harish's reference is the COREHR dashboard (saved in the session's images folder). Every page, public and signed-in, follows it:

- A soft tint ground (pale mint at the top left, cream at the top right, fading to off-white), with white rounded cards (32 px corners) in a bento grid on it.
- Near-black for the one main button and the current menu item; lime for highlights (tags, number badges, round arrow buttons, check marks, status tags); sage green for one tinted card per page and for charts. Lime is only ever a fill behind dark text, never text.
- A pill-shaped top menu (the current page in black); a logo in an outlined pill (the logo slot).
- Inter, with light-weight headings and big figures (`type-figure`, weight 300) and small quiet labels. Muted text is a little darker than the reference's so body text keeps 7:1.
- Dashboard parts to come with Today: the dotted bar chart, the tick-mark ring, the split progress bar, round-check lists, tables with status pills. The reference's photo card becomes a design slot (D-142: nothing is a photograph); people show as initials.
- Motion: one easing, short durations, nothing loops; everything respects reduced motion.
- The `/design` catalogue is redone in this look so every page is built from parts already seen and approved.

## 5. Order, with your yes at each step (HD-006)

1. **Home**, with the public shell, the slot system, the neutral tokens and the slot-isolation test. This is the first thing shown, because it decides the look for every other page.
2. The other public pages, one at a time.
3. Sign in, then the signed-in shell.
4. The creator pages, reusing the working code from D-200 (onboarding, Discover, campaign and Apply, My applications), then Today, Inbox, Deals and the pass, Me.
5. The brand pages.

Each page is shown at phone and laptop widths, light theme, against the real backend for signed-in pages, and waits for a yes or changes before the next one starts.

## 6. What stays from the creator journey (HD-005)

Kept as they are: the rules (`src/lib/onboarding.ts`, `campaigns.ts`, `applications.ts`, `safety.ts`, `drafts.ts`, `writes.ts`), the data hooks (`queries.ts`, `mutations.ts`), the session, the API client, the message files, and the 87 unit tests. Rebuilt: the components under `src/components/` and the page layouts. The 137 browser tests that check behaviour are kept and re-pointed at the new markup where it changes.

The work goes on a new branch, `feature/website-structure`, starting from `feature/creator-apply-journey` (`5e32ee9`), so that branch is untouched. The creator journey's pull request is not opened separately; it goes with the first approved pages.

## 7. The twelve dimensions

- **Quality:** every page's states screenshotted and checked by eye before showing; the slot-isolation test; the existing accessibility checks (WCAG 2.2 AA, 7:1 body text) in light and dark at both widths; the raw-colour check; every rule broken on purpose and seen to fail; an independent review before merge.
- **Novelty:** the strongest competitor's site is compared side by side with Home when it is shown (not yet done, so no claim is made here). What is ours by design: one look across the public site and the product, with heritage design added in fixed places that a test proves cannot break it.
- **Architecture:** frontend only. Adds `src/design/` (slots, registry, art) and a neutral theme in `tokens.json`; replaces the shells. No backend change; `ARCHITECTURE_SCALE.md` unchanged.
- **Research:** the benchmarks are the ones `frontend.md` section 8a names; each page's benchmark is named, with the date it was looked at, when the page is shown.
- **Security:** no change to sign-in, tokens or what anyone may see. Designs are our own code, never fetched from elsewhere; external scripts stay blocked by the existing content security policy.
- **Privacy and law:** no new personal data. Privacy and Terms pages hold structure only until the validation pack gives the words (constraint 6). No invented proof on public pages: no testimonials, logos or user counts; sample data is labelled.
- **Trust and safety:** report and block stay one tap from anything a brand sent (D-201). Public pages never promise anything about money that constraint 1 forbids.
- **Performance:** public pages stay within the Lighthouse ratchet and the 150 KB download budget; designs load lazily and only on their pages. The signed-in pages' current JavaScript (about 215 KB compressed against a 150 KB budget) is measured again under the new shell and reported.
- **Design:** this document is the design plan; each page's layout is shown before the next is built.
- **Business:** a launch-ready website sooner, with the visual design able to arrive page by page without rework. Cost: the creator screens' look is rebuilt.
- **Reliability:** a design that fails to load leaves its placeholder; the rest of the page is unaffected. No new dependency or service.
- **Maintainability:** one slot list, one registry, one token file. A design is added or removed in one line, and the isolation test guards every change.

## 8. Gates, risks and how to undo it

- **Gates:** scope (rebuilding the look of built screens), architecture (the `src/design/` folder and new shells), the token rule change (HD-004, which Adhi should hear about). No new dependency, no backend change, no CI change.
- **Risks:** about 42 pages is a lot of work, and one page at a time with approval is slower than a batch, which is the trade HD-006 chose. Brand pages depend on backend gaps already listed (R2 and others in `docs/PROPOSAL_FRONTEND_API_REQUESTS.md`). The legal pages wait on the validation pack.
- **Undo:** everything is on its own branch; `feature/creator-apply-journey` stays as it is.

## 9. Open questions, for later pages

- A Pricing page: there is no pricing decision on record, so none is planned until the founders make one.
- Contact details for the footer and Help: none are on record.
- The logo: the designer's logo is pending, so the logo is itself a slot (`brand.mark`), shown as the word "Colyv" until then.
