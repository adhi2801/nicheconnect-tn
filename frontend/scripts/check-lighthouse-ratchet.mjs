// The Lighthouse ratchet only tightens (D-198, frontend.md section 4): every line in apps/web/lighthouserc.cjs
// may only move toward the standard's budget, never away from it. This compares each assertion CI will run
// (page by page, audit by audit) with the same file on the base branch and fails if any is looser: a lower
// minimum score, a higher maximum, an assertion dropped, warned instead of failed, or judged on anything
// but the median of the runs. A file not yet on the base branch passes, since there is nothing to loosen.
//   node scripts/check-lighthouse-ratchet.mjs [base ref, default origin/main]
import { execFileSync } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const FILE = "frontend/apps/web/lighthouserc.cjs";
const base = process.argv[2] ?? "origin/main";
const git = (...args) => execFileSync("git", args, { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] });

try {
  git("rev-parse", "--verify", "--quiet", `${base}^{commit}`);
} catch {
  throw new Error(`base ${base} is not fetched; fetch it first, or the ratchet cannot be checked`);
}

let baseSource;
try {
  baseSource = git("show", `${base}:${FILE}`);
} catch {
  console.log(`${FILE} is not on ${base} yet: nothing to loosen.`);
  process.exit(0);
}

const require = createRequire(import.meta.url);
const baseCopy = join(mkdtempSync(join(tmpdir(), "lhci-ratchet-")), "lighthouserc.cjs");
writeFileSync(baseCopy, baseSource);
const before = require(baseCopy).ci.assert.assertMatrix;
const after = require(resolve(git("rev-parse", "--show-toplevel").trim(), FILE)).ci.assert.assertMatrix;

const faults = [];
for (const old of before) {
  const now = after.find((entry) => entry.matchingUrlPattern === old.matchingUrlPattern);
  if (!now) {
    faults.push(`${old.matchingUrlPattern}: the page is no longer checked`);
    continue;
  }
  for (const [audit, [oldLevel, oldOptions]] of Object.entries(old.assertions)) {
    const where = `${old.matchingUrlPattern} ${audit}`;
    const current = now.assertions[audit];
    if (!current) {
      faults.push(`${where}: assertion dropped`);
      continue;
    }
    const [level, options] = current;
    if (oldLevel === "error" && level !== "error") faults.push(`${where}: "${level}" no longer fails the build`);
    if ((oldOptions.aggregationMethod ?? "optimistic") === "median" && options.aggregationMethod !== "median") {
      faults.push(`${where}: no longer judged on the median run (${options.aggregationMethod ?? "optimistic"})`);
    }
    if (oldOptions.minScore !== undefined && !(options.minScore >= oldOptions.minScore)) {
      faults.push(`${where}: minScore ${oldOptions.minScore} -> ${options.minScore}`);
    }
    if (oldOptions.maxNumericValue !== undefined && !(options.maxNumericValue <= oldOptions.maxNumericValue)) {
      faults.push(`${where}: maxNumericValue ${oldOptions.maxNumericValue} -> ${options.maxNumericValue}`);
    }
  }
}

if (faults.length > 0) {
  console.error(`The Lighthouse ratchet was loosened against ${base} (a line may only move toward the budget):`);
  for (const fault of faults) console.error(`  ${fault}`);
  process.exit(1);
}
console.log(`Lighthouse ratchet: no line looser than on ${base}.`);
