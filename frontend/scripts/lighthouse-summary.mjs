// Prints what Lighthouse measured on each page, so the ratchet's lines (apps/web/lighthouserc.cjs, D-198)
// are lowered from CI's own numbers, never from a laptop's. Reads the reports `lhci autorun` saved in
// apps/web/.lighthouseci; uses the run Lighthouse marks as representative (the median run) for each page.
//   node scripts/lighthouse-summary.mjs apps/web/.lighthouseci
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { join, resolve } from "node:path";

const dir = process.argv[2];
if (!dir) throw new Error("usage: node scripts/lighthouse-summary.mjs <.lighthouseci folder>");

const manifest = JSON.parse(readFileSync(join(dir, "manifest.json"), "utf8"));
const representative = manifest.filter((run) => run.isRepresentativeRun);

// Every page lighthouserc.cjs collects must have its report, or a page that failed to load would pass unseen.
const expected = createRequire(import.meta.url)(resolve(dir, "..", "lighthouserc.cjs")).ci.collect.url;
const missing = expected.filter((url) => !representative.some((run) => run.url === url));
if (missing.length > 0) {
  console.error(`no Lighthouse report for ${missing.join(", ")} in ${dir}/manifest.json`);
  process.exitCode = 1;
}

for (const run of representative) {
  const report = JSON.parse(readFileSync(run.jsonPath, "utf8"));
  const audit = (id) => report.audits[id]?.numericValue;
  const script = report.audits["resource-summary"]?.details?.items?.find((item) => item.resourceType === "script");
  const score = (id) => Math.round((report.categories[id]?.score ?? 0) * 100);
  console.log(
    [
      run.url,
      `performance ${score("performance")}`,
      `accessibility ${score("accessibility")}`,
      `best-practices ${score("best-practices")}`,
      `seo ${score("seo")}`,
      `LCP ${Math.round(audit("largest-contentful-paint"))} ms`,
      `CLS ${audit("cumulative-layout-shift")?.toFixed(3)}`,
      `TBT ${Math.round(audit("total-blocking-time"))} ms`,
      `script ${script?.transferSize ?? "?"} bytes`,
    ].join(" | "),
  );
}
