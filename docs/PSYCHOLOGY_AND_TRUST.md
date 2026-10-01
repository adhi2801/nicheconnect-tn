# Psychology and trust: why people will rely on us, and the line we never cross

**Researched 1 October 2026.** Every product decision that touches how people feel (screens, alerts, words, the order things happen in) reads this first. Facts carry sources at the bottom; where something is our judgement, it says so.

**The one idea:** both sides of this market already price in each other's risk. Creators quote higher or demand deposits because brands pay late; brands haggle because creators inflate. **Whoever removes the fear takes the market.** We remove it with facts, not with persuasion.

---

## 1. What each side feels today

| | Creators | Brands (small and mid-size businesses) |
|---|---|---|
| **The fear** | Not being paid, or being paid months late. **One in three Indian influencers report delayed payments**; cycles of 60 to 90 days are common (`docs/COMPETITIVE_LANDSCAPE.md` section 7) | Paying for reach that is not real. **42% of brands say they paid an influencer later found to have heavy fake followings** |
| **The weight** | A study of 550 Indian creators in 18 cities found **high burnout in 52.7%**, performance pressure in 54.9%, and psychological burden in 55.3%. About 70% of creators report unstable income. No law recognises them as businesses, and no body represents them | Time. The owner is also the marketer, the accountant and the shopkeeper |
| **The power** | Unequal: a nano creator cannot chase a brand that stops answering | Unequal the other way when a creator disappears with a free product |
| **What they want to feel** | **Respected as a professional, and safe** | **In control, and not a fool** |

Our judgement from this: **the creator's strongest emotion is anxiety about money, and the brand's is fear of being cheated.** Every feature should lower one of them, visibly.

## 2. The line we never cross

India's Central Consumer Protection Authority made 13 deceptive designs unfair trade practices from **30 November 2023**, and enforces them. They are banned here whether or not the law reaches us, because a trust product that manipulates is a contradiction. For each, the rule we follow instead:

| Banned pattern | Our rule |
|---|---|
| False urgency | A deadline shown is a real one from the deal: the memo's due date, the approval window, the payment clock |
| Basket sneaking | Nothing is ever added to what a person agreed to |
| Confirm shaming | Declining is a plain, neutral button: "Not now", never "No, I don't want more brands" |
| Forced action | No task is held hostage to an unrelated one (installing the app, inviting friends, connecting Instagram) |
| Subscription trap | Cancelling is as easy as joining, from the same screen, in the same number of steps |
| Interface interference | The safe choice is never hidden or greyed; both choices look like choices |
| Bait and switch | What a campaign promises is what the memo records (D-024) |
| Drip pricing | Any price we charge is shown whole, at the start |
| Disguised advertisement | Paid placement, if it ever exists, is labelled as paid |
| Nagging | Every alert is tied to a real event in a deal; a notification budget per person (section 5) |
| Trick wording | Plain English; buttons say what happens (`docs/standards/ux.md` section 6) |
| SaaS billing | No silent renewals; reminders before any charge |
| Rogue malware | Nothing installed that the person did not ask for |

**Also never:** fake activity ("12 brands are viewing this"), fake scarcity, streaks that punish a day off, or infinite feeds built to keep people scrolling. Creators are already burning out; we will not add to it.

## 3. What builds trust, from the evidence

| Mechanism | Evidence | How we use it | Status |
|---|---|---|---|
| **Facts over opinions** | Star ratings inflate (Airbnb's skew heavily positive) and lose their meaning; two-sided reviews invite retaliation | Records of what happened, with dates: on-time payment share, delivered on time, disputes. Never stars | **Built** (D-034, D-038) |
| **Proof nobody can quietly change** | Trust needs that the record itself cannot be edited by the platform | The deal record is append-only, chained, and stamped daily by outside authorities | **Built** (D-057, D-060) |
| **Simultaneous reveal**, if feedback ever exists | Airbnb shows reviews only after both sides submit, or 14 days pass, which discourages tit-for-tat | Any future feedback between the two sides is hidden until both have answered | Proposed |
| **Fair process, visible** | People accept an outcome they dislike when the process was fair and they could see it (procedural justice, our judgement from long-established research) | Dispute timelines both sides can see and export; no verdict recorded by us (D-036) | **Built** |
| **Certainty lowers anxiety** | Unknown waiting is felt as longer and worse than known waiting (our judgement from queueing research) | Always show **what happens next and when**: the approval window, the payment clock, the day it becomes overdue | Built in the data; the screens show it |
| **Thresholds before numbers** | A figure from two deals misleads | Five creators or nothing for price guidance (D-056); minimum deals before a reliability record shows | **Built** |
| **Honest labels** | A screenshot can be edited; Claude cannot tell a real image from a fake one | "Read from the creator's screenshot", never "verified" (D-070) | **Built** |
| **Ownership** | People value what they built and own (our judgement from the endowment effect) | A creator's record and Passport are theirs: exportable, portable, never held hostage | **Built** (export); portability is a principle |

## 4. Moments that create connection

Our judgement: people remember a few peaks and the ending of an experience more than its average. So we design a handful of moments with care, and keep everything else quiet and fast.

| Moment | Who | What we make of it |
|---|---|---|
| **First application sent** | Creator | Clear next step and honest timing: "Brands usually reply within N days", from real data only, never invented |
| **First memo accepted** | Both | The deal becomes real: what was agreed, sealed, with the payment clock visible to both |
| **Proof approved** | Creator | Recognition of the work, and the exact payment due date from that moment |
| **Payment confirmed** | Both | The ending that matters most: a deal receipt both can keep, and the record updated for both reputations |
| **A dispute** | Both | Calm and factual: both timelines side by side, no blame language, the next possible step |
| **Milestones** | Creator | "10 deals, all delivered on time": earned, true, and shareable to their Passport. Never a streak that punishes rest |
| **A brand pays on time** | Brand | Its on-time record grows where creators can see it; good behaviour is visible and rewarded with better applicants |

## 5. Habit without exploitation

Our rule: **people come back because something real needs them, not because we engineered a craving.**

- **Every alert maps to a real event in a deal**, gathered by `GET /api/v1/me/attention` (built): what needs this person, and why.
- **A notification budget per person**, quiet hours, and a daily digest option. Urgent deal events (payment marked, proof approved) still come at once.
- **No infinite feeds.** Discovery lists end; matches explain themselves (Phase D).
- **Rest is respected.** Nothing penalises a creator for taking a week off.

## 6. What this asks of the backend

| Item | Why | Status |
|---|---|---|
| A timestamp for every state change | "What happened when" on every screen (`docs/standards/ux.md` section 7) | **Built** |
| "What needs me" in one call | Alerts tied to real events | **Built** (`/me/attention`) |
| **Notification preferences: quiet hours, digest, per-event choice** | Section 5; no nagging | **Not built**: needs a table and a decision. Added to `docs/BACKEND_COMPLETE.md` |
| **Typical response times from real data** ("brands usually reply within N days") | Certainty (section 3) without invention | **Not built**: computed from existing timestamps; a decision on thresholds |
| **Milestones from real records** | Section 4 | **Not built**: derived from existing records; a decision on which |
| Simultaneous reveal for any two-sided feedback | Section 3 | Only if feedback is ever approved |

## 7. How we know it works

Measured, never assumed: time to first deal for each side; share of deals paid on time; disputes per hundred deals; repeat deals between the same brand and creator; creators active after 90 days; and how many people turn off alerts (a rising number means we are nagging). Targets are set once the pilot has a baseline (`docs/REVENUE_RESEARCH.md` section 8).

---

## Sources

- [CCPA Guidelines for Prevention and Regulation of Dark Patterns, 2023 (Mondaq)](https://www.mondaq.com/india/consumer-trading--unfair-trading/1398262/ccpa-issues-guidelines-for-prevention-and-regulation-of-dark-patterns-2023-effective-30-november-2023), [CCPA acts against dark patterns (PIB)](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2268302&reg=3&lang=1), [The 13 patterns explained](https://www.thepresspad.com/post/dark-patterns-india-ccpa-13-dark-patterns-explained)
- [Designing Online Marketplaces: Trust and Reputation Mechanisms (Luca, HBS)](https://www.hbs.edu/ris/Publication%20Files/17-017_ec4ccdc0-4348-4eb9-9f46-86e1ac696b4f.pdf), [Reviews and reputation (Fradkin)](https://andreyfradkin.com/assets/reviews_paper.pdf), [Trust and power in Airbnb's rating system](https://link.springer.com/article/10.1007/s10676-025-09825-6), [The trust stack for marketplaces](https://www.uladshauchenka.com/p/the-trust-stack-for-marketplaces)
- [India's creator economy: broken payments as the bottleneck](https://www.thereelstars.com/tech/indias-creator-economy-is-booming-but-broken-payments-are-becoming-its-biggest-bottleneck/), [Creator mental health study, 550 respondents in 18 Indian cities](https://kommerstad.org/journal/article/download/355/272/797), [Influencer economy statistics 2026](https://lonelyentrepreneur.com/influencer-economy-statistics-2026/)
- Fake followers and brand losses: `docs/COMPETITIVE_LANDSCAPE.md` sources
- Compliance is not taken from here: any legal duty comes from the validation pack (constraint 6)
