// Prints what Lighthouse measured on each page, so the ratchet's lines (apps/web/lighthouserc.cjs, D-198)
// are lowered from CI's own numbers, never from a laptop's. Reads the reports `lhci autorun` saved in
// apps/web/.lighthouseci; uses the run Lighthouse marks as representative (the median run) for each page.
//   node scripts/lighthouse-summary.mjs apps/web/.lighthouseci
import { readFileSync } from "node:fs";
import { join } from "node:path";

const dir = process.argv[2];
if (!dir) throw new Error("usage: node scripts/lighthouse-summary.mjs <.lighthouseci folder>");

const manifest = JSON.parse(readFileSync(join(dir, "manifest.json"), "utf8"));
const representative = manifest.filter((run) => run.isRepresentativeRun);
if (representative.length === 0) throw new Error(`no representative run in ${dir}/manifest.json`);

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
