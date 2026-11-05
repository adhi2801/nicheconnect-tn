# Reference devices: the phones and laptop every budget is measured on

**For:** the founders, to buy the test bench `docs/standards/frontend.md` section 3 requires; and whoever measures performance, frames or the 3D budgets. **Version 1, 31 October 2026**, from market data read that day. `frontend.md` section 3 leaves the exact models as a decision "chosen by current Indian sales at frontend start"; this file makes that choice ready.

---

## 1. What the market says (Q2 and Q3 2026)

- **Q3 2026** (Counterpoint): India's shipments fell 20% year on year to a ten-year low; **sub-₹20,000 shipments nearly halved**, and the sub-₹15,000 band was hit hardest. **Samsung led with 17%** (Galaxy A-series: the A07, A17 and A27 named as best-sellers), **vivo 16%**, **OPPO 12%**; **Xiaomi with POCO about 12%, leading ₹10,001 to ₹20,000**, through POCO's C series and Redmi's A and number series ([Counterpoint, Q3 2026](https://counterpointresearch.com/en/insights/india-smartphone-market-slumps-20-yoy-in-q3-sub-inr-20000-shipments-nearly-halve); [FoneArena](https://www.fonearena.com/blog/495745/india-smartphone-market-q3-2026-counterpoint.html); [ETV Bharat](https://www.etvbharat.com/en/technology/indian-smartphone-market-declines-20-pc-in-q3-due-to-rising-costs-sub-rs-20000-segment-takes-biggest-hit-enn26102303746); [RSWebSols summary](https://www.rswebsols.com/news/indias-smartphone-market-hits-ten-year-low-in-q3-2026-according-to-reports/)).
- **Q2 2026**: vivo led (Counterpoint 20%; Omdia 18%, with Samsung 17%, OPPO 14%, Xiaomi 13%, Apple 10%) ([Counterpoint](https://www.counterpointresearch.com/india-smartphone-share/); [TelecomLead on Omdia](https://telecomlead.com/smart-phone/top-smartphone-vendors-in-india-vivo-leads-as-omdia-reports-13-shipment-decline-in-q2-2026-126837)).
- **What phones people browse on** (web traffic, June 2026): vivo 17.3%, Xiaomi 15.7%, Realme 12.3%, Samsung 12.2%, OPPO 10.7% ([Statcounter](https://gs.statcounter.com/vendor-market-share/mobile/india)). Traffic shows the installed base, which is older and cheaper than this quarter's sales.
- **Prices are rising**: the average selling price hit a record $315 to 318 in Q2 2026, and phones under $100 fell to 4.5% of shipments (`docs/research/FRONTEND_RESEARCH_2026.md` B9).
- **iOS 26** runs on the iPhone 11 series and the iPhone SE (2nd generation) and later; the XS, XS Max and XR were dropped ([9to5Mac](https://9to5mac.com/2025/09/15/ios-26-supports-these-recent-iphones-but-drops-three-models/); [MacRumors](https://www.macrumors.com/2025/08/05/will-my-iphone-support-ios-26/)).

## 2. The bench

| Tier | Choose | Why | Used for |
|---|---|---|---|
| **Budget Android** | **A Samsung Galaxy A07** (or, if unavailable, a Redmi A-series or POCO C-series), 4 GB RAM | Samsung's best-sellers lead the market; Xiaomi's lead the sub-₹20,000 band; 4 GB is `frontend.md` section 3's floor | Every budget in `frontend.md` section 4, the frame test, the 3D byte budget |
| **Mid-range Android** | **A Samsung Galaxy A17 or A27**, or a current vivo Y or T series, 6 to 8 GB | The "typical creator" phone in Q3 2026's best-sellers | The typical check; glass and blur cost |
| **Older iPhone** | **An iPhone 11 or SE (2nd generation), bought second-hand** | The oldest iPhones iOS 26 supports | iOS budgets; Safari's 60 fps default (`docs/research/FEEL_AND_MOTION_2026.md` section 1) |
| **Laptop** | A mid-range Windows laptop with Chrome (a founder's own is enough) | Desk work for brands | Website budgets on desktop |
| **Network** | Chrome's throttling at about 1.6 Mbps down and 150 ms round trip, plus fully offline | `frontend.md` section 3 | Every lab run |

**Cost.** Both founders are students; the two Android phones are bought new (current street prices to be checked on the day of purchase), the iPhone second-hand, the laptop already owned. Only the specific model and its RAM matter for the measurements; the colour and storage do not.

## 3. How the bench is used

- **Every release**: each core journey on each phone, with the platform frame tools; results recorded per release (`docs/FRONTEND_COMPLETE.md`, performance section).
- **Every 3D scene and frame sequence**: its byte and frame budgets are set on the budget Android before the scene is built (`frontend.md` section 8b).
- **Lab profiles in CI** are tuned so their numbers match the budget Android's within 10%, measured once and re-checked each quarter.

## 4. Decision

| # | Decision | Recommended |
|---|---|---|
| 1 | The bench in section 2 | Yes: buy the budget and mid-range Android new, the iPhone second-hand |

## Sources (read 31 October 2026)

Linked where used. Counterpoint's model names come through press coverage of its Q3 report; the brand shares are Counterpoint's own page.
