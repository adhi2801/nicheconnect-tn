# Design direction: Modern Tamil

**Status: Adhi's direction (4 October 2026), awaiting Erode Harish.** Adhi asked for a look that is "traditional but modern all around": premium, with considered motion, 3D and transitions, at least as good as Passionfroot's site, and better in every respect. Erode Harish's draft leans traditional. This file is the brief that serves both, for the design work D-053 allows now. Everything here is a proposal until a founder decides; nothing here is a decision entry.

It sits under the binding standards: `docs/standards/frontend.md` (budgets, accessibility, tokens) and `docs/standards/ux.md` (journeys, copy). Where this file and a standard disagree, the standard wins.

---

## 1. The idea in one line

**Tamil craft as the grammar, never as decoration.** A visitor should feel "premium product" in the first second and "this was made here, with care" in the fifth. No temple photographs, no clip-art kolams, no festival banners: the tradition is in the structure, the line, the colour and the material, the way Japanese design is present in a Muji shop without a single cherry blossom.

The test for every screen: *would a design-literate person in Bengaluru, London or San Francisco call it beautiful, and would a Coimbatore shop owner feel it is theirs?* Both, or it is not done.

## 2. The signature: the kolam, as a living line

A **kolam** is drawn on a grid of dots (*pulli*) with one continuous line that loops around them, fresh each morning at the threshold, as a welcome. It is also mathematics: kolams have been studied as single closed paths around a dot grid. It is the most fitting idea we have:

- **The dots are the people. The line is the deal that connects them.** That is the product, drawn.
- **One line, never lifted**, is the design language: things connect by a line drawing in; stages join by a line; a finished deal closes its loop.

Where it appears, and only here:

| Place | What it does |
|---|---|
| The logo mark | A small kolam that draws itself once on first load, then stays still |
| **The deal seal** (the novelty) | Every deal's record already has a `latest_seal` (a SHA-256 value, `docs/DEAL_RECORD_VERIFY.md`). The client turns it into **a unique kolam, deterministically**: the same record always draws the same kolam, and any change to the record draws a different one. Each new entry adds a loop; a finished deal closes the line. Brand and creator can compare their two kolams at a glance, the way SSH "randomart" lets people compare keys. It is beautiful, it is ours, and it carries real meaning: proof drawn as tradition. Shown only to the deal's two parties, like the record itself. |
| Completion moments | Mark as paid, confirmed received, campaign complete: the line closes its loop. The one place we celebrate. |
| Loading | Skeleton screens use a faint pulli dot grid instead of grey bars |
| Empty states | One single-line drawing, never a stock illustration |

Rules: **one kolam moment per screen at most**; never behind text; never animated more than once without the person doing something. A tradition overused becomes a theme park.

The kolam generator is a small piece of shared code (SVG on the web, Skia in the apps), seeded from the seal. No backend change is needed: the seal is already in the contract.

## 3. Colour: from the material, refined

Taken from things a Tamil household knows (granite, turmeric, kumkum, Kanchipuram silk, brass lamps), then tuned to digital contrast. Exact values are set in the token file and checked for WCAG 2.2 AA contrast in both themes before use; the names below are the roles.

| Token role | Source | Use |
|---|---|---|
| `ink` | Lamp soot, warm near-black | Text, the dark theme's ground |
| `granite` (a scale) | Temple stone, warm greys | Surfaces, borders, secondary text |
| `paper` | Rice-flour white, slightly warm | The light theme's ground; the kolam line on dark |
| `kumkum` | Deep red | The one primary action per screen. Never for errors (errors get their own red, distinguishable without colour). |
| `manjal` | Turmeric gold | Highlights, the completed loop. Sparingly: a few pixels per screen. |
| `pattu` | Kanchipuram peacock (deep teal) | Secondary accent, links, focus rings where it passes contrast |

Rules: one accent per screen region; meaning is never carried by colour alone; the dark theme is "lamp-lit" (warm), never blue-black.

## 4. Type

- **Display: a contemporary high-contrast serif** for headlines, for the editorial, crafted feel (candidates, all free: Fraunces, Instrument Serif, Newsreader). Large, tight, few words.
- **Interface: a clean, neutral sans** for everything else (candidates, free: Geist, Inter). Tabular figures for every amount and date, so ₹ columns line up.
- Self-hosted, subset, preloaded, with metric-matched fallbacks (frontend standard, section 4). Final pick by testing at 360 px on the budget Android device, at 200% text size.
- A commissioned typeface or logo is later and within the founders' budget: free fonts first.

## 5. Material and texture

- **The silk border.** Kanchipuram sarees end in a woven border (*korvai*). The deal pass, our signature object, gets a hairline border motif drawn from it, at the edge only. Nothing else does.
- Surfaces are solid with soft, warm elevation. No glassmorphism on the web (it fails contrast and costs paint time on budget phones); the apps use the platform's own materials (Liquid Glass on iOS, Material 3 Expressive on Android) through Expo UI, as the standard already says.
- Photography: real creators and real Tamil Nadu shops, after the pilot, with consent. Until then, product UI is the image. No stock photos, ever.

## 6. Motion: one language, three speeds

**Principle: motion explains, it never performs.** Everything moves the way a line is drawn: starts decisively, settles softly.

| Token | Duration | For |
|---|---|---|
| `motion.quick` | about 150 ms | Press, toggle, hover |
| `motion.move` | about 250 ms | A panel, a sheet, a card |
| `motion.story` | about 400 to 600 ms | A page change, the seal drawing, completion |

- **Shared-element transitions** are the signature move: a deal's card on the board *becomes* the deal pass when opened, the stage strip carried across. On the web this is the View Transitions API (no JavaScript library); in the apps, Reanimated shared transitions.
- **Scroll-told landing page**: the deal pass assembles itself stage by stage as the visitor scrolls (CSS scroll-driven animations where supported, behind `@supports`; a still, complete pass where not).
- **Physics, not curves**, for anything the finger drags (springs), so it feels physical on a phone.
- **Haptics in the apps** at three moments only: memo accepted, marked as paid, confirmed received.
- **"Reduce motion" is honoured everywhere**: transitions become fades, the seal appears complete. Nothing flashes more than three times a second.
- Lottie is not used (heavy, hard to theme). Rive is the candidate for the few interactive animations in the apps **(dependency decision when frontend starts)**.

## 7. 3D: one moment, earned

3D is where most "premium" sites fail on budget phones, which is where our creators are. So:

- **Exactly one 3D moment**: the deal pass on the landing page as a physical object (a card with weight and the silk border) that turns as you scroll to show its stages, and flips to show the seal.
- **It loads only after the page is usable**, only on devices that can run it (checked capability, memory and data saver), and never counts against the first-load JavaScript budget. Everyone else sees a crafted still image (AVIF) of the same pass, so nobody gets a worse page, only a still one.
- Built with Three.js (WebGPU where available, WebGL otherwise), or pre-rendered to an image sequence if that hits the budget better: chosen by measuring on the budget Android device, not by taste.
- No 3D inside the signed-in product. Brands are there to work; speed is the luxury.

## 8. The components that carry the brand

1. **The deal pass**: one per deal, five stages, who acts next, one action. Silk border, seal kolam. The object the whole product is remembered by.
2. **The stage strip**: five stages joined by one line that fills as the deal moves.
3. **Money facts**: amount, due, who marked it and when. Tabular, calm, never alarming. Overdue is stated plainly, never in flashing red.
4. **Honest numbers**: "not enough to say yet" is a designed state with its own look, not a missing number.
5. **The Passport card**: a creator's public page, shareable, fast (≤ 50 KB JavaScript), beautiful as a link preview on WhatsApp.

## 9. What we take from Passionfroot, and where we go past it

Passionfroot (Berlin, creator sponsorships) is the closest well-designed product to ours. Read 4 October 2026.

| They do well | We keep | We go past it by |
|---|---|---|
| Product UI is the hero, not illustration | Yes: the deal pass is our hero | Ours is a living object (3D, seal, stages), not a screenshot |
| Dark, tech-forward, one bright accent | A disciplined palette, one accent | A palette with a home, not a generic tech-dark one; a warm light theme too |
| Big customer logos and quotes | Social proof, **only real** | Pilot creators' and brands' own words, with consent, after the pilot. No sample numbers on the landing page. |
| Video trailer | No | A scroll-told story that works on 4G, plus a short muted loop at most |
| An AI agent as the headline feature | AI where it removes work (proof reading, D-070) | AI is never the headline; trust is. Every competitor says AI. Nobody else can show a sealed record. |

Other references, each for one thing: **CRED** (proof that an Indian product can have world-class craft and motion), **Linear** (motion restraint, keyboard speed), **Stripe** (detail, and documentation as product), **Apple product pages** (scroll storytelling), **Zerodha** (plain, trustworthy money wording).

## 10. What this changes in the current wireframes

The wireframe canvas (4 October) has the right structure. Against this brief:

- **The hero image "Temple scene (the one anchor)" becomes the deal pass** (still on load, 3D on capable devices). The Tamil identity moves into the kolam, colour and border.
- **"Festival strip" and "Kolam knot" are removed**; the kolam lives in the logo, seal, loading and completion.
- **The landing page goes from 20 sections to about 8**: hero, the two fears, how it works (the scroll-told pass), trust record and Passport, who it is for, what Colyv never does, FAQ, join.
- **"Proof band (sample data)" and "Ask Colyv" wait** until there are real numbers and a real endpoint.

## 11. How we will know it is the best, measured

Taste is argued; these are measured (`CLAUDE.md` section 7):

- **The five-second test** with 10 brand owners and 10 creators from the pilot interviews: "what is this, and would you trust it with a deal?" Run on Erode Harish's direction and on this one, same questions.
- **Budgets from the frontend standard hold with every motion and the 3D moment switched on**: LCP ≤ 2.0 s, INP ≤ 150 ms, CLS ≤ 0.05 on the budget Android device on slow 4G; 60 fps on transitions.
- **Accessibility 100** in Lighthouse, plus a manual screen-reader pass of the deal pass and the seal (the seal has a text equivalent: "Record intact, 7 entries, last on 3 October").
- **A design review against this file** before any screen is built.

## 12. Decisions this brief needs

1. **Direction**: Modern Tamil as above, or Erode Harish's traditional draft, or a blend: settled by the five-second test. **(Adhi and Erode Harish)**
2. **The seal kolam** as the signature: it is frontend-only, but it is a product idea. **(both)**
3. **Typefaces and exact colour values**: after testing on the reference devices. **(design, then both)**
4. **Rive and Three.js** as dependencies: when frontend work starts, through the usual dependency request.

## Sources

- Passionfroot, read 4 October 2026: https://www.passionfroot.me/
- Scroll-driven animations and View Transitions, browser support (2026 summaries; confirm on caniuse.com when frontend starts): https://www.frontendhorizon.com/blog/view-transitions-api-and-css-scroll-driven-animations-the-browser-wins-of-2026 and https://modern-css.com/whats-new-in-css-2026/
- The seal this design draws from: `docs/DEAL_RECORD_VERIFY.md`
