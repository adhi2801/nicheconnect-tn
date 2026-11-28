# Harish's design decisions

**What this file is.** The frontend design decisions Erode Harish has made, in his own words where he gave them, newest last. Nothing here is softened or "improved" after he said it. A decision is changed only by a newer entry from him. Where one of his decisions meets an earlier rule (a `docs/DECISIONS.md` entry, `frontend/tokens/tokens.json`, `docs/standards/frontend.md`), the entry names the rule so nobody has to guess which one stands.

Started 27 November 2026. Earlier choices he made in sessions before this file existed are in the session notes, not here, and are added only when he confirms them again.

---

## HD-001: Launch the website first, at billion-dollar quality

- Date: 2026-11-27
- His words: "first our target is to launch the website and we gonna work on the website for now....and the app looks like it is made for some 1000-3000 rupees.....i want our website to look like bilion dollor website"
- What it means: the website is built and launched before the phone apps. The signed-in screens built on 25 and 26 November (D-200) do not meet his bar for the look.

## HD-002: Structure first, design later, in slots that change nothing else

- Date: 2026-11-27
- His words: "first we will do every page and its architect and just leave space to fill the aesthetic designs we have planned....but for now the website should be made in a way that i can add designs in upcoming days which wont affect the website and its looks in any way"
- What it means: every page is built now as structure: what it shows, in what order, its layout and every state. Each place a planned design goes is a reserved space of fixed size. A design added there later must not move or restyle anything outside that space. The plan is `frontend/design/website-plan.md`.

## HD-003: "The website" is the public site and the signed-in product together

- Date: 2026-11-27
- He chose: "Public site + product". The public pages (home, for creators, for brands, how it works, trust and safety, about, legal, sign in, public Passport) and the signed-in product for creators and brands, all designed as one desktop-first website, with no app-style tab bar.

## HD-004: An Apple-calm neutral look until the designs are added

- Date: 2026-11-27
- He chose: "Apple-calm neutral". Near-white and near-black, one refined typeface, large type, generous space; empty design slots shown as quiet placeholders. The warm colours return when he adds the designs.
- Meets an earlier rule: `frontend/tokens/tokens.json` says "never a plain white ground (white is mourning, TAMIL_DESIGN_ROOTS.md section 7)". He was shown this rule when choosing. The neutral look therefore uses an off-white ground, not pure white, and the rule's text in `tokens.json` is updated to say the warm ground returns with the designs. D-141 (Adhi: "should stand like a SaaS site, look SaaS") is consistent with this choice. Adhi is to be told.

## HD-005: Keep the creator journey's working code; redo its look

- Date: 2026-11-27
- He chose: "Keep logic, redo look". The logic, the backend wiring and the tests of onboarding, Discover, campaign, apply and My applications (D-200, D-201) stay; their layout and look are rebuilt inside the new website structure.

## HD-006: Each screen is shown and approved before the next

- Date: 2026-11-26
- His words: "show me each screen and get approval before creating next page"
- What it means: one page at a time, shown at phone and laptop widths, and the next page starts only after his yes.

## HD-007: The look of the dashboard and every page follows the COREHR reference

- Date: 2026-11-28
- His words: "i want the dashboard to look like this and every page in the standard" (with the Dribbble reference "Dashboard Mockup, Data Dashboard, Design by Saddam", saved in the session's images folder as 3.png).
- He chose: restyle Home first, then build the dashboard (Today); and a soft mint-to-cream tint as the site's background (not plain off-white, not the iridescent swirl).
- What it means: white rounded cards in a bento grid on the soft tint; near-black for the main button and the current menu item; lime as the highlight (badges, round arrow buttons, status tags, progress); sage green for one tinted card and charts; a centred pill-shaped top menu; large light-weight numbers and headings with small quiet labels. Dotted bars, the tick-mark ring, the split progress bar, round-check lists and tables with status pills are the dashboard's parts.
- Refines HD-004 (Apple-calm neutral): the near-white and near-black base stays; lime and sage are added to it. A style reference only: no names, assets or layout copied one-to-one.
- Meets earlier rules: D-142 (nothing is a photograph): the reference's photo card becomes a design slot and people show as initials. The reference's faint grey text is made darker so body text still meets 7:1 (`frontend.md` section 6).

## HD-008: Both roles get a dashboard; performance and campaign facts visible to both

- Date: 2026-11-28
- His words: "i need both the creator and brand to have dashboard. The brand should be able to view the collab status and the insights of the reel or post performing which is posted by the creator or posted in colab... and every information about the campaign and ongoing campaign should be able to be viewed by both creator and brands... i have already given you a dashboard look previously for reference it is in our file already the yellow one... just change its colour tone and use the reference i gave you now and that one and make a new one out of these... and it shouldnt spoil the aesthetics of the website"
- He chose: performance from the numbers read from creators' screenshots, honestly labelled ("Screenshot numbers now"), and "Yes, build it" to `frontend/design/dashboard-plan.md`.
- Order: Today for the creator and the brand, then the campaign page for both roles; one page at a time (HD-006).
