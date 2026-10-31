# Colour psychology: what the evidence says, and what Colyv does with it

**For:** whoever chooses or changes a colour in the website or the apps, and the founders deciding the accent. **Version 1, 31 October 2026**, from web searches made that day and the colour research in `docs/PROPOSAL_FRONTEND_ARCHITECTURE.md` section 4 (30 October), which this file deepens. The Tamil meanings of colour live in `docs/research/TAMIL_DESIGN_ROOTS.md` section 7 and are linked, not copied. **Nothing here is a decision**; section 9 lists what needs one.

**The honest headline.** Popular colour psychology ("blue means trust", "red makes people buy") is mostly unsupported. The strongest findings are about **lightness and saturation**, about **consistency of meaning**, and about **people who see colour differently**. Hue matters less than the internet says, and culture and context change what a hue means.

---

## 1. Hue: weaker than its reputation

- **A review of 128 years of research** linking colours and emotions (42,266 participants, 64 countries) found the links mostly many-to-many, with systematic effects driven by **lightness, saturation and hue together**, not hue alone ([Psychonomic Bulletin & Review, 2024](https://link.springer.com/article/10.3758/s13423-024-02615-z)).
- **On websites and trust**, the most-cited study (over 200 people rating finance and medical sites) found blue rated most trustworthy and black least, but colour's effect was small next to content ([Alberts and van der Geest, 2011](https://research.utwente.nl/en/publications/color-matters-color-as-trustworthiness-cue-in-web-sites)). A 2025 review calls "blue is most trusted" methodologically unreliable ([Kosova, 2025](https://journals.rcsi.science/2782-2184/article/view/298120)).
- **"Red impairs performance"** (Elliot and colleagues) has repeatedly failed to replicate: Steele's lab could not produce the effect across several studies; one web-test study found it only in men ([Steele, Psychonomics 2016](https://www.appstate.edu/~steelekm/documents/Psychonomic2016Poster_Steele.pdf); [Steele and Rash, 2021](https://www.appstate.edu/~steelekm/documents/SteeleRash2021.pdf); [red in web-based testing](https://www.academia.edu/2887870/Color_red_in_web_based_knowledge_testing)). What is solid is the **interface convention**: on screens, red means "error" or "danger" because products taught people that.

**So:** the accent hue is chosen for meaning, distinctiveness and the convention it must not collide with, not for a promised emotional effect.

## 2. Saturation and lightness: the steadiest findings

- **Highly saturated colour reads as aggressive and promotional and lowers trust**; moderate saturation is trusted more, and greying everything out lowers it again ([saturation and trust, Computers in Human Behavior 2016](https://www.sciencedirect.com/science/article/abs/pii/S0747563216302254); [Kosova, 2025](https://publications.hse.ru/articles/1034440132)).
- **Brighter, more saturated colours are rated more pleasant** in isolation ([BMC Psychology, 2025](https://d-nb.info/1375425110/34)), and **saturation raises expected intensity** of a product ([Psychology & Marketing, 2025](https://onlinelibrary.wiley.com/doi/10.1002/mar.70021)). Pleasant on a swatch is not the same as trusted on a payment screen.
- **Colourfulness matters much less than visual complexity** for a site's first impression: in Reinecke and colleagues' study of 450 sites rated by 548 people, complexity explained far more of the appeal than colour did ([CHI 2013](https://kgajos.seas.harvard.edu/papers/reinecke13aesthetics.pdf)).

**So:** a calm, warm, near-neutral base; **one** accent at moderate saturation; strong colour reserved for meaning (state, sealed, threshold), never spread for excitement.

## 3. Meaning: consistency beats cleverness

The system holds each colour to one job, for ever:

| Role | Colour family | Never used for |
|---|---|---|
| Base surfaces and text | Warm neutrals: cream to ink (`TAMIL_DESIGN_ROOTS.md` section 7 names them from daily life) | Status |
| The one accent | Deep red (kumkum and kemp) by default; green as the alternative under test | Errors, warnings, money state |
| Sealed, final, confirmed | Raised gold | Anything that can still change (`frontend.md` section 8a) |
| Success (paid, approved) | A green distinct from any brand green | Decoration |
| Warning (due soon, look again) | Amber, never orange as a field (rule 6) | Decoration |
| Error, refusal, danger | A red clearly different from the accent in lightness and hue | The brand |
| Information | A muted blue | Primary actions |

The clash to manage: **a red accent next to red errors**, or **a green accent next to green success**. Either accent works only if the state colour is far from it in lightness as well as hue, and every state carries an icon and words too (section 5).

## 4. Culture and politics

- **Tamil meanings** (red for the auspicious and marriage, white also for mourning, gold for what is final): `TAMIL_DESIGN_ROOTS.md` section 7. Plain white is avoided as a large ground; warm cream is used instead.
- **India-wide preference** data is thin: one small study of 120 young adults found blue most preferred, red read as vibrant and auspicious, green as faith and nurturing (`docs/PROPOSAL_FRONTEND_ARCHITECTURE.md` section 4 sources).
- **Politics (D-143):** no saffron or orange as a brand colour, sky or large field, and no lotus; a sunrise only as natural light in a scene (`TAMIL_DESIGN_ROOTS.md` rule 6).
- **Colour in context:** Elliot and Maier's own framework says a colour's meaning depends on context; a red seal on a sealed deal and a red error banner do not mean the same thing, and the system must keep them visibly different.

## 5. People who see colour differently

- **In Indian studies, about 8 to 9% of men and 1 to 2% of women** have a red-green colour-vision difference, with deuteranomaly the most common type: 8.73% of men and 1.69% of women in Manipur; 8.12% and 0.9% in a Belagavi hospital sample; lower in a Dehradun tribal sample ([Iranian Journal of Public Health, 2013](https://ijph.tums.ac.ir/index.php/ijph/article/view/4765); [JCDR, 2022](https://doaj.org/article/054cdcb82c8244988387b6bd782667c8)). Samples and methods differ; the order of magnitude is consistent.
- For a product mostly used by men in some niches, **close to one user in ten** may not tell our red and green apart by hue.

**Rules.** Colour is never the only signal (`frontend.md` section 6): every state has an icon and a word. CI renders the state colours through deuteranomaly, protanomaly and tritanomaly simulations and fails if any two state colours fall below a set difference **(decision: the threshold, from the simulation test)**. The paid/unpaid distinction never depends on red against green.

## 6. Contrast, measured properly

- **OKLCH** (CSS Color 4, built on Oklab) spaces lightness so equal steps look equal, which makes a ramp of shades predictable ([frontend checklist](https://frontendchecklist.io/rules/css/color-oklch); [arXiv 2512.07623](https://arxiv.org/html/2512.07623v1)). Its L is **not** WCAG's luminance, so contrast is still computed, never assumed.
- **WCAG 2.2 stays the standard we are held to.** APCA, the contrast method expected in WCAG 3, is still a draft and not a requirement. We compute both where APCA helps (dark mode, thin text), and gate on WCAG.
- **Already built** (on branch `feature/design-foundations`, not merged): the tokens in OKLCH with a contrast gate over 112 text-on-surface pairs, at 7:1 for body text (`frontend.md` section 6).

## 7. Light and dark

- **Light mode reads faster for most people with normal vision** in NN/g's summary of lab research; Material's readability work found dark mode readable at adjusted type grades; people with astigmatism often report halos around light-on-dark text, but no controlled study was found; some people with cataracts read light-on-dark better ([NN/g: dark mode](https://www.nngroup.com/articles/dark-mode/); [Material: readability research](https://material.io/blog/readability-research)).
- **Preference is not performance**: many people prefer dark mode and use apps longer in it.

**Rules.** Both themes from the same tokens; the theme follows the device unless the person chooses; dark text weight is adjusted (lighter text on dark looks bolder), and contrast is gated in both. **Temple dusk** is the natural dark theme.

## 8. How Colyv decides the accent

The question is open between burgundy (the prototype, Tamil roots) and green (Harish's app). The design-foundations branch makes burgundy the default and green selectable, so either can ship; the evidence test proposed in `docs/PROPOSAL_FRONTEND_ARCHITECTURE.md` section 4 (option C: both accents on three real screens, a five-second test with five brand owners and five creators in Tamil Nadu) **has not been run**. Given section 1, hue will matter less than saturation, restraint and the clash with state colours; the test should measure trust and clarity ("which would you trust with a payment?", "what does this colour mean here?"), not liking.

## 9. Decisions this file asks for

| # | Decision | Recommended |
|---|---|---|
| 1 | The accent: run the five-second test before locking it | Yes |
| 2 | The colour-role table in section 3 as binding | Yes |
| 3 | A CI test of state colours under colour-vision simulations | Yes |
| 4 | APCA computed alongside WCAG, WCAG as the gate | Yes |

## 10. What the literature cannot settle, and how we settle it

- **How Tamil Nadu's brand owners and creators read each accent**: the colour test in `docs/research/PEOPLE_RESEARCH_KIT.md` section 5, run by the founders.
- **The exact colours of real objects** (silk, kumkum, bronze, granite): photographed under daylight with a colour checker, as `TAMIL_DESIGN_ROOTS.md` section 7 asks; an item in `docs/FRONTEND_COMPLETE.md` (materials in 2D).
- **Colour-vision prevalence in Tamil Nadu itself**: no study exists; the regional figures in section 5 agree on the order of magnitude, and the simulation test in CI protects everyone regardless of the exact share.
- **No meta-analysis of colour and website trust exists**; the 128-year review and the saturation studies are the strongest evidence there is, and section 2's rule rests on them.

## Sources (read 31 October 2026)

Every source is linked where it is used. Studies are cited by venue and year; secondary summaries are named as such.
