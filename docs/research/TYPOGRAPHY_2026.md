# Typography: the faces, the numbers and the rules

**For:** whoever sets type in the website, the apps, the share images or the 3D scenes. **Version 1, 31 October 2026**, from web searches made that day. Type is about 90% of what a product shows; this file chooses how ours reads. **Nothing here is decided**; section 7 lists what needs a founder.

**How strong the evidence is.** Font roundups are mostly SEO content; facts here (licences, axes, browser support) are taken from the font projects, Fontsource and browser documentation where possible, and marked where only a blog says so.

---

## 1. The roles

| Role | Job | Where |
|---|---|---|
| **Display** | Headlines with character: the landing page's opening, section titles, the Passport's name | Marketing pages and signature moments only |
| **Interface sans** | Everything people read and use: labels, body, tables, forms | Everywhere else, both apps |
| **Mono** | Fingerprints, references, UPI IDs, codes | Where exactness matters |
| **Tamil** | Ready for when Tamil returns (D-054 is English only today), and for the seal's inscription now | The seal scene; later the whole product |

One family per role, at most three families in total, so the page stays fluent (`docs/research/INTERFACE_PSYCHOLOGY_2026.md` section 2).

## 2. The interface sans: candidates

**Measured from the font files themselves** (Google Fonts' repository, read with fontTools on 31 October 2026), not from articles:

| Face | Variable axes | Tabular figures (`tnum`) | ₹ sign | Tamil | Licence (from the file) |
|---|---|---|---|---|---|
| **Inter** | optical size 14–32, weight 100–900 | Yes | Yes | No | SIL OFL 1.1 |
| **Geist** | weight 100–900 | Yes | Yes | No | SIL OFL 1.1 |
| **Geist Mono** | weight 100–900 | Not needed: every figure is one width | Yes | No | SIL OFL 1.1 |
| **Fraunces** (display) | optical size 9–144, weight 100–900, softness, "wonk" | No (display only, so not needed) | Yes | No | SIL OFL 1.1 |
| **Noto Sans Tamil** | weight 100–900, width 62.5–100 | No | Yes | Yes | SIL OFL 1.1 |
| **Anek Tamil** | weight 100–800, width 75–125 | Yes | Yes | Yes | SIL OFL 1.1 |
| **Mukta Malar** (Ek Type) | None: seven static weights, 200–800 | Not checked: static only | — | Yes | OFL ([Google Fonts metadata](https://raw.githubusercontent.com/google/fonts/main/ofl/muktamalar/METADATA.pb)) |

- **Inter**: widely called the default UI face, built for screens and legible at small sizes; its optical-size axis is what makes it closest to SF Pro Display for headlines ([fontalternatives](https://fontalternatives.com/alternatives/sf-pro-display/for/ui/); [Design Monks](https://www.designmonks.co/blog/best-fonts-for-ui-design)). Its ubiquity is its weakness: it is the face of a thousand templates.
- **Geist** (Vercel): positioned for developer tools and SaaS, more technical than SF Pro ([fontalternatives](https://fontalternatives.com/alternatives/sf-pro-display/)); six stylistic sets for character; no optical-size axis.
- **SF Pro**: Apple's licence does not allow self-hosting on a website; only `system-ui` reaches it on Apple devices ([inspoai](https://www.inspoai.io/blogs/sf-pro-font-alternatives)).
- **Others named**: DM Sans, Source Sans 3, Noto Sans, Roboto (Android's own).

**Recommendation.** A short test, not a debate: set the deal pass, the memo and the payment list in Inter, Geist and one less common face with tabular figures, on the budget Android at 360 px and on a laptop; judge legibility of amounts and dates, character at heading sizes, and file size after subsetting. **(decision)**

## 3. The display face

- Serif display headlines over a sans body are reported as returning on SaaS pages in 2026; a template pairs **Fraunces** (display) with Inter (body); one designer names Editorial New; the adoption figures quoted were not verifiable ([SaaSFrame](https://www.saasframe.io/blog/10-saas-landing-page-trends-for-2026-with-real-examples); [pravinkumar.co](https://www.pravinkumar.co/blog/editorial-serif-type-webflow-b2b-saas-design-2026)). A statistics page reports about 95% of top sites use sans-serif body text and suggests one distinctive face in one place only ([mean.ceo](https://blog.mean.ceo/?p=11514)).
- **Why a serif fits Colyv**: the deal record is a ledger, and Tamil merchants wrote deals in stone (`docs/research/TAMIL_DESIGN_ROOTS.md` section 12.1); a carved, inscriptional serif says "kept for good" in a way a geometric sans does not.
- **Rule.** One display face, used only for headlines on marketing pages and in signature moments, never in working screens; an OFL or bought licence with web and app rights written down. Candidates to test: Fraunces (OFL, variable with an optical-size axis) and one inscriptional face. **(decision)**

## 4. Tamil

- **Noto Sans Tamil**: variable weight and width ([Fontsource](https://fontsource.org/fonts/noto-sans-tamil/about)); already used for the seal's rim inscription (the seal scene in frontend/3d/seal, on branch feature/temple-study, not yet merged); no tabular figures, so Latin figures come from the interface sans.
- **Anek Tamil**: variable weight and width, **with tabular figures**, designed as a multi-script family with Latin built in ([Fontsource](https://cdn.jsdelivr.net/npm/@fontsource-variable/anek-tamil@5.3.0/README.md)).
- **Mukta Malar**: OFL, by Ek Type, static weights only (table above).
- **Rule.** The interface sans is chosen with a Tamil companion whose x-height and weight match, so a second language arrives without a redesign (`frontend.md` section 7). Anek Tamil is the strongest companion on the measurements above (variable, tabular, Latin and Tamil designed together). Tamil numerals and ledger signs, when used as ornament, follow `docs/research/LANDING_CULTURE_FIT.md`.

## 5. The rules that make type look expensive

- **Numbers**: tabular figures (`font-variant-numeric: tabular-nums`) in every column of numbers; Indian grouping and IST dates through `Intl` with `en-IN`, never by hand (`frontend.md` section 7).
- **Line breaking**: `text-wrap: balance` for headings (Chrome 114, Firefox 121, Safari 17.5) and `text-wrap: pretty` for paragraphs (Chrome 117, Safari 26; **not Firefox**), the latter as an enhancement (MDN browser-compat-data, read 31 October 2026; [LogRocket](https://blog.logrocket.com/css-text-wrap-balance-vs-text-wrap-pretty/)). Balance only short blocks: it costs layout time.
- **Optical size**: variable fonts with an `opsz` axis set it automatically by size (`font-optical-sizing: auto`), so small text opens up and large text tightens ([web.dev: variable fonts](https://web.dev/articles/variable-fonts)).
- **Measure**: body lines of about 60 to 75 characters on desktop; headings tracked slightly tighter as they grow.
- **Loading**: self-hosted, subset to the characters we use, preloaded, with metric-matched fallbacks (`size-adjust`) so nothing shifts (`frontend.md` section 4).
- **Share images**: Next.js's `ImageResponse` (Satori) accepts only TTF and OTF fonts, not WOFF2, so each face also ships as TTF for the generated cards ([Next.js docs](https://nextjs.org/docs/app/api-reference/functions/image-response.md); [Paulund](https://paulund.co.uk/notebook/nextjs/dynamic-og-images-nextjs/)).

## 6. How it is tested

- **No layout shift from fonts**: CLS ≤ 0.05 in Lighthouse CI.
- **200% text**: nothing clipped or overlapping, in browser tests.
- **Pseudo-locale**: every string 40% longer, accented (`frontend.md` section 7).
- **Weight on the budget phone**: total font bytes per page within budget **(decision: the number)**.
- **A visual test of the type scale** in both themes at 360 px and desktop.

## 7. Decisions this file asks for

| # | Decision | Recommended |
|---|---|---|
| 1 | The interface sans | After the three-face test in section 2 |
| 2 | The display face | After a test of Fraunces and one inscriptional face, on the landing page's opening |
| 3 | The Tamil companion | Anek Tamil for the product (variable, tabular, Latin and Tamil designed together); Noto Sans Tamil stays on the seal |
| 4 | The mono face | Chosen with the interface sans, for matching metrics |
| 5 | The font byte budget per page | Set on the budget Android |

## 8. What is checked, and what the test decides

- **Checked in the files**: axes, tabular figures, the ₹ sign, Tamil coverage and the licence of every candidate (section 2's table). All are SIL OFL 1.1, which allows use in the website, the apps, share images and 3D scenes, with the licence shipped alongside.
- **Decided by the test in section 2**: which face reads our amounts and dates best on the budget Android, which carries Colyv's character at heading sizes, and the byte cost after subsetting.

## Sources (read 31 October 2026)

Every source is linked where it is used.
