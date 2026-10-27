# Colyv landing page — design brief

**Status:** Proposed. Design only; no frontend code is in this repository (D-053).
**Updated:** 2 October 2026. This replaces the first version of the brief, whose motion decisions were wrong (section 1).
**Not reviewed by a second person** (D-051). Findings below are labelled **measured**, **sourced** or **judgement**.
**Preview:** the published design preview (private artifact "Colyv Landing Page"). Its source is not in this repo.

---

## 1. What went wrong, and what changed

The first build answered "all the motion, even more" literally: a fixed background that swapped scenes, drifting dust and petals, birds, a spinning kolam, flickering lamps, constant parallax, auto-advancing demos and looping records. The founder called it a school project. That verdict is supported by the sources in section 2 and by Colyv's own design system, which says: *"Motion explains cause and effect. Anything purely decorative is cut."* The first build ignored it.

The rebuild keeps the heritage and removes the noise. After 7 seconds idle the page has **0 running animations** (measured). The only motion left is a one-time line-draw of each temple scene, about 1.4 s, plus UI feedback under 300 ms. Everything that loops, drifts, flickers or auto-advances is gone.

## 2. Evidence base

| Finding | Source | Confidence | Consequence |
|---|---|---|---|
| People judge a page's beauty within 17 to 50 ms. Low visual complexity and high familiarity win; high complexity looks worse "even if the design is familiar". | [Google Research on Tuch et al. 2012](https://research.google/blog/users-love-simple-and-familiar-designs-why-websites-need-to-make-a-great-first-impression/) | Sourced, peer-reviewed lab study (screenshots, not live sites) | One temple anchor, a conventional page structure, calm ground. |
| Design look made up 46% of credibility comments across 100 sites; people infer "is good" from "looks good". | [Stanford Web Credibility guidelines](https://credibility.stanford.edu/guidelines) | Sourced; the study is older (early 2000s) | Craft and restraint are a trust feature. Show a real organisation, address and contact. |
| Hue maps to brand personality (red: exciting; blue: competent). Purchase intent is highest when colour supports the personality the brand claims. | [Labrecque and Milne 2012](https://link.springer.com/article/10.1007/s11747-010-0245-y) | Sourced; Western consumer samples | Colyv claims trust and competence, so a blue action colour supports it. |
| Colour meaning is largely cultural; in India red signals marriage and auspiciousness. | [exchange4media](https://www.exchange4media.com/marketing-news/decoding-colour-psychology-influencing-consumer-behaviour-in-india-137214.html), [Tilburg cross-cultural study](https://research.tilburguniversity.edu/en/publications/colours-of-emotion-trust-and-exclusivity-a-cross-cultural-study/) | Sourced, general | Maroon and red are heritage warmth, not action colours. |
| Studies of blue and online trust "show contrasting results". | Search result summary, 2 Oct 2026 | Sourced, thin | No colour is proven to convert. Test it (section 7). |
| UI animation should stay at or under about 500 ms; if you cannot say what it tells the user, delete it. | [Nielsen Norman Group summary](https://valhead.com/?p=2978) | Sourced, secondary | Motion budget in section 3. |
| India UPI adoption is driven by ease of use, speed and security. | [IIMK working paper](https://iimk.ac.in/uploads/publications/IIMKWPS638FIN202505%20.pdf), [arXiv](https://arxiv.org/html/2401.09937v2) | Sourced, not about colour | Reassurance copy about security and speed matters beside any hue. |

**Not found:** an India-specific study of which colour builds trust in a marketplace app. Anything claiming one is a guess.

## 3. Rules derived from the evidence

1. **Familiar structure.** Nav, hero, proof, how it works, features, FAQ, sign-up, footer. Heritage is the finish, not the layout.
2. **One anchor per screen.** One large temple in the hero. Faint, still line art at the right edge of a few sections, hidden behind cards. A thin temple border between major sections. Nothing else competes.
3. **Heritage is ornament; Colyv is the UI.** Gold and red oxide never mean "press this". Cobalt does.
4. **Motion budget.** At most 500 ms. Nothing loops. Nothing advances by itself. Each scene draws once (about 1.4 s). Reduced-motion users see everything fully drawn and still.
5. **Day first.** The light theme is the default on first visit, because a light, high-contrast, familiar surface is the safest first impression for money. Night (maroon and gold) is one tap away and remembered. A production build should respect the system setting.
6. **Say what Colyv does not do, beside the main button:** "Colyv never holds or moves money."
7. **No invented proof.** All people, brands, figures and dates are labelled sample data.

## 4. The heritage system: each motif has a job and a place

| Tradition | What it means | Where it appears |
|---|---|---|
| Vimana / gopuram (temple tower) | A gateway; arrival | Hero tower; faint towers at section edges |
| Kolam | A threshold of welcome, drawn fresh each morning | Sign-up floor; the "not enough data yet" states, where it marks something not yet drawn |
| Mango-leaf toranam | The garland over a door that says "come in" | Over the sign-up card |
| Kovil karai (temple border of Kanchipuram silk) | The woven border that frames fine cloth | Thin dividers between major sections |
| Athangudi tile | Chettinad's handmade courtyard floor | The mark on each price package in the Passport |
| Thanjavur arch with gold double border | A framed, honoured picture | The Passport frame |
| Chettinad pillared hall and veranda | Where deals were struck | Faint line art behind the Passport section |

Not done, and why: **bharatanatyam mudra hands** and **terracotta Ayyanar horses** need an illustrator to avoid looking amateur. **Tamil script** is out (D-054); all text is English.

### 4a. The 3D temple background (added 2 October 2026 at the founder's request)

The founder asked for a Thanjavur (Brihadisvara) temple as a 3D background, with the front elements and boxes in glass. Reference: a sunset photograph of the temple.

- **What it is.** A procedural WebGL scene (three.js r128, no image or model files): a 13-tier stepped tower with carved-relief textures and bump maps, two storeys of niched walls, a dome and gold finial, the front halls with a pillared porch and stairs, a stone lamp pillar in the foreground, a far compound wall, and a sunset sky with a low warm key light and haze. The night theme relights it as dusk.
- **It is a stylised model, not a photograph.** It reads as the same temple, but the carving is texture and relief, not sculpture. A modelled-and-textured asset by a 3D artist would be the next step in quality.
- **Glass in front.** Hero copy, deal record, nav, dock and every card sit on Colyv glass with a 12 px blur and 180% saturation (the web ceiling), so the temple shows through softly. The fill is more translucent over the scene (0.74 day, 0.70 night), and the nav uses the strong fill because it carries small text.
- **A scroll-driven scrim** (a copy of the calm ground) rises from 8% to 88% as the visitor scrolls the first screen, so lower sections stay readable and the temple fades to a faint ghost.
- **Motion rule.** Nothing moves by itself. The camera eases a little with scroll and pointer, then stops. Measured: 0 animation-frame requests in 3 s idle; 21 frames to ease after a scroll, then 0. Reduced motion: one static frame, no camera movement.
- **Loading rule.** The scene loads after the page is up and the browser is idle. A CSS sunset poster shows instantly and the canvas fades in over it. It is only attempted when the device reports Data Saver off, at least 4 CPU cores (6 on touch devices) and at least 4 GB of memory, and the visitor has not turned it off. Otherwise, or on any failure or lost context, the page uses the calm still version, which is the layout measured in section 6. A "3D" switch in the dock turns it on or off and the choice is remembered.

### 4b. Bringing it together (2 October 2026, second round of founder references)

The founder supplied a Thanjavur kolam-and-doll wall niche photo and a banana-tree illustration, and asked for them as **elements, not the main thing**; for glass that is more transparent; for smoother motion; and for a more unified, aesthetic page.

- **Banana trees** (the supplied illustration, white sticker outline removed, 46 KB WebP) frame the foreground at the hero's left and right, toned to the scene's light and drifting a few pixels with the pointer. They fade out as the visitor scrolls. Hidden on small phones except one.
- **The wall niche** (the supplied photo, 19 KB WebP) sits inside the sign-up card in an arch frame with a brass outline, in front of the glass.
- **The kolam from the photo** is drawn as a woven-knot motif in code (four teardrop loops, over and under, a dot in each) and reused in five places that each mean something: the divider between major sections (with the temple border either side), the hero card corner, the footer crest, and the "not enough data yet" notices, where it stands for something not yet drawn.
- **Other ornaments:** a lamp symbol (kuthuvilakku) replaces the check marks in the assistant's list; the toranam over the sign-up card and the kovil-karai dividers were kept.
- **Glass is more transparent over the scene:** 0.56 white in day (was 0.74) and 0.60 deep maroon at night (was 0.70). This is the point where text contrast is still above 4.5:1 everywhere: computed worst case over the darkest sky, mid sky, stone and brightest sky is, day, body 6.6 and muted 5.1; night, body 5.5 and muted 5.0. The muted text colours were darkened (day) and lightened (night) to hold that. Going further would fail the standard.
- **Smoother motion.** One easing curve and four durations (160, 280, 600 and 1200 ms) for every transition; transform and opacity only. Camera, banana drift and the scrim now share one frame-rate-independent smoothing loop (the same feel at 30, 60 or 120 fps) that stops when nothing changes. The theme switch is one cross-fade using the View Transitions API with the 3D sky prepared beforehand, so nothing pops. Switching between brand and creator softly cross-fades. The deal-step panel eases in. FAQ items open with an animated height. Sections reveal with a gentle rise. All of it is removed under reduced motion.
- **Measured:** 0 animation frames and 0 running CSS animations at idle; 0 axe violations, day and night; no horizontal overflow and no touch target under 44 px at 390 px. Fallback (no 3D) Lighthouse: mobile 98 / 100 / 96 / 100 (LCP 1.8 s), desktop 100 / 100 / 96 / 100 (LCP 0.4 s). The images load after first paint. "Smoother" is by construction (shared easing, no layout-property animation, an adaptive loop), **not yet measured as frame times on a real device**.
- **Photo rights.** The two images are used as supplied by the founder; their licences are unknown. Confirm the right to use them commercially before launch, or replace them with commissioned or licensed art.

### 4c. Rearchitecture against a benchmark (3 October 2026)

The founder asked for the site to be rearchitected and to be better than Passionfroot in every aspect. "1000x better" is not a measurable claim, so the benchmark below uses what can be measured.

**What the benchmark site does well, and what was matched.** A confident centred headline; floating product cards in the hero; full-fidelity product walkthrough sections; large proof blocks (customer logos, testimonials, case studies, a roster of named creators); a full FAQ; a footer sitemap; a consent banner. Colyv matches the first three, and does not fake the fourth: there are no customers yet, so there are no logos, quotes or case studies (CLAUDE.md constraint 7, and section 3 rule 7 above). The honest equivalents are a "where we are" section and a deal-record check anyone can try.

**Measured, 3 October 2026, Lighthouse 13.5 with simulated mobile throttling, public pages, headless Chrome on a laptop:**

| | Passionfroot (live) | Colyv rearchitected (no-3D fallback, local server, uncompressed) |
|---|---|---|
| Performance, mobile / desktop | 57 / 79 | 97 / 100 |
| Accessibility, mobile / desktop | 94 / 85 | 100 / 100 |
| Largest contentful paint, mobile | 11.4 s | 2.1 s (budget 2.5 s) |
| Cumulative layout shift, mobile / desktop | 0.127 / 0.104 | 0 / 0.001 |
| Transfer size | 1.9 to 2.2 MB | about 0.33 MB uncompressed; page 113 KB gzip |
| Failed accessibility audits | aria-allowed-attr, heading-order, label-content-name-mismatch (and list, listitem, target-size on desktop) | none |

Caveats: the two sites were served differently (theirs from a CDN with compression; ours from a plain local server), so the speed comparison favours neither cleanly; a real hosting test is still owed. With the 3D temple on, Colyv's speed is **not** shown here: the sandbox needs a CPU renderer for WebGL, which distorts Lighthouse.

**Where Colyv is not yet better.** No customer proof, no video, no mascot or illustration set beyond the generated temple art, no brand photography, no case studies, no real product behind the screens (they are previews), and the deal-record checkpoint and hash demos run in the browser, not against the service.

**What changed in the architecture.**
- A real source tree (`source/` in the published artifact): messages in `en.json` with a build that fails on a missing key; one HTML partial per section; nine style files from tokens to motion; ten script modules; one build command that produces a single deployable file.
- Information architecture: nav, hero with three floating product cards, a "works with" strip, the problem, a six-chapter interactive walkthrough (post a campaign, review applications, agree the memo, send proof, payment said then confirmed, dispute), roles, the trust record with a tamper-evident check, Passport and fair rate, matching, the assistant, "what we never do", "where we are", a comparison table, a ten-question FAQ, the pilot form and a footer sitemap.
- The product mockups use only states and words the API has (campaign types, shortlist/accept/reject with a reason, memo, proof with a disclosure confirmation, mark paid then confirm, dispute entries, sealed records, a daily outside-timestamped checkpoint from D-057 and D-060).
- Kolam is an element (knot dividers, footer crest, hero corner, empty states), not a background. The floral damask ground and the faint line-art temples remain; no kolam is drawn behind content.

**Measured:** 0 axe violations in day and night; every walkthrough step, the tamper demo, the passport toggles, the assistant, the form and the theme switch exercised by script; 0 animation-frame requests and 0 running CSS animations at idle; no horizontal overflow at 320, 390 and 720 px; no touch target under 44 px at 390 px except one inline text link.

### 4d. Motion, depth and the empty-page fix (3 October 2026)

Research consulted: the motion.dev examples catalogue (scroll-linked, text effects, cursor, springs, layout), Framer template patterns, Passionfroot's own page, a 2026 trends survey and its six-month reality check (bento and design systems held up; glass is fine only in limited areas; kinetic type needs restraint; WebGL needs a budget and a fallback), and browser support for CSS scroll-driven animation ([all three engines, over 95% of traffic](https://www.buildmvpfast.com/blog/css-scroll-driven-animations-replace-js-2026)). Passionfroot's markup references Framer and Lenis; Colyv uses native CSS and about 30 KB of its own script instead.

What changed, and why:
- **The temple is a tour, not a hero image.** A camera path (hero, close on the carved storeys, the hall side, a high view, the lamp-pillar pavilion, pulled back) is driven by scroll across the whole page, and the scrim that covers it now stops at about half, so the sections below sit over the moving temple instead of a blank ground. The temple has pilasters, lotus-petal plinths, niche figures with torana arcs, horseshoe kudu arches with faces on every tier, projecting salas, corner Nandi plinths, a gabled porch with stairs, yali heads, a lamp-pillar pavilion, and a cloistered compound wall with gateway towers. It is still procedural.
- **Controls are symmetric.** Every segmented control has equal-width columns and one thumb that springs to the pressed option (measured: 127/127, 119/119, 167/167/167, 251/251 px). The nav sets the current section.
- **Heads and chapter text sit on glass** so they read over the scene; contrast math was re-run for the new alpha.
- **Motion vocabulary** (native CSS plus small script): a scroll progress line; whole-word headline reveals (the text stays real text); a cursor spotlight on glass; magnetic primary buttons on fine pointers; Framer-style 3D rise for device mockups and tiles driven by the scroll timeline; spring easing on the thumb and tiles; a pausing ticker; count-up on trust figures. All of it is removed under reduced motion; none of it fades text below full contrast.
- **Kolam is in the border.** The feature cards carry kolam knots at the four corners and a braid along the top and bottom edges, outside the content.
- **New section:** a bento of six rules with something to try (add a sealed step; tap twice and get one record; publish or unpublish a Passport; small-number honesty; export; WhatsApp alerts marked Coming).

Measured: axe 0 violations day and night; no horizontal overflow at 320 and 390 px; touch targets 44 px except one inline link; 0 animation-frame requests at idle; reduced motion leaves no looping animation. Fallback Lighthouse: mobile 94 / 100 / 96 / 100 with LCP 2.8 s (**0.3 s over the 2.5 s budget**, driven by the late-painting decorative banana image), desktop 100 / 100 / 96 / 100. Two regressions were found and fixed along the way: an entry fade that failed contrast mid-animation, and start-up work that pushed mobile LCP to 3.9 s.

### 4e. The temple at festival (3 October 2026)

Founder references: a set of sikku kolams (a tall lattice with rounded edges and a dot in every diamond; a small woven knot) and a large rhombus kolam in white rice flour on a red-oxide floor, in front of a limewashed wall with painted niches.

- **Kolam geometry is generated, one source for 2D and 3D.** `kolamGeom('bounce')` is the diagonal lattice whose lines end in rounded Vs at the border; `kolamGeom('hairpin')` is two interleaved serpentines of hairpin loops, rotated 45 degrees, with rings round alternate dots. These are faithful in structure to the references, not copies, and a kolam specialist should review them before launch.
- **2D:** large terracotta kolams (`--kolam-clay`, #B8582F by day, #DB8A5E at night) sit in the margins of five sections, 340 to 600 px tall, and draw themselves once when scrolled into view. They are ornament beside content, never behind text, and are hidden below 900 px.
- **3D, in front of the temple:** a rice-flour kolam on a red-oxide courtyard patch, drawn in line by line once on load. As the page scrolls through the festival interlude the patch and kolam grow by about 55% and the camera pushes in over them.
- **Toranam and festival dressing:** mango-leaf and marigold swags hang on both storey porches, the hall porch, across the plaza between two poles (over the kolam) and around the lamp pavilion; flower strands hang from the porch; 24 lamps on clay saucers ring the courtyard. Each swag has its own window on the scroll path and drops in along its length as the page scrolls down.
- **A festival interlude** (about 1.9 screen heights, 3D mode only) follows the hero: the glass parts, the scrim lifts, and a single caption appears: "A welcome at the threshold". It is the one place the whole scene is on show. The camera path is mapped so its first 30% plays during the interlude.
- **Concision:** the "principles" section went from eight cards to four, because the bento section already covers the rest.

Measured: 0 axe violations (day and night); 0 animation-frame requests at rest once the kolam is drawn; no horizontal overflow at 390 px; reduced motion shows kolams complete and nothing loops. Fallback (no 3D) Lighthouse: mobile 95 / 100 / 96 / 100, LCP 2.3 s (inside the 2.5 s budget); desktop 100 / 100 / 96 / 100. With the 3D scene on, speed is still not measured on a real GPU or phone.

### 4f. Burgundy, the kolam idea, and the Passport card (3 October 2026)

Founder decisions in this round: no dark mode; a burgundy action colour; the Creator Passport should look like the card in the product (a burgundy credential with a flip); the kolam looked artificial and should follow a new reference (a cropped petal kolam in brown line on cream); and **the kolam is the definition of the product: the dots are creators, and a brand connects with every creator in one place.** The site should stop looking machine-built.

- **Dark mode is removed**, with its tokens, its toggle, the night sky and the night logo. Day is the only theme.
- **Burgundy** `#7A1428` is the default action colour (hover `#651021`, pressed `#520D1A`; white text 11.5:1). The Colyv design system's cobalt is still one tap away in the dock for comparison; the logo mark is unchanged and is still cobalt, so choosing burgundy for good is a brand change and needs a decision entry and a logo update. This also means burgundy buttons sit next to a cobalt mark on the page today.
- **The kolam idea has its own section** ("One line. Every creator. One place."). A petal kolam of twelve creator dots and one brand dot: the brand's thread, one burgundy curve, draws through every dot in turn while a counter reaches "12 creators connected to 1 brand, in one place". Hover or focus a dot to meet a (sample) creator. The thread is a visual device: the kolam is the drawing, the line is the brand, and nothing in it is data.
- **The kolam geometry was redrawn** (`kolamGeom('petal')`): a diamond of dots, each in a teardrop whose tip crosses its neighbour's, after the new reference. It replaces the hairpin lattice on the courtyard floor and the margin ornaments (cropped at the page edge like the reference), and the earlier woven knot is gone from every border, crest and notice. It is still generated, not hand-drawn: a kolam artist should draw the final version.
- **Passport card:** a burgundy card with a flip: front has the category, name, a photo area, handle, key facts and the card code; the back has channels (links only), asking prices and the actions. **The photo is a monogram**, because the service has no photo field; the sample note says so. Adding a photo would be a backend request with its own consent and storage questions. The card tilts toward the pointer, and the hidden face is inert so a keyboard cannot reach it.
- **Why it looked machine-built, and what changed:** every section was a floating frosted box, with identical rounded cards, sans-serif headings and decorative frames. Now: headlines are set in a serif (Fraunces) with sentence-case body in the system sans; sections are full-width frosted slabs with plain headings and a hairline; the cards inside are solid paper (no glass on glass); the decorative frames remain only on the hero and the sign-up card; and ornaments carry one idea each. Whether this reads as "billion dollar" is a judgement for the five-second test in section 7, not something measured here.

Measured: axe 0 violations; no overflow at 390 px; 0 frame requests at rest after load; reduced motion shows the thread drawn; fallback Lighthouse mobile 96 / 100 / 96 / 100 (LCP 2.2 s), desktop 100 / 100 / 96 / 100.

### 4g. The traced kolam and the chosen logo (3 October 2026)

The founder said everything was right except the kolam, supplied a photograph of the kolam wanted (a white lotus-star sikku kolam on a terracotta arch) and a logo to use.

- **The kolam is traced from the photograph, not drawn from a rule.** The invented generators (hairpin lattice, petal teardrops) were rejected twice as artificial. The photo was thresholded, thinned to a one-pixel skeleton, split at crossings and fitted with smooth curves (`tools/trace-kolam.mjs`): 74 strokes, 13 dots in a 1-3-5-3-1 diamond, an eight-point lotus outline, a woven lattice and teardrop loops. It keeps the hand-painted character of the original, including small irregularities in the star outline. A symmetrised version is possible if wanted, but would no longer be "exactly like this". The source photograph is small (the kolam is about 280 px wide), so a kolam artist should redraw it for print or large display. The photograph's licence is unknown.
- **One drawing, used everywhere.** The same data draws the courtyard-floor kolam in 3D (rice-flour white on red oxide, drawn in once), the large terracotta margin kolams (cropped at the page edge), the idea section (the 13 dots become 12 creators and 1 brand, with the brand's thread through all of them), the Passport photo corner, and a small reusable mark for crests and notices.
- **Logo.** The supplied kolam-and-wordmark artwork replaces the design-system logo in the nav and footer. It was cut from the supplied PNG onto transparent backgrounds in a single burgundy; it is a raster (the nav copy is 209 and 327 px wide), so a vector master is needed for print and app icons.
- **Conflicts to decide before this logo ships, none of which I have resolved:** (1) the wordmark reads "கோlyv.ai" — it contains Tamil script, while D-054 says the product is English-only with Tamil as art only; (2) it spells the name with a Tamil first letter and a ".ai" suffix, while the rest of the product, the domain assumptions and the design system say "Colyv"; the page copy still says Colyv; (3) the Colyv design-system logo set (cobalt) is now superseded for the website but unchanged in the design system. Each needs a founder decision and a `docs/DECISIONS.md` entry. I cannot vouch for the meaning of the Tamil letters; a fluent reader should confirm them.
- **Measured:** axe 0 violations; 0 frame requests at rest; no overflow at 390 px; fallback Lighthouse mobile 94 / 100 / 96 / 100 (first and largest paint 2.5 s, exactly at the 2.5 s budget), desktop 100 / 100 / 96 / 100. One regression was found and fixed on the way: rebuilding the kolam for every small mark pushed mobile paint to 5.0 s, fixed by defining the mark once and reusing it.

### 4h. The temple becomes a photograph, motion floats, a courtyard to explore (6 October 2026)

**Reverted the same day at the founder's request.** The published preview is back to the procedural temple of section 4e and the dashboard-mockup changes; none of what follows is live. It is kept as a record of what was tried and measured.

Founder request: much smoother scroll motion that "floats"; the temple as real as a supplied reference photograph; birds flying as the page scrolls; and, if it suits the site, a supplied rain-courtyard illustration made interactive below the temple. **Not reviewed by a second person** (D-051).

- **Why the procedural temple was replaced.** A model built from primitives cannot reach photographic realism (section 4a already said so). The background is now the supplied photograph, upscaled and sharpened (the source is only 736 px wide), with a depth map estimated from it (Depth Anything V2, run offline) and a hand-traced pond mask. A three.js plane is displaced by the depth map, so the tower, the pond pavilion and the steps move against each other as the camera tours down the picture. Past the picture's edges it is stretched and blurred, like the edge of a lens. The earlier 3D festival dressing (floor kolam, toranam, lamps) is gone with the procedural scene; `temple3d.js` is kept under `_retired/`, unbuilt. The illustrated banana trees stay, but as out-of-focus foreground, because crisp illustration beside a photograph looks pasted on.
- **Smooth, by construction.** Scroll, pointer, scrim, camera, birds and the floating cards now share critically damped springs (no overshoot, continuous velocity) instead of a first-order ease. On a step input at 60 fps (computed, not measured on a device) the old ease moved at its peak speed on the first frame; the new one starts at 6% of peak and peaks at 0.35 s. Cards (hero card, three hero cards, device mockups, tiles) drift a little behind the page and settle, using the CSS `translate` property so they never fight existing transforms. Native scrolling is untouched, so keyboard, find-in-page and anchors behave as before. Per-frame custom properties moved off the root element, which had forced the whole page to re-check styles.
- **Birds.** About 24 birds in four flocks (a gliding V in the hero sky, a few far ones, white egrets over the pond during the interlude, three late stragglers). Wing-beats are driven by distance scrolled, not time: they beat while you scroll, glide when you stop, and turn round when you scroll back. Nothing loops, which keeps rule 4 of section 3. The silhouettes are procedural and simple; an illustrator's flight cycle would be better.
- **The pond** ripples only while you scroll, by an amount that follows scroll speed, and settles.
- **Courtyard section** (after the cities strip, before the kolam idea). The supplied illustration is split by estimated depth into a far layer and a near layer (banana leaves, pepper vine); the layers shift against each other with pointer and scroll. Four numbered moments (veranda, arrival, lamp, steps) map to the deal memo, proof, sealed record and payment status, using only statements already made elsewhere on the page. Selecting one zooms toward it. Puddles ripple where you touch or hover them, then stop. It is a tablist with arrow-key navigation; the pins are a pointer shortcut and are hidden from assistive technology.
- **Does the courtyard suit the site?** Partly. Its palette (terracotta, leaf green, grey-blue) sits well with the red oxide, burgundy and banana green already used, and a courtyard where deals were struck is already in the heritage table of section 4. But it is flat vector art beside a photograph, so it is framed like the Passport (Thanjavur arch, gold double border) rather than blended. It also reads as a Kerala house (palm-leaf umbrella, Mangalore tiles), not a Tamil Nadu one, which a Tamil Nadu audience may notice. Decide whether to keep it, commission a Chettinad courtyard, or drop it.
- **Provenance and licences (open).** Both supplied images are of unknown origin and licence. The courtyard image carries a visible credit ("NeuralRaga"), which is kept in the image and repeated as a caption. The temple photograph looks like a Vijayanagara-style tank with a central pavilion; I cannot identify a specific temple, and it is not claimed to be in Tamil Nadu. Replace both with licensed or commissioned art before launch.
- **Measured (headless Chrome with a software WebGL renderer, so GPU cost is not included).** Main-thread cost for the same scripted 4,400 px scroll, before and after: script 657 to 60 ms, layout 20 to 3 ms (195 to 29 layouts), style recalculation 1,292 to 302 ms, total tasks 2,383 to 613 ms. Idle: 0 animation-frame requests in 3 s. Reduced motion: the tour stays at its start, no looping animation. No console errors; no horizontal overflow at 390 px. Text contrast against the actual rendered pixels (glass, scrim and photograph, text hidden, worst 3rd percentile) over five scroll positions: 125 text runs, 0 below 4.5:1 (3:1 for large text); one failure (the hero's gold phrase, 2.76:1) was found and fixed by darkening it to `#6f4500`.
- **Not measured.** Frame rate on a real GPU or phone, Safari and Firefox, battery, and a real screen reader. **Page weight rose** to about 916 KB (577 KB gzip) because the images are inlined as data URIs in this single-file preview (temple 250 KB, courtyard 150 KB, plus masks); production should ship them as cached image files, loaded only when needed, and the temple should be re-sourced at a higher resolution.

## 5. Colour roles

| Job | Day | Night | Rule |
|---|---|---|---|
| Ground | Limewash cream `#F8EDD6` | Kumkum maroon `#3A0A17` | Never used for buttons. |
| Ornament | Red oxide `#9B2F20`, brass | Manjal gold `#E9BC5A` | Decoration and the one emphasised phrase only. |
| Action | Cobalt `#2C4BD6` | Cobalt light `#6180FF` | Buttons, links, the active step. The brand colour, unchanged. |
| Status | Green, amber, red | Same | Always a word plus an icon. |

The dock's colour switch (cobalt, indigo, peacock teal) is a review tool. Indigo or teal would change the brand and needs a decision entry; teal is also close to the "paid" green. Saffron and orange were deliberately not offered (strong religious and political meaning in India).

## 6. Measured results (2 October 2026)

Headless Chrome on a laptop, Lighthouse 13.5 with its simulated mobile throttling (4x CPU slowdown, 1.6 Mbps, 150 ms latency), page served locally and uncompressed. **Not a real phone.**

| Check | Result | Budget (`docs/standards/frontend.md`) |
|---|---|---|
| Lighthouse mobile: performance / accessibility / best practices / SEO | 100 / 100 / 96 / 100 | performance 90 or more |
| Largest contentful paint (mobile, simulated) | 1.1 s | 2.5 s or less |
| Total blocking time (INP proxy) | 0 ms | INP 200 ms or less |
| Cumulative layout shift | 0 | 0.1 or less |
| Lighthouse desktop | 100 / 100 / 96 / 100; LCP 0.3 s | n/a |
| Script and style, gzip | 14.0 KB and 6.4 KB (whole page 27.8 KB) | 170 KB JavaScript per route |
| axe-core 4.10 (WCAG 2.0 to 2.2 A and AA, plus best practice), day and night | 0 violations, 49 rules pass | WCAG 2.2 AA |
| Text and background contrast, computed for every pair, both themes | Body at least 16:1; muted at least 7.5:1; emphasised phrase at least 4.4:1; button text at least 5.7:1; status pills at least 6.8:1 | 4.5:1 text, 3:1 large text and UI |
| Running or looping animations after 7 s idle | 0 and 0 | none that loop |
| Touch targets under 44 px (phone, 390 px wide) | 0 | 44 px (`tap-target`) |
| Horizontal overflow at 390 px | 0 px | none |
| Reduced motion | all scenes fully drawn, 0 running animations | respected |

axe could not resolve 39 contrast checks because text sits on translucent glass; those were computed by hand and are in the row above.

**The numbers above are for the page with the 3D background off (the fallback).** With 3D on:

| Check | Result |
|---|---|
| axe-core, day and night | 0 violations, 49 rules pass |
| Worst-case text contrast on the translucent glass (computed over the darkest sky, mid sky, stone and brightest sky) | Day: body at least 10.5:1, muted at least 5.6:1. Night: body at least 7.6:1, muted at least 5.6:1. This check caught the night nav at 4.1:1 and 3.0:1 over a bright sky; it now uses the strong fill |
| Render loop at idle | 0 animation-frame requests in 3 s |
| 3D library weight | `three.min.js` 145 KB gzip, loaded only after the page is up. Page scripts including the scene: 19.7 KB gzip. Total script about 165 KB gzip, under the 170 KB budget even counted together |
| Lighthouse with 3D on | **Not trustworthy in this environment.** Giving the headless browser WebGL required a software (CPU) renderer, which also made the 3D-off page slower in the same run (first paint 3.2 s instead of 1.3 s). With 3D on it reported performance 36 to 63 and 11 to 15 s of blocking time, mostly the software renderer. A real GPU runs this work off the main thread, so those numbers are pessimistic, but how pessimistic is unknown |

**Not measured:** real-device frame rate, battery, scene build time and INP on a physical budget Android phone, Safari and Firefox rendering, a real screen reader, Tamil Nadu network conditions. **Before the 3D background is enabled by default, measure it on real mid-range and low-end Android phones** (for example WebPageTest on a real device or Chrome DevTools remote profiling) against the budgets in `docs/standards/frontend.md`; if it misses them, restrict it to desktop and high-end devices. Lighthouse's other notes are the missing document headers on the local test server and compression, which belong to hosting.

## 7. Test plan (per `docs/standards/ux.md` section 2)

Colour and heritage choices are hypotheses until users test them. Five or more conversations each with brand owners and creators in Tamil Nadu.

1. **Five-second test** of three variants: (A) this page in day theme; (B) night theme; (C) a plain modern control with no heritage ornament. Ask: what does this company do? How much do you trust it (1 to 7)? Would you give your phone number?
2. **Pass condition, set before testing:** A or B must rate at least equal to C on trust and not lower on comprehension. If heritage lowers either, reduce it further.
3. **Action colour:** compare cobalt and indigo buttons on the same page for the sign-up rate once there is traffic.
4. **Task completion** of the core journeys (`docs/standards/ux.md` section 3) at 90% or better.

## 8. Decisions needed

1. **Is the calm direction confirmed?** It replaces the founder's earlier "all the motion for everyone". It also removes the need for a budget exception (JavaScript is 14 KB gzip). If full motion is still wanted, the exception must be recorded in `docs/DECISIONS.md` with an approver's name; the approver is not known to this session.
2. **Default theme.** Day-first is a judgement, not an evidence-backed fact; the five-second test should check it.
3. **Brand colour.** Keep cobalt (recommended) or change the brand; a change needs a decision entry and a new logo set.
4. **Illustration.** The temple art is generated in code. It is clean but cannot match carved detail. For the quality of the reference images, commission or license vector illustrations (vimana, gopuram, Chettinad hall, mudra hands) and have a Tamil designer review every motif.
5. **Real-organisation details** (registered name, address, contact) are placeholders in the footer. Credibility research says they matter; they must come before launch.

## 9. What this page needs from the rest of the team

1. **A waitlist endpoint** (not built): role, city, phone or email, a consent record, a rate limit. The form sends nothing.
2. **Sign-in** works in the backend, but no one-time-code provider is chosen (backlog E1), so it is shown as "opens with the pilot".
3. **The assistant is a scripted demo** with a small fixed knowledge base from this repository's docs. A real one needs approvals under CLAUDE.md section 5: provider, grounding on approved content (retrieval, not fine-tuning), abuse handling, rate limits, no personal data in prompts or logs, and refusal of legal, tax and compliance questions.
4. **Copy to confirm:** "Pricing is not final"; "WhatsApp alerts" is marked Coming because notifications are recorded but not delivered; consent wording is a placeholder; the pilot city is not chosen.

## 10. Known issues

- `ink-primary` (light) in the design system is `#283c8b` with a 18.8:1 claim that colour cannot reach. The page uses the system's near-black ink (`brutal-stroke`) instead.
- The Figma file from the original request was never opened.
- Other pages (Creator Passport spec, onboarding, app screens) are not restyled; `creator-passport-spec.md` still describes the earlier plain treatment.
