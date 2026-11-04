# Feel and motion: what "smooth as butter" is, and how we prove ours is

**For:** whoever designs or builds motion, scrolling, transitions or 3D in the website or the apps; and the founders, to judge the frontend by numbers instead of by feel alone. **Version 1, 31 October 2026**, from about 25 web searches made that day (sources at the end), on top of `docs/research/FRONTEND_RESEARCH_2026.md` sections B4, B5 and B9, which this file does not repeat. **Nothing here is built yet.** Choices that need a founder are marked **(decision)** and gathered in section 13.

**Why it exists.** Adhi, 31 October 2026: the frontend must be "smooth as butter and billion times better in all aspects" than his Interview Coach site, which has scroll animations. "Smooth" is a feeling, but it has physical causes that tools can measure. This file names them, says what the best sites do, and turns each into a rule with a test.

**How strong the evidence is.** The physics of frames and the browser's rendering pipeline are documented by Chrome and WebKit engineers; browser support is read from MDN's browser-compat-data; springs from Google's and Apple's own sources: strong. Response-time limits rest on decades-old research restated by Nielsen in 2024: strong for the 0.1 s limit, weaker for the rest. Apple does not publish how its product pages animate, so section 6 uses the community-documented method and our frame test proves it on our scenes. How it feels to our people is settled by `docs/research/PEOPLE_RESEARCH_KIT.md`.

---

## 1. What smoothness is, physically

- **A frame is a deadline.** A 60 Hz screen shows a new picture every 16.7 ms; a 120 Hz screen every 8.3 ms. Everything the page does between two pictures (scripts, style, layout, paint, compositing) must fit inside that time, or the screen shows the old picture again. That repeat is a **dropped frame**, and a run of them is what people feel as stutter or "jank".
- **Chrome defines it the same way.** Its graphics metrics count dropped frames as the share of expected screen updates that were not delivered during an interaction, and jank as a change in throughput between consecutive frames ([Chromium graphics metrics](https://chromium.googlesource.com/chromium/src/+/refs/heads/main/docs/speed/graphics_metrics_definitions.md)). Chrome's team proposed "percent dropped frames" as a smoothness metric, averaged and as a worst one-second window ([web.dev, older article](https://web.dev/articles/smoothness)).
- **The browser itself is getting smoother.** Google reports Chrome on Android cut janky scrolls by 48% between 2023 and 2026 ([Google, July 2026](https://blog.google/chromium/smoother-scrolling-how-we-halved-scroll-jank-in-chrome-on-android/)). The browser's own scroll is now the smoothest thing on a page; anything that replaces it starts behind.
- **The two properties that are almost free.** Only `transform` and `opacity` can be animated by the compositor alone, without layout or paint on the main thread. Animating anything else (width, top, margin, box-shadow) re-runs layout or paint every frame, and on a budget phone that is where frames are lost ([web.dev: compositor-only properties](https://web.dev/articles/stick-to-compositor-only-properties-and-manage-layer-count); [Shopify performance guidance](https://shopify.dev/docs/storefronts/themes/best-practices/performance/use-transform-for-animations)). Each promoted layer costs memory, so promotion is targeted, not blanket.
- **120 Hz is not the default everywhere.** Safari renders pages near 60 fps by default on ProMotion iPhones, iPads and Macs, behind a setting ("Prefer Page Rendering Updates Near 60fps") that people can turn off; apps that show web pages inside a WKWebView stay capped at 60 Hz with no public way out. WebKit's own tracker records this: bug 294338, open since 11 June 2025, last updated 17 September 2026, asks for a public API to lift the WKWebView cap; a WebKit engineer notes an internal preference exists ([WebKit bug 294338](https://bugs.webkit.org/show_bug.cgi?id=294338); [iGeeksBlog on the Safari setting](https://www.igeeksblog.com/this-hidden-safari-setting-unlocks-120hz-scrolling/)).

**What this means for Colyv.**
1. **Design for 60, let 120 happen.** Every animation is built to hold 60 fps on the budget Android reference phone; on a 120 Hz screen the browser simply gets more frames.
2. **Only `transform` and `opacity` move.** A lint rule fails any animation or transition of another property, except colour on hover, which is small and allowed by name.
3. **The apps are native, never a web page in a shell.** A WebView app inherits the 60 fps cap and the web's costs; this supports `docs/standards/frontend.md` section 2 (native apps).

## 2. How fast a response must be to feel instant

- **0.1 second** is the limit for feeling that you caused the result directly; **1 second** keeps the flow of thought, though the delay is noticed; **10 seconds** is the limit of attention, past which a progress indicator and a way out are needed. The limits come from Robert Miller (1968) and were restated by Nielsen in 2024 ([UX Tigers, 2024](https://www.uxtigers.com/post/time-scales-ux); [NN/g video](https://www.nngroup.com/videos/3-response-time-limits-interaction-design/)).
- **The "Doherty threshold" (400 ms)** comes from a 1982 IBM paper and is widely quoted as a productivity limit; its empirical basis is thin and it is best treated as a historical rule of thumb ([behavioural glossary](https://atticusli.com/behavioral-science-glossary/doherty-threshold/)). We do not cite it as evidence.
- **Skeleton screens are not proven to make waits feel shorter.** In Viget's 2017 test (136 people) skeletons felt the *longest* of blank, spinner and skeleton; another study found the opposite; one small write-up found left-to-right shimmer felt shorter than pulsing ([Viget](https://www.viget.com/articles/a-bone-to-pick-with-skeleton-screens); [UX Collective summary](https://uxdesign.cc/what-you-should-know-about-skeleton-screens-a820c45a571a)). What skeletons reliably do is hold the layout still and say what is coming.
- **Showing the work can raise the value of a wait.** Buell and Norton (Management Science, 2011, five experiments) found people valued a slower result more when the site showed the work being done, the "labor illusion" ([INFORMS](https://pubsonline.informs.org/doi/10.1287/mnsc.1110.1376)).

**Rules for Colyv.**
1. **Every tap answers within one frame**: the pressed state shows on the next frame, whatever the network does (the 0.1 s limit, met with room to spare).
2. **Data in under about 300 ms appears with no loader at all**; a loader that flashes for a moment reads as a flicker. Past that, a skeleton shaped like the content appears, with left-to-right shimmer. The 300 ms figure is our starting point to tune by test, not a published number.
3. **Waits we cannot shorten show the honest work**: a proof file being cleaned says "removing location data from your photo", because it is true and, per Buell and Norton, it helps. Never a fake progress bar.
4. **Interaction to Next Paint stays at or under 150 ms at the 75th percentile** (already `frontend.md` section 4), and taps in the app aim at 100 ms.

## 3. Motion physics: springs and curves

- **Apple's model.** Since WWDC23 Apple describes a spring by two numbers, **duration** and **bounce** (−1 to 1). Bounce 0 is the general-purpose default; around 0.15 hardly feels bouncy; around 0.3 is noticeable; the session notes advise caution with durations much above about 0.4 s for interface elements. Springs keep motion continuous when a gesture hands over velocity, which eased curves cannot ([WWDC23 "Animate with springs" notes](https://wwdcnotes.com/notes/wwdc23/10158); [UIKit API](https://developer.apple.com/documentation/uikit/uiview/animate(springduration:bounce:initialspringvelocity:delay:options:animations:completion:))).
- **Google's model.** Material 3 uses **springs for spatial movement** (position, size, shape) and **springs that never overshoot for effects** (opacity, colour). The values, read from Google's own Compose source (`ExpressiveMotionTokens` and `StandardMotionTokens`, androidx main branch, 31 October 2026):

| Spring | Expressive: damping, stiffness | Standard: damping, stiffness |
|---|---|---|
| Spatial, fast | 0.6, 800 | 0.9, 1400 |
| Spatial, default | 0.8, 380 | 0.9, 700 |
| Spatial, slow | 0.8, 200 | 0.9, 300 |
| Effects, fast / default / slow | 1.0 (no overshoot); 3800 / 1600 / 800 | the same |

  Sources: [ExpressiveMotionTokens.kt](https://raw.githubusercontent.com/androidx/androidx/androidx-main/compose/material3/material3/src/commonMain/kotlin/androidx/compose/material3/tokens/ExpressiveMotionTokens.kt); [StandardMotionTokens.kt](https://raw.githubusercontent.com/androidx/androidx/androidx-main/compose/material3/material3/src/commonMain/kotlin/androidx/compose/material3/tokens/StandardMotionTokens.kt). Third-party packages that quoted other damping values were wrong.

**Colyv's motion tokens** (to be tuned on the reference phones):
- **Spatial** (anything that moves or resizes): working screens use Google's **standard** springs (damping 0.9: settled, no visible bounce); the few joyful moments (a deal agreed) use the **expressive** default (0.8, 380). Expressed in Apple's terms for the web and iOS: `snappy` about 0.25 s, bounce 0; `smooth` about 0.35 s, bounce 0; `lively` about 0.4 s, bounce 0.15. Dragged things keep the finger's velocity.
- **Effects** (opacity, colour, blur): critically damped (1.0), so they never overshoot, or the eased durations in `frontend.md` section 8c.
- **Signature moments** (the seal closing, the fold): authored timelines, 400 to 800 ms, one per page.
- **Nothing loops** except a loading state, and every movement ends in a still pose (the temple's karanas, `docs/research/TAMIL_DESIGN_ROOTS.md`).

## 4. Scroll: never hijack it

- **CSS scroll-driven animations** tie an animation to scroll position in CSS, running off the main thread: **Chrome 115, Safari 26 and Firefox 159**, so every engine now ships them (MDN browser-compat-data, `css.properties.animation-timeline`, read 31 October 2026: [BCD](https://github.com/mdn/browser-compat-data/blob/main/css/properties/animation-timeline.json)); they were an Interop 2026 focus area ([web.dev: Interop 2026](https://web.dev/blog/interop-2026)). Forum posts saying Firefox kept them behind a flag are out of date.
- **Libraries.** Motion's `scroll()` can run on the browser's native scroll timeline; GSAP's ScrollTrigger measures and updates every frame but is the most capable for pinned, scrubbed scenes. Motion's own site claims its scroll features at about 0.5 to 2.5 KB against about 12 KB for ScrollTrigger; that is the vendor's claim, and no independent frame-time benchmark was found ([Motion: migrating from GSAP](https://motion.dev/docs/migrate-from-gsap-to-motion); [OpenReplay comparison](https://blog.openreplay.com/motion-vs-gsap/)).
- **Smooth-scroll libraries** (Lenis and others) re-time the page's scroll for a gliding feel. Lenis says it wraps the browser's own scroll, so sticky positioning, anchors and accessibility keep working; no measured comparison with native scroll on interaction latency was found ([Lenis README](https://github.com/darkroomengineering/lenis/blob/main/README.md)). Its own docs warn that checking nested scroll areas on every event costs performance.

**Rules for Colyv.**
1. **Native scroll by default, everywhere.** It is the smoothest thing the browser has (section 1), it respects every person's settings, and it is what Android users' thumbs expect.
2. **Scroll-linked effects in CSS** (`animation-timeline`), in every engine; Motion's `scroll()` only for older browser versions; GSAP only for the pinned signature scenes, if they need it. **(decision: GSAP for the scenes, after the frame test in section 10)**
3. **A smooth-scroll library only if it wins a measured test** on the reference phones and laptop (frame drops and input latency against native), only on the landing page, and never on touch screens or with reduce motion on. **(decision)**
4. **No section pins the scroll for more than about two and a half screens** (`docs/PROPOSAL_FRONTEND_ARCHITECTURE.md` part 22, the fold prototype's lesson). Scroll never moves sideways on its own, and never snaps unless the content is a set of pages.

## 5. Moving between screens

- **Same-page View Transitions** (`document.startViewTransition`): Chrome 111, Safari 18, Firefox 144. **Cross-page** ones (`@view-transition`): Chrome 126 and Safari 18.2, **not Firefox** (MDN browser-compat-data, read 31 October 2026; [BCD: @view-transition](https://github.com/mdn/browser-compat-data/blob/main/css/at-rules/view-transition.json)); an Interop 2026 focus ([web.dev](https://web.dev/blog/interop-2026)).
- **React's `<ViewTransition>` is stable in React 19.3** (9 September 2026): "in 19.3 it's stable and ready to use"; "currently, `<ViewTransition>` only works in the DOM" ([React 19.3, read in full](https://react.dev/blog/2026/09/09/react-19-3)). The same release adds `addTransitionType`, so going forward and going back can animate differently, and Suspense reveals that animate when content arrives.

**Rules for Colyv.** Moving into a deal, a memo or a Passport animates the card into the page it opens (a shared element), so a person never loses their place. Browsers without support get a clean cut, which is complete in itself. Reduce motion turns every transition into a short fade.

## 6. Cinematic scroll scenes: frames, not live 3D

- Apple's product pages are widely reported to draw **pre-rendered image frames on a canvas**, chosen by scroll position, rather than scrubbing a video; community guides put such scenes at about 60 to 150 frames. A normal MP4 scrubs badly because its keyframes are seconds apart ([dev.to on scrubbing video](https://dev.to/alki/video-on-scroll-in-elementor-why-scrubbing-an-mp4-stutters-and-what-to-do-instead-156l); [Vulk guide, 2026](https://vulk.dev/blog/how-to-build-an-apple-style-scroll-website-with-ai)). Apple has not documented its own method; this is community practice.
- This is already the plan for the temple and the fold (`docs/PROPOSAL_FRONTEND_ARCHITECTURE.md` part 23): photoreal because the frames are path-traced in Blender, smooth because drawing an image is cheap, light because the first frame is one image and the rest stream in.

**Rules.** Frames in AVIF (WebP fallback), sized to the screen, the first frame doubling as the poster and never the page's largest paint; the rest load after the page is usable, nearest frames first; a per-scene byte budget set on the reference phone **(decision: the number)**; reduce motion and Save-Data show the poster only.

## 7. Live 3D, where it earns its place

- **WebGPU** ships in Chrome and Edge, in Chrome on Android (121 and later), and in Safari 26; Firefox 141 has it partly on desktop and **not on Android** (MDN browser-compat-data `api.GPU`, read 31 October 2026; [web.dev](https://web.dev/blog/webgpu-supported-major-browsers)).
- **Three.js's own manual** calls `WebGPURenderer` "still in an experimental state although its maturity level has been greatly improved"; it falls back to a WebGL 2 backend when WebGPU is missing; `WebGLRenderer` "is still maintained and the recommended choice for pure WebGL 2 applications"; custom `ShaderMaterial`, `onBeforeCompile` and `EffectComposer` are not supported on the WebGPU renderer ([three.js manual](https://threejs.org/manual/en/webgpurenderer)).
- **Always-on GPU effects cost battery.** Stripe's homepage gradient is a small WebGL program; the only evidence on its cost is one forum complaint about battery drain, which is anecdotal ([GSAP forum](https://gsap.com/community/forums/topic/24837-animating-gradients/)).

**Rules.** Live 3D only where a person interacts (turning the seal, perhaps); a WebGL 2 path always, which the WebGPU renderer's own fallback gives; no custom shader material that the WebGPU renderer cannot run (node materials instead); rendering paused off screen, in a hidden tab, and when idle; quality chosen by device class (memory, Save-Data, frame time in the first second), never one size for all.

## 8. Characters and illustrated motion

- **Rive** files carry state machines, so an animation reacts to the app (a character that nods when a deal is agreed); **Lottie** plays a fixed animation and has the larger ecosystem. Size claims (Rive files 10 to 15 times smaller) come from vendors on both sides ([LottieFiles](https://lottiefiles.com/blog/working-with-lottie-animations/lottiefiles-or-rive); [Callstack](https://callstack.com/blog/lottie-vs-rive-optimizing-mobile-app-animation)). Text and controls always stay real HTML, never inside the animation (`FRONTEND_RESEARCH_2026.md` B4).

**Rule.** Rive for the thalaiyatti bommai and any reacting character, if it is made in 2D at all **(decision: Rive or a 3D scene for the doll)**; no Lottie unless a specific asset needs it.

## 9. The apps

- **React Native**: Reanimated 4 brings CSS-style animations and runs only on the New Architecture; its worklets moved to a separate package ([heise](https://heise.de/-10502942); [freeCodeCamp](https://www.freecodecamp.org/news/how-to-create-fluid-animations-with-react-native-reanimated-v4/)).
- **Flutter**: the Impeller renderer is the default on Android 10 and later and removed the shader-compilation stutter Skia had on first use of an effect; Flutter's 2026 roadmap completes the move ([Flutter 2026 roadmap](https://flutter.dev/blog/flutter-darts-2026-roadmap); [State of Flutter 2026](https://devnewsletter.com/p/state-of-flutter-2026/)).
- **The lock screen.** Android 16's Live Updates (a progress-style notification on the lock screen and status bar) and iOS Live Activities show a journey's stage without opening the app ([proandroiddev](https://proandroiddev.com/live-updates-in-android-16-exploring-the-next-evolution-of-notifications-1a5cf5de2068); [TechRadar](https://www.techradar.com/computing/software/android-16s-answer-to-ios-live-activities-is-coming-soon-here-are-the-apps-itll-support-including-google-maps)).

**Rules.** Whichever framework is chosen **(decision, both founders, by 15 November)**, every animation runs on the UI thread, holds 60 fps with under 1% slow frames on the budget Android (`frontend.md` section 4), and has haptics only where a physical act completes (a deal sealed, a payment confirmed).

## 10. How we measure it (the tests)

- **In the lab, on every pull request:** a Playwright test records a performance trace (Chrome DevTools Protocol) while it scrolls the landing page and runs each signature scene on a throttled CPU profile; it counts expected against presented frames, as Chrome's own trackers do ([Chromium: investigating jank](https://chromium.googlesource.com/chromium/src/+/refs/heads/main/docs/speed/debug-janks.md)), and **fails above 1% dropped frames or any frame over 50 ms**.
- **In the field:** the web-vitals library's attribution build reports Interaction to Next Paint with Long Animation Frame entries, which name the script behind a slow interaction; Long Animation Frames are in **Chrome 123 and Chromium browsers only**; Firefox and Safari do not have them (MDN browser-compat-data, read 31 October 2026), so field attribution covers Android Chrome, which is most of our users ([web.dev: slow interactions in the field](https://web.dev/find-slow-interactions-in-the-field/); [Chrome: LoAF](https://developer.chrome.com/docs/web-platform/long-animation-frames)).
- **On the phones:** the same journeys on the reference devices, with the platforms' frame tools, every release.
- **A test that the test works:** a deliberately bad animation (animating `top`) is committed to a fixture page and must fail the frame check, as backend rules are broken on purpose.

## 11. Motion and people who are hurt by it

- **WCAG 2.3.3 (AAA):** motion triggered by an interaction can be turned off unless it is essential; parallax is the classic non-essential example; vestibular disorders cause dizziness, nausea and headaches ([W3C: Understanding 2.3.3](https://w3c.github.io/wcag/understanding/animation-from-interactions)). The CSS `prefers-reduced-motion` query is a listed sufficient technique (C39).
- **We meet the AAA level, not only AA:** every animation, transition and scene has a reduced version (`frontend.md` section 8c); parallax and scroll-scrubbed scenes show their still; browser tests run with motion on and off.

## 12. Colyv against Interview Coach, measured where we can

Interview Coach AI is Adhi's own site and the floor, not the bar (`frontend.md` section 8a). What was measured on 28 October 2026, and what Colyv commits to:

| Dimension | Interview Coach (measured 28 October) | Colyv's gate |
|---|---|---|
| First heading on a throttled phone | 14.8 s | Largest paint ≤ 2.0 s on slow 4G (about 7 times faster) |
| Without JavaScript | An empty page to search engines and link previews | Every public page complete without JavaScript, tested in CI |
| Contrast | Low in places | Body text ≥ 7:1, checked for every token pair in CI |
| Scroll animation | A particle scroll story; not measured | Dropped frames ≤ 1%, no frame over 50 ms, tested in CI on a throttled profile |
| Reduce motion | Not checked | AAA: every motion has a calm version, tested both ways |
| Tests | 41 unit, 48 Playwright with axe | Every component state screenshot-tested, every journey end to end on slow 4G, frames, budgets |

"Billions of times better" cannot be measured; each row above can, and the finish line (`docs/FRONTEND_COMPLETE.md`) holds an item for each.

## 13. Decisions this file asks for

| # | Decision | Recommended |
|---|---|---|
| 1 | Native scroll everywhere; a smooth-scroll library only after a measured win, landing page only | Yes |
| 2 | GSAP for the pinned signature scenes; Motion for everything else | Yes, after the frame test |
| 3 | Motion tokens: springs (duration, bounce) for space, eased durations for effects | Yes |
| 4 | The frame test (≤ 1% dropped, no frame over 50 ms) as a CI gate | Yes |
| 5 | The byte budget per frame-sequence scene | Set by the reference-phone benchmark |
| 6 | Rive or 3D for the thalaiyatti bommai | After the doll is bought and photographed |

## 14. Checked against primary sources, and what only a test can settle

**Checked on 31 October 2026 against primary sources:** browser support from MDN's browser-compat-data (scroll timelines, both kinds of View Transition, WebGPU, Long Animation Frames); React 19.3 from react.dev; Material's springs from Google's Compose source; three.js from its own manual.

**Settled only by our own tests, each an item in `docs/FRONTEND_COMPLETE.md`:**
- **How it feels to our people**: the task and five-second tests, run with the kit in `docs/research/PEOPLE_RESEARCH_KIT.md`.
- **The real numbers on real phones**: the reference bench, chosen in `docs/research/REFERENCE_DEVICES_2026.md`.
- **GSAP against Motion against CSS, and native scroll against a smooth-scroll library**: no independent benchmark exists anywhere, so section 10's frame test is how we decide.
- **Apple's own technique** is not published; section 6 uses the community-documented method, which our frame test then proves or rejects on our scenes.
- **Firefox** lacks cross-page transitions and Long Animation Frames; every rule above degrades there to a complete, still page.

## Sources (read 31 October 2026)

Every link is given inline where it is used. Secondary sources are labelled where a finding rests on them alone.
