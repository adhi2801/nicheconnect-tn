# Interface psychology: how people judge, read and remember a screen

**For:** whoever designs a screen, a flow or the landing page. **Version 1, 31 October 2026**, from web searches made that day. It covers the **interface**: first impressions, beauty and usability, waiting, memory of an experience, effort and choice. **Why people will trust Colyv at all, and the line we never cross** (no dark patterns, no manufactured urgency, facts over opinions) is `docs/PSYCHOLOGY_AND_TRUST.md`; this file builds on it and never overrides it.

**How strong the evidence is.** Each finding says how it was tested and cites its original paper. Several famous "laws of UX" rest on one old study or on folklore (the 400 ms "Doherty threshold" is one); those are marked, and none is used as the only reason for a rule. Testing with Tamil brand owners and creators is section 8, run with `docs/research/PEOPLE_RESEARCH_KIT.md`.

---

## 1. First impressions are fast, and they colour everything after

- **Lindgaard and colleagues (2006)** showed homepages for 50 ms and for 500 ms: appeal ratings at 50 ms correlated highly with those at 500 ms. The study shows people *can* judge appeal from a 50 ms glimpse, not that they *decide* in 50 ms; Lindgaard argued the first impression carries a halo into later judgements of usability and credibility ([Behaviour & Information Technology 25(2), 2006](https://www.digitaltrends.com/home/surfers-judge-web-pages-seen-for-only-50ms/); [commentary on what it does and does not show](https://websiteoptimization.com/speed/tweak/blink/)).
- **Reinecke and colleagues (CHI 2013)**: 548 people rated 450 sites after 500 ms; models of **visual complexity** and colourfulness explained about half the variance in appeal, and complexity mattered much more than colour. A 2014 follow-up with almost 40,000 participants found age, gender, education and country shift the preferred level of complexity and colourfulness ([CHI 2013 paper](https://kgajos.seas.harvard.edu/papers/reinecke13aesthetics.pdf); [2014 paper](https://iis.seas.harvard.edu/papers/reinecke14visual.pdf)).

**Rules for Colyv.**
1. **The first screen is judged before it is read.** The landing page's opening and every app home screen are tested as a five-second test with brand owners and creators before they are final (`docs/PROPOSAL_FRONTEND_ARCHITECTURE.md` part 29).
2. **Low visual complexity on working screens**: one primary action, a clear grid, few competing weights. Grandeur lives on the landing page and the signature moments, not on the deal screen.
3. **Our audience's own preferences are measured, not assumed**: Reinecke's 2014 result means a Bay Area SaaS look is not automatically right for Madurai.

## 2. Beautiful things are judged easier to use, before and after use

- **Kurosu and Kashimura (1995)**: 252 people rated 26 ATM layouts; apparent usability tracked beauty more than the layouts' functional design. **Tractinsky (CHI 1997)** replicated it in Israel. The fair criticism, that people rated without using the machines, was answered by **Tractinsky and colleagues (2000)**: after real use, aesthetics still shaped perceived usability, while actual usability did not ([Tractinsky, CHI 1997](https://chi1997.acm.org/proceedings/paper/nt.html); [BGU summary of the 2000 study](https://www.ise.bgu.ac.il/faculty/noam/research/aesthetics.html); [York critique](https://www-users.york.ac.uk/~am1/HOIT07MonkLelos.pdf)).
- **Processing fluency (Reber, Schwarz and Winkielman, 2004)**: things that are easy to perceive feel more beautiful, and fluency is felt as pleasant; very high complexity lowers fluency and liking ([PSPR 2004](https://pages.ucsd.edu/~pwinkielman/reber-schwarz-winkielman-beauty-PSPR-2004.pdf)).

**Rules.**
1. **Beauty is a requirement, not polish**: it changes whether people believe the product works. This is why `frontend.md` section 8a's aesthetic bar is binding.
2. **Beauty never hides a problem**: the aesthetic-usability effect can make people forgive a flaw they should have reported, so usability is measured by tasks completed and errors made, never by how people say it felt.
3. **Fluency first**: familiar SaaS structure (the "prototype" people expect), real type hierarchy, aligned edges. The Tamil soul enters through material and light, which add meaning without making the screen harder to parse (`TAMIL_DESIGN_ROOTS.md` rule 0).

## 3. Waiting: honest, short, and shown

The limits (0.1 s, 1 s, 10 s), the mixed evidence on skeletons and the labor illusion are in `docs/research/FEEL_AND_MOTION_2026.md` section 2. The psychological rule they add up to: **uncertainty is worse than delay**. A screen always says what is happening, what happens next, and when (`PSYCHOLOGY_AND_TRUST.md` section 3).

**Operational transparency** goes further than loading screens. Buell and colleagues found showing customers the work being done raised perceived value (2011), and **reciprocal** transparency (each side seeing the other's work) raised reported quality by 22% and cut throughput time by 19% in a field study ([Buell and Norton, Management Science 2011](https://pubsonline.informs.org/doi/10.1287/mnsc.1110.1376); [IDEAS summary](https://ideas.repec.org/a/inm/ormnsc/v57y2011i9p1564-1579.html)). A deal's shared timeline, where each side sees what the other did and when, is exactly that: it is the product, not decoration.

## 4. People remember the peak and the end

- **The peak-end rule**: people judge a past experience mostly by its most intense moment and its end, and largely ignore its length (Kahneman and colleagues, 1993; Redelmeier and Kahneman, 1996). A meta-analysis of 85 to 95 studies found the effect large (r = .57) and robust, and the effect of duration essentially nil ([Alaybek, George Mason University, 2020](https://psychology.gmu.edu/defenses/1259); [Wikipedia summary](https://en.wikipedia.org/wiki/Peak%E2%80%93end_rule)).

**Rules.** Colyv designs its peaks and ends on purpose:
- **The peak** is the deal agreed and sealed: the one orchestrated moment of the product (the seal closing across the fold, `docs/PROPOSAL_FRONTEND_ARCHITECTURE.md` section 5).
- **The end** is the payment confirmed and the record closed: calm, final, raised gold, with the next useful step ("work together again").
- **The worst moment** (a late payment, a dispute) is made as un-intense as honesty allows: exact facts, dated, a clear next step, never alarm colours across the whole screen.

## 5. Progress pulls people forward

- **The goal-gradient effect**: Kivetz, Urminsky and Zheng, "The Goal-Gradient Hypothesis Resurrected", *Journal of Marketing Research* 43 (February 2006), 39–58. On a café's buy-ten-get-one card, the time between purchases shrank by about 20% from the first stamp to the last; a 12-stamp card with two stamps given free was completed faster than a plain 10-stamp card, an **illusion** of progress; after the reward, the pace reset ([Columbia Business School](https://business.columbia.edu/faculty/research/goal-gradient-hypothesis-resurrected-purchase-acceleration-illusionary-goal); [paper](https://business.columbia.edu/sites/default/files-efs/pubfiles/1200/goalgradient.pdf); [Chicago Booth Review](https://www.chicagobooth.edu/review/going-goal)).

**Rule.** Every deal shows its stage on one stepper with whose move it is (the backend already answers `stage` and `waiting_on`); onboarding shows "step n of 2". Progress is shown truthfully: **Kivetz's free stamps work, and we refuse them**: never a bar that starts half full to make people feel closer than they are (`PSYCHOLOGY_AND_TRUST.md` section 2).

## 6. Effort, choice and attention

- **Fitts's law**: movement time to a target grows with its distance relative to its width (Fitts, "The information capacity of the human motor system in controlling the amplitude of movement", *Journal of Experimental Psychology* 47(6), 1954, 381–391; [summary](https://en.wikipedia.org/wiki/Fitts%27s_law)). → Primary actions are large and within thumb reach on phones (bottom of the screen); targets are at least 48 dp (`frontend.md` section 6).
- **Hick's law**: decision time rises with the logarithm of the number of equally likely choices (Hick, *Quarterly Journal of Experimental Psychology* 4(1), 1952, 11–26; Hyman, *Journal of Experimental Psychology* 45(3), 1953, 188–196). Its known limits: it does not hold for searching an unordered list, which grows linearly, nor for very familiar choices ([summary with the limits](https://en.wikipedia.org/wiki/Hick%27s_law)). → One primary action per screen; secondary actions in a menu; campaign creation in four short steps (`frontend/design/screen-plan.md`); long lists are searchable and sorted, never scanned.
- **Defaults are decisions**: most people keep them. → Every default is the option that protects the person who did not change it (the memo's defaults favour neither side; notifications default to what is urgent), never the one that suits us.
- **Cognitive load**: people hold a few things in mind at once. → The agreed terms are always one tap away during the work (screen plan, C7 the deal pass), so nobody has to remember them.

## 7. Emotion without manipulation

- **Don Norman's three levels**, from *Emotional Design: Why We Love (or Hate) Everyday Things* (Basic Books, 2004), developed with Andrew Ortony and William Revelle: **visceral** (the immediate response to appearance), **behavioural** (the pleasure and effectiveness of use) and **reflective** (what it says about me), working at once, not in sequence ([jnd.org](https://jnd.org/emotional-design-why-we-love-or-hate-everyday-things/); [NPTEL lecture](https://archive.nptel.ac.in/content/storage2/courses/109104075/lecture40/40_6.htm)). → Every screen review asks all three: does it look right at a glance, does it work, and would a brand owner be proud to show it to a client?
- **The line**: emotion comes from craft and truth (a beautiful seal on a real record), never from pressure. No countdowns that are not real deadlines, no "3 brands are viewing this creator", no confirmshaming. The thirteen banned dark patterns are checked before every release (`docs/standards/legal.md` section 3, `frontend.md` section 7).

## 8. How each rule is tested

| Rule | Test |
|---|---|
| First impression | Five-second test of each opening screen with five brand owners and five creators; written up in `docs/research/` |
| Beauty and usability | Task tests: completion and errors, separate from satisfaction ratings |
| Waiting | The frame and response tests in `FEEL_AND_MOTION_2026.md` section 10 |
| Peak and end | Asked after a pilot deal: "what do you remember?", and checked against the moments we designed |
| Progress | Every journey's stepper checked against the backend's `stage` in end-to-end tests |
| Dark patterns | The release checklist (`docs/standards/legal.md` section 3) |

## 9. What only our own people can settle

Every finding above is checked against its original paper or its authors' institution. What no paper can settle is how **Tamil Nadu's** brand owners and creators respond: almost all the studies are Western or East Asian, and Reinecke's 2014 work shows preferences move with country. Section 8's tests settle it, run with `docs/research/PEOPLE_RESEARCH_KIT.md`.

## Sources (read 31 October 2026)

Every source is linked where it is used.
