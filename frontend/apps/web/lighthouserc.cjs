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

// Measured by CI's runner on 19 November 2026 (the median run, printed by scripts/lighthouse-summary.mjs):
// landing Performance 100, Best practices 100, LCP 755 ms, TBT 91 ms, script 159,800 bytes;
// sign-in 100, 96, 800 ms, 47 ms, 154,941 bytes; Accessibility and SEO 100 on both. Every line CI already
// meets holds the TARGET itself. Only what misses is ratcheted: both pages' JavaScript (sizes do not vary
// between runs, so each line is the measured size rounded up to the next KiB) and sign-in's Best practices.
// (A laptop, loaded with other tests, measured about 3.3 times the JavaScript and far slower timings on
// 18 November; that difference is not explained, so laptop figures are never used for these lines.)
const RATCHET = {
  landing: { ...TARGET, scriptBytes: 157 * 1024 },
  signIn: { ...TARGET, bestPractices: 0.96, scriptBytes: 152 * 1024 },
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
