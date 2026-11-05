# The futurist frontend: what is new, what is ready, and what we refuse

**For:** the founders and whoever builds the frontend, to put Colyv ahead of every competitor in what the web and phones can now do, without betting the product on something unfinished. **Version 1, 31 October 2026**, from web searches made that day and `docs/research/FRONTEND_RESEARCH_2026.md` (28 October). **"Futurist" here means the newest thing that is shipped and stable for our users, used on purpose**, not the newest thing announced. That is D-047's upgrade rule, applied to the frontend.

**The four shelves.** Every capability below sits on one:
- **Use now**: stable in the browsers and phones our users have.
- **Use as an enhancement**: shipped in some engines; the page is complete without it.
- **Watch**: promising, not ready; each has an adopt-when trigger.
- **Refuse**: hype, or wrong for Colyv, with the reason.

**Every browser-support figure below is read from MDN's browser-compat-data** (the data behind MDN and caniuse; [repository](https://github.com/mdn/browser-compat-data)), on 31 October 2026, and re-read when its item is built.

---

## 1. Use now

| Capability | State (sources) | What Colyv does with it |
|---|---|---|
| **React 19.3 `<ViewTransition>`** | Stable since 9 September 2026, DOM only ([React 19.3](https://react.dev/blog/2026/09/09/react-19-3)) | Cards that open into their page: a deal, a memo, a Passport |
| **Same-page View Transitions** | Chrome 111, Firefox 144, Safari 18 | Tab switches, filters, the deal board's columns |
| **CSS scroll-driven animations** | Chrome 115, Firefox 159, Safari 26: every engine | Scroll reveals off the main thread (`docs/research/FEEL_AND_MOTION_2026.md` section 4) |
| **Anchor positioning** | Chrome 125, Firefox 147, Safari 26: every engine | Popovers and menus that stay attached to their trigger, without a positioning library |
| **Next.js 16** with Turbopack the default and the React Compiler stable (opt-in) | Released 21 October 2025; 16.3 adds build caching ([Next.js 16](https://nextjs.org/blog/next-16); [Next.js 16.3](https://nextjs.org/blog/next-16-3-turbopack)) | The website's framework (`frontend.md` section 2); the compiler switched on after a measured test |
| **Popover API** | Chrome 114, Firefox 125, Safari 17 | Menus, tooltips and the command menu without a positioning library |
| **OKLCH colour** | CSS Color 4, about 96% of browsers by one count ([frontend checklist](https://frontendchecklist.io/rules/css/color-oklch)) | The whole token system (`docs/research/COLOUR_PSYCHOLOGY_2026.md` section 6) |
| **`text-wrap: balance`** | Chrome, Edge, Firefox 121, Safari 17.5 | Every heading (`docs/research/TYPOGRAPHY_2026.md` section 5) |
| **WebGPU with a WebGL 2 path** | Chrome, Edge, Chrome on Android 12+, Safari 26; Firefox partial ([web.dev](https://web.dev/blog/webgpu-supported-major-browsers)) | Live 3D only where people interact (`docs/research/FEEL_AND_MOTION_2026.md` section 7) |
| **Generated share images** | Next.js `ImageResponse`, per page, at build or request time ([Next.js docs, 16.3.8](https://nextjs.org/docs/app/api-reference/functions/image-response.md)) | Every Passport and city page shared on WhatsApp shows a designed card with the creator's real, public facts |
| **Passkeys** | The backend is built, switched off until the domain (item 79) | Sign in with a fingerprint on both apps and the web |
| **Android 16 Live Updates and iOS Live Activities** | Progress-style notifications on the lock screen ([proandroiddev](https://proandroiddev.com/live-updates-in-android-16-exploring-the-next-evolution-of-notifications-1a5cf5de2068)) | A deal's stage and a payment's due date on the lock screen: "Proof approved · payment due 7 Nov". **No competitor found does this for creator deals** |

## 2. Use as an enhancement (complete without it)

| Capability | State | What Colyv does, and the fallback |
|---|---|---|
| **Cross-page View Transitions** (`@view-transition`) | Chrome 126, Safari 18.2; **not Firefox** ([Chrome](https://developer.chrome.com/docs/web-platform/view-transitions/cross-document)) | Public pages (landing, Passport, city) glide between each other; a clean cut in Firefox |
| **Customizable `<select>`** (`appearance: base-select`) | Chrome 135, Safari 27; Firefox 149 behind a flag | Our styled select where supported, the native one elsewhere: both accessible |
| **`text-wrap: pretty`** | Chrome 117, Safari 26; not Firefox | Paragraphs without orphans |
| **`corner-shape: squircle`** | Chrome 139; Firefox and Safari in preview builds only | Continuous-curve corners; plain radius elsewhere |
| **Speculation Rules (prerender)** | Chrome 109; Safari 26.2 behind a flag; Firefox preview only; Next.js prefetches by default ([Sentry](https://blog.sentry.io/less-than-100ms-e-commerce-instant-loads-with-speculation-rules-api)) | Public pages prerendered on intent in Chrome, which is most of our users |
| **`prefers-reduced-transparency`** | Chrome 118; Firefox behind a flag; not Safari | Glass becomes solid for people who ask; our own "solid surfaces" setting covers the rest (`docs/research/UI_STYLES_2026.md` section 5.1) |
| **Device-aware quality** (`navigator.deviceMemory` Chrome 63 only; Save-Data; first-second frame time everywhere) | Device Memory in Chrome only | "Adaptive grandeur": the first-second frame time works in every browser, Device Memory refines it in Chrome |

## 3. Watch, with the trigger that moves each to "use"

| Capability | Why it is interesting | Adopt when |
|---|---|---|
| **Generative UI** (an assistant answering with real components): Vercel AI SDK's tool-to-component pattern, Google's A2UI, MCP Apps ([CopilotKit guide, 2026](https://www.copilotkit.ai/blog/the-developer-s-guide-to-generative-ui-in-2026); [Telus Digital](https://www.telusdigital.com/insights/data-and-ai/article/accelerating-genui-ecosystem-mcp-apps-openai-apps-sdk-and-google-a2ui)) | "Ask Colyv" (`FRONTEND_RESEARCH_2026.md` B15) could answer "who hasn't paid me?" with the real payment cards, not text | The brief builder and the MCP server (backend items 40, 41) exist; and only in the **constrained** form: the model chooses from our own registered components, never writes markup |
| **React Three Fiber v10** (WebGPU default) | Cleaner WebGPU path | It leaves alpha (`FRONTEND_RESEARCH_2026.md` B5) |
| **Gaussian splats** (Spark 2.0) | Photoreal captured objects in a three.js scene | We own an object worth capturing, with rights (the doll) |
| **Rust React Compiler** | Faster builds | It leaves experimental in Next.js |
| **APCA contrast (WCAG 3)** | Better contrast for dark mode and thin text | WCAG 3 becomes a recommendation |
| **Home-screen widgets** (what needs me today) | One glance without opening the app | The apps ship and Today proves useful |

## 4. Refuse, with the reason

| Idea | Why not |
|---|---|
| AI-generated images on pages | Every visual is made, with written rights (D-142) |
| Scroll hijacking and long pinned scrollytelling | It fights the browser's own smooth scroll and people's settings (`FEEL_AND_MOTION_2026.md` section 4) |
| Always-running WebGL backgrounds | Battery and heat on budget phones for decoration |
| Neumorphism, claymorphism, neo-brutalism | `UI_STYLES_2026.md` section 2.6 |
| A WebView app shell | 60 fps cap and web costs inside an app (`FEEL_AND_MOTION_2026.md` section 1) |
| Voice-first or chat-only interfaces | Deals need terms people can see and check; chat is an addition, never the way in |
| An unconstrained generative UI (the model writes HTML) | Inconsistent, unsafe, and impossible to test |
| Crypto, NFT "certificates" of deals | The deal record's seal and daily outside timestamp already prove it; we hold no money (constraint 1) |

## 5. Where this puts Colyv ahead

Against the competitors in `docs/COMPETITIVE_LANDSCAPE.md`, the futurist pieces that no one in Indian creator marketplaces was found to have:
1. **A deal on the lock screen** (Live Updates and Live Activities).
2. **A seal generated from the deal's own fingerprint**, drawn closing across the fold (`docs/PROPOSAL_FRONTEND_ARCHITECTURE.md` section 5).
3. **Instant public pages**: prerendered on intent, gliding between each other, readable without JavaScript.
4. **Share cards generated per Passport**, so a creator's link in a WhatsApp group already looks professional.
5. **Adaptive grandeur**: the richest version a phone can hold, measured in its first second.
6. **"Ask Colyv" answering with real components**, once the backend's assistant pieces exist.

## 6. Decisions this file asks for

| # | Decision | Recommended |
|---|---|---|
| 1 | The four shelves as the rule for any new capability | Yes |
| 2 | Lock-screen deal stages in the apps' first release | Yes |
| 3 | Generated share images for Passports and city pages | Yes |
| 4 | Speculation Rules on public pages | Yes, measured |
| 5 | "Ask Colyv" only in the constrained form | Yes, when its backend exists |

## 7. How this file stays true

- **Support moves monthly**: each row is re-read from MDN's browser-compat-data when its item is built, and this file updated in the same change.
- **"No competitor was found to have it"** rests on `docs/COMPETITIVE_LANDSCAPE.md`'s research; each claim in section 5 is re-checked against the competitors' current apps before it is said in public (`docs/standards/legal.md` section 1).
- **Generative UI**: the sources are mostly vendors, which is why it sits on "Watch" with a trigger, not on "Use".

## Sources (read 31 October 2026)

Every source is linked where it is used.
