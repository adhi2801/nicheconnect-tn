// What changed in the backend's API contract since the frontend last looked.
// Usage: pnpm api:changes [from-ref] [to-ref]
//   from-ref defaults to the commit in design/api-reviewed.txt; to-ref defaults to HEAD.
//   pnpm api:changes --mark   records HEAD as reviewed (do this after the designs catch up).
import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";

const root = execFileSync("git", ["rev-parse", "--show-toplevel"], { encoding: "utf8" }).trim();
const marker = new URL("../design/api-reviewed.txt", import.meta.url);
const git = (...a) => execFileSync("git", ["-C", root, ...a], { encoding: "utf8", maxBuffer: 64 * 1024 * 1024 }).trim();
const contractAt = (ref) => JSON.parse(git("show", `${ref}:docs/api/openapi.json`));

if (process.argv[2] === "--mark") {
  const head = git("rev-parse", "--short", "HEAD");
  writeFileSync(marker, head + "\n");
  console.log(`marked ${head} as reviewed`);
  process.exit(0);
}

const from = process.argv[2] ?? readFileSync(marker, "utf8").trim();
const to = process.argv[3] ?? "HEAD";
const a = contractAt(from);
const b = contractAt(to);

const METHODS = ["get", "post", "put", "patch", "delete"];
const ops = (d) => new Map(Object.entries(d.paths).flatMap(([p, v]) => METHODS.filter((m) => v[m]).map((m) => [`${m.toUpperCase()} ${p}`, v[m].summary ?? ""])));
const oa = ops(a);
const ob = ops(b);
const added = [...ob].filter(([k]) => !oa.has(k));
const removed = [...oa].filter(([k]) => !ob.has(k));

const sa = a.components?.schemas ?? {};
const sb = b.components?.schemas ?? {};
const fieldChanges = [];
for (const name of Object.keys(sb)) {
  if (!sa[name]) continue;
  const pa = new Set(Object.keys(sa[name].properties ?? {}));
  const pb = new Set(Object.keys(sb[name].properties ?? {}));
  const plus = [...pb].filter((k) => !pa.has(k));
  const minus = [...pa].filter((k) => !pb.has(k));
  if (plus.length || minus.length) fieldChanges.push({ name, plus, minus });
}
const newSchemas = Object.keys(sb).filter((k) => !sa[k]);

console.log(`API changes ${from}..${git("rev-parse", "--short", to)}: ${oa.size} to ${ob.size} operations`);
console.log(`\nAdded operations (${added.length}):`);
for (const [k, s] of added) console.log(`  ${k}  ${s}`);
console.log(`\nRemoved operations (${removed.length}):`);
for (const [k, s] of removed) console.log(`  ${k}  ${s}`);
console.log(`\nFields added or removed on existing schemas (${fieldChanges.length}):`);
for (const c of fieldChanges) console.log(`  ${c.name}${c.plus.length ? "  + " + c.plus.join(", ") : ""}${c.minus.length ? "  - " + c.minus.join(", ") : ""}`);
console.log(`\nNew schemas: ${newSchemas.length}`);
