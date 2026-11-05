# The landing as a film: a living world at dusk

Research for the landing page's hero, written 5 November 2026 after Adhi's direction the same day. Every source has the date it was read. What this changes in the standard is in `docs/standards/frontend.md` section 8b; the scroll mechanics it builds on are in `FEEL_AND_MOTION_2026.md` section 4 and are not repeated here.

## 1. What was asked, and what the last renders got wrong

**The direction (Adhi, 5 November 2026).** A lone tower on a plain sky reads as "a temple website". The landing should be the prototype's *living world* (sky, courtyard, the temple standing in it, motion) with class and definition the prototype never had: photoreal, restrained, cinematic, one slow camera move driven by scroll, the product's glass cards sitting in that world. The prototype (`frontend/prototypes/homepage.html`) stays the floor, never the target.

**The two test renders of 5 November, judged against that:**

| Shot | What worked | What failed |
|---|---|---|
| `threshold` | Two hall pillars frame the tower; lamps along the step; the wet paving reflects | Lit as afternoon, not dusk: the scene's default sun stands **16° above the horizon** (`frontend/3d/temple/vimana.py`, the `SUN_EL` default), so the sky is flat blue and the lamps are invisible against it |
| `approach` | The processional path leads the eye to the tower | Cartoon props (bananas) below the render bar; an empty plaza; the same afternoon light |

The cause of "flat blue afternoon" is therefore one number, not the renderer. Sections 3 and 4 set the hour and the light that replace it.

## 2. What the best do

- **One world, navigated by scroll.** Igloo Inc (studio Abeto) won Awwwards' Site of the Year and Developer Site of the Year 2024; the jury's comments single out an immersive 3D world that is still navigated by plain scrolling, "a video game turned into a website" ([Awwwards, Site of the Year 2024](https://www.awwwards.com/annual-awards-2024/site-of-the-year) and [Developer Site of the Year 2024](https://awwwards.com/annual-awards-2024/developer-site-of-the-year), read 5 November 2026). It also won a 2026 Webby for visual design ([Webby Awards 2026](https://winners.webbyawards.com/2026/websites-and-mobile-sites/features-design/best-visual-design-aesthetic/361001/igloo-inc), read 5 November 2026). **What we take:** the world is the page, and scroll is the only control. **Where we go further:** Igloo is real-time WebGL and is heavy on a budget phone; ours is path-traced frames (section 6), so a ₹10,000 Android sees film quality at the cost of a sequence of images, not a GPU.
- **Restraint.** A designer's survey of 2026's Sites of the Day names "1–2 strong moments, not 10" and gold or copper accents on dark palettes as what wins now ([svilenkovic.com, "Awwwards 2026 3D"](https://svilenkovic.com/3d/awwwards-2026-3d), read 5 November 2026). This is one person's opinion, not Awwwards' own words, and is used only because it matches section 8c's existing rule (one orchestrated moment per page).
- **Apple's product pages.** The page for iPhone 17 Pro, fetched on 5 November 2026, carries 33 still images (`large_2x.jpg`) in its HTML and no inline video source: its scroll films are loaded by script, so whether Apple scrubs a video or draws frames on a canvas today could not be confirmed from the page. Community accounts disagree: older ones describe frames drawn on a canvas, a recent one says video ([CSS-Tricks](https://css-tricks.com/?p=308477); [skills.sh, scroll-video-website](https://skills.sh/musoyangrigor/scroll-video-website-skill/scroll-video-website); both read 5 November 2026). **Not verified; we do not rely on it.** Our choice in section 6 rests on the cost of each method, not on what Apple does.

## 3. The hour

- **Blue hour has no official definition.** The most cited band is the sun **4° to 8° below the horizon** ([Wikipedia, "Blue hour"](https://en.wikipedia.org/wiki/Blue_hour); [timeanddate.com, "Blue hour"](https://www.timeanddate.com/astronomy/blue-hour.html); both read 5 November 2026). Some photography guides use −4° to −6°.
- **Our hour: the sun 2° to 4° below the horizon.** Earlier than full blue hour, so the horizon still holds a warm band under a deepening blue zenith, and dark enough that lamps outshine the sky. This is the moment temple lamps are lit, the "temple dusk" that `frontend.md` section 8a names as one of the three layers the Tamil roots enter through. The scene's `blue` grade already uses −3.5°; the hero films use that grade, not the default.
- **Checked, not assumed.** In each final frame the sky's brightest band sits at the horizon and is warmer than the zenith (hue measured in the frame, written in the commit), and no lamp is brighter than its own halo can carry without clipping.

## 4. The light

- **Lamps are the hero light.** A candle's flame is about **1,800 to 1,900 K** ([Light11, "Colour temperature"](https://light11.eu/info/about-light/lamps/colour-temperature); [Optica, "Why are candle flames yellow?", June 2016](https://www.optica-opn.org/home/articles/volume_27/june_2016/departments/why_are_candle_flames_yellow/); both read 5 November 2026). No measured figure for a diya was found (a gap, below); a cotton wick in oil burns in the same range, so lamps are lit by the Blackbody node at 1,850 K with a small spread (1,750 to 1,950 K) so no two are identical.
- **Haze carries the glow.** Blender 5.0 (18 November 2025) made **unbiased null-scattering** the default for volumes in Cycles: no step size to tune, no blocky artefacts where volumes overlap ([Blender 5.0 release notes: Cycles](https://developer.blender.org/docs/release_notes/5.0/cycles/), read 5 November 2026). A thin, low-lying world volume (denser near the ground, falling off with height) lets each lamp and the floodlit tower throw visible light into the air, which is what reads as "dusk" more than any sky colour. The scene already builds this for the hall (`dust`); it extends to the courtyard.
- **Glow in the camera, not painted.** The compositor's Glare node (Bloom, or the slower and more physical Fog Glow) gives each lamp the bloom a real lens gives it ([Blender manual, Glare node](https://docs.blender.org/manual/ko/dev/compositing/types/filter/glare.html); [Bloom added, pull request #119128](https://projects.blender.org/blender/blender/pulls/119128); both read 5 November 2026). One setting for the whole film; never a glow added by hand to one frame.
- **Tone.** AgX, Blender's default since 4.0, keeps saturated highlights from shifting hue the way older transforms did ([BlenderNation, 5 September 2023](https://www.blendernation.com/2023/09/05/filmics-successor-new-agx-view-transform-in-blender-4-0/), read 5 November 2026): lamp flames stay amber, not yellow-white. The sky model outputs physical values, so exposure is set per hour, as the scene already does ([Blender developer forum, "New sky texture"](https://devtalk.blender.org/t/new-sky-texture/12708?page=26), read 5 November 2026).

## 5. The camera

- **One move, physically moved.** A camera that travels (a push-in) keeps the true depth between foreground and tower; a zoom flattens it ([Morphic glossary, "Push in"](https://morphic.com/ai-glossary/Push-In), read 5 November 2026; a vendor glossary, the weakest source here, and only a statement of optics). So the film is one continuous dolly at walking height, never a zoom and never a cut.
- **The journey proposed** (shots that already exist in `vimana.py`, joined by one path): from outside the gateway down the processional path (`approach`), through the hall's edge where two pillars frame the tower (`threshold`), ending on the tower lit against the dusk. The `aerial` shot is left out: a drone's view is a tourism film, not a person arriving.
- **Slow, and that has a cost.** The camera positions of `approach` and `threshold` are 53 m apart in the scene. Scrolled in 8 seconds, that is about 6.6 m/s, a cycling pace; a walk is about 1.4 m/s. To read as arriving, not flying, the path starts nearer the gateway, or the film takes more scroll, or both; which one is judged on the first test film, not decided here.

## 6. Life, and how the film reaches a phone

- **What moves.** Mist drifting across the paving, lamp flames breathing, a few leaves of the thoranam turning, one flock of birds crossing once. Each is simulated in the scene and baked into the frames, so it is real (the birds' flight is a flight, not a sprite) and costs the phone nothing.
- **What does not.** Nothing moves for its own sake (section 8c); no particle storm, no lens flare.
- **Frames, not a video.** Scrubbing a video makes the player decode from the last keyframe, which one community guide puts at 50 to 150 ms behind the scroll depending on codec and keyframe distance, against drawing an already decoded image, which it calls "synchronous and sub-frame-cheap" ([skills.sh, "Image sequence scrubbing"](https://www.skills.sh/avnehsbhatia/ultraui/image-sequence-scrubbing), read 5 November 2026; not measured by us). Encoding every frame as a keyframe removes the seek cost but multiplies the file size ([Maglr, "Preparing your video for scrub on scroll"](https://help.maglr.com/en/article/preparing-your-video-for-scrub-on-scroll-1o5jbvr/), read 5 November 2026). We keep the canvas and image-sequence approach the landing already uses, loading the frames nearest the scroll position first.
- **Scroll in CSS now works everywhere.** MDN marks `animation-timeline` as **Baseline 2026, newly available since October 2026** ([MDN, `animation-timeline`](https://developer.mozilla.org/en-US/docs/Web/CSS/animation-timeline), read 5 November 2026). This settles the "Firefox unclear" left open in `FRONTEND_RESEARCH_2026.md` section B4: the glass cards and text can enter on CSS scroll timelines with no script; only the canvas needs JavaScript.
- **Reduce motion and no JavaScript** show one still frame, the film's last, with the page complete around it (section 8c, D-157).

## 7. The product in the world

- **Glass cards sit where the frame is calm.** Translucency fights legibility; even Apple's answer for Liquid Glass leans on accessibility settings that raise contrast ([MobileSyrup, 10 June 2025](https://mobilesyrup.com/2025/06/10/how-apple-is-making-sure-liquid-glass-as-legible-as-possible/), read 5 November 2026; `UI_STYLES_2026.md` covers Liquid Glass in full). So each card is placed over sky or shadow, never over a lamp or the carved tower; its text contrast is **measured against the brightest frame it passes over** and holds 4.5:1 (section 6), not only against the average.
- **Cards carry the product's real screens** (section 8a): the deal board, a deal memo, a payment marked paid. The world is the setting; the product is what is said.

## 8. What made the prototype "school ppt", so it is never repeated

| Fault | Rule that prevents it |
|---|---|
| Cartoon props (the bananas), flat colours | Nothing enters the frame below the render bar (section 8b, check 4); fewer things, all real |
| Noon light, everything equally lit | One hour (section 3); lamps and the floodlit tower carry the frame, the rest falls into shadow |
| An empty plaza | Foreground, middle ground, background in every frame: pillars or steps near, the path in the middle, the tower far |
| Everything moving | Section 6: the few things that move, move because they would |

## 9. Decisions this asks for

**Decided 5 November 2026 (D-164):** decision 1, the three shots in that order; decision 3, still at rest. Decision 2 waits for the benchmark.

1. **The journey**: the three shots in section 5, in that order, or another. *(Adhi)*
2. **The frame budget**: how many frames and how many bytes at each width. The standard already says this is set on the budget Android before the scene is built (section 8b); the proposal to measure is 96 frames, with the first frame painted as the page's largest content. *(set by the benchmark, then Adhi)*
3. **Life at rest**: section 8c says nothing loops. A still world at rest is the default here; a few seconds of mist drifting at rest would need 8c changed. *(Adhi; the recommendation is still at rest, alive on scroll)*

## 10. The place as it is (6 November 2026)

Adhi asked for the temple to look exactly like Tamil architecture, its detail and definition included. That needs the measured survey and real photographs, not memory.

**The sources.**
- **Pichard, *Tanjavur Brhadisvara: An Architectural Study*** (IGNCA and EFEO, 1995, 244 pages, line drawings): the measured study of the temple. Only IGNCA's published excerpts were read ([IGNCA, the book](https://ignca.gov.in/divisionss/kalakosa/kalasamalocana/ksetra-sampada-regional-heritage-series/tanjavur-brhadisvara-an-architectural-study-3/); [IGNCA, "Glimpses of content"](https://ignca.gov.in/?p=7350); both read 6 November 2026). The book itself is owed: its drawings give the tier-by-tier dimensions this scene still estimates.
- **Balasubrahmanyam (1975)**, as cited in [Wikipedia, "Brihadisvara Temple, Thanjavur"](https://en.wikipedia.org/wiki/Brihadisvara_Temple,_Thanjavur) (read 6 November 2026): a secondary route to a primary source, used where Pichard's excerpts are silent.

**What they give, and what the scene had wrong.**

| | Source | The scene before 6 November |
|---|---|---|
| Courtyard | "length twice its width"; the eastern half open, the Nandi pavilion at its centre (Pichard); about 241 by 122 m (Balasubrahmanyam) | about 240 by 190 m |
| Cloister | ground floor only, 5.61 m deep; two rows of plain square monolithic pillars, 38 cm a side, 2.02 m high, 2.96 m from the courtyard, about 1.94 m apart; the wall shows two levels of pilasters and two cornices (Pichard) | a 6.5 m wall, 90 cm posts 3.2 m apart |
| The halls | "a low and long pillared hall" and a vestibule before the tower (Pichard); maha- and mukha-mandapa square, on the axis (Balasubrahmanyam) | the hall built on the tower's side, the tower seen side-on |
| Tower | 30.18 m square at the base, 63.4 m high, thirteen square tiers above the walls (Balasubrahmanyam) | 29.2 m base; the height to be measured in the scene |
| Crown | octagonal griva and shikhara on a capstone 7.77 m square; the stupi 3.81 m (Balasubrahmanyam) | round |
| Socle | "nearly two metres" (Pichard); upapitha 1.4 m and adhishthana 3.6 m (Balasubrahmanyam; the article's own figures conflict) | to be checked |

**From the photographs** (twenty, from Wikimedia Commons, kept privately with an index of each one's source and licence, section 8a):
- the granite reads warm tan to ochre, and cream-gold under the night floodlights;
- the central bay of each wall storey holds a tall stone lattice window, not a niche;
- the gable of each lower tier's central pavilion is a large horseshoe arch filled with a radiating fan, edged with flame tongues;
- the whole tower is floodlit evenly from base to crown at night, and the blue-hour sky behind it is a near pure blue.

**Measured against the blue-hour reference.** Sky: hue 215°, saturation 0.99, lightness 0.31. Tower: lightness 0.49 high, 0.42 low, hue 31° to 32°. The dusk pass of 5 November measured sky saturation 0.19 and tower lightness 0.31 and 0.20: right in hue, half as bright, and grey where the real sky is blue.

## 11. Gaps

- No measured colour temperature for a diya; the candle's 1,800 to 1,900 K stands in.
- Apple's current method (video or frames) is unconfirmed.
- The film's frame time and bytes on the budget Android are not yet measured; nothing in section 6 is a measured number of ours.
- Pichard's book itself, beyond IGNCA's excerpts: the tier-by-tier dimensions are still estimated.
- The Morphic and svilenkovic sources are a vendor glossary and one designer's opinion; each is used only where it agrees with a stronger rule already in the standard.
