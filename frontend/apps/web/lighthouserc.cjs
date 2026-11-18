// Lighthouse CI (D-171, D-198): the lab budgets of docs/standards/frontend.md section 4, failing the build.
// Lighthouse's default mobile run throttles to about 1.6 Mbps down and 150 ms round trip with a slowed CPU,
// which is the standard's reference network (section 3). Each page runs three times and the median is judged,
// so one noisy run neither passes nor fails a page on its own.
//
// A RATCHET (Adhi, 18 November 2026, D-198). The first measurement (the same day, on a laptop) found both
// pages far over the targets, so the check blocks at today's numbers: a page that gets worse fails, and every
// change that improves a page lowers its line here, never raises it. TARGET is the standard's bar; a line may
// only move toward it. When a page meets its target, its RATCHET line is deleted and TARGET is what it holds.
//
// Pages: the public ones a stranger lands on. The signed-in screens are judged by the browser tests
// (accessibility, every state) until a signed-in Lighthouse run is wired to the stand-in backend.

const TARGET = {
  performance: 0.95, accessibility: 1, bestPractices: 1, seo: 1,
  lcpMs: 2000, cls: 0.05, tbtMs: 200, scriptKb: { landing: 50, signIn: 150 },
};

// Measured 18 November 2026: landing Performance 0.83, Best practices 0.81, LCP 2,926 ms, TBT 349 ms,
// script 524,986 bytes; sign-in 0.91, 0.77, 2,523 ms, 245 ms, 520,127 bytes. Accessibility and SEO were
// already 100 on both, so they hold the target. Timing lines carry a margin for the runner's speed; sizes,
// which do not vary between runs, carry none beyond the next kilobyte.
const RATCHET = {
  landing: { performance: 0.8, bestPractices: 0.81, lcpMs: 3200, tbtMs: 450, scriptBytes: 513 * 1024 },
  signIn: { performance: 0.86, bestPractices: 0.77, lcpMs: 2800, tbtMs: 350, scriptBytes: 509 * 1024 },
};

const median = { aggregationMethod: "median" };
const assertionsFor = (r) => ({
  "categories:performance": ["error", { minScore: r.performance }],
  "categories:accessibility": ["error", { minScore: TARGET.accessibility }],
  "categories:best-practices": ["error", { minScore: r.bestPractices }],
  "categories:seo": ["error", { minScore: TARGET.seo }],
  "largest-contentful-paint": ["error", { maxNumericValue: r.lcpMs, ...median }],
  "cumulative-layout-shift": ["error", { maxNumericValue: TARGET.cls, ...median }],
  // INP needs a real person's taps; in the lab its stand-in is the main thread's blocking time.
  "total-blocking-time": ["error", { maxNumericValue: r.tbtMs, ...median }],
  // JavaScript a page sends on first load (section 4).
  "resource-summary:script:size": ["error", { maxNumericValue: r.scriptBytes, ...median }],
});

module.exports = {
  TARGET,
  RATCHET,
  ci: {
    collect: {
      url: ["http://127.0.0.1:3100/", "http://127.0.0.1:3100/sign-in"],
      numberOfRuns: 3,
      settings: { chromeFlags: "--no-sandbox --headless=new" },
    },
    assert: {
      assertMatrix: [
        { matchingUrlPattern: "3100/$", assertions: assertionsFor(RATCHET.landing) },
        { matchingUrlPattern: "/sign-in$", assertions: assertionsFor(RATCHET.signIn) },
      ],
    },
    upload: { target: "filesystem", outputDir: ".lighthouseci" },
  },
};
