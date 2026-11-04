// The landing page reads without JavaScript (frontend.md section 8d): its headline and every section's heading
// must be in the HTML the server sends, before any script runs. A search engine, a link preview, or a phone on a
// slow link that has not run the script yet sees exactly this.
// Usage: node scripts/check-no-js.mjs [url]   (default http://127.0.0.1:3100/)
import { readFileSync } from "node:fs";

const url = process.argv[2] ?? "http://127.0.0.1:3100/";
const words = JSON.parse(readFileSync(new URL("../apps/web/src/messages/en.json", import.meta.url), "utf8")).landing;
const expected = [
  words.hero.title,
  words.hero.lede,
  words.steps.title,
  ...Object.values(words.steps.items).map((item) => item.title),
  words.record.title,
  words.money.title,
  words.sides.brands.title,
  words.sides.creators.title,
  words.closing.title,
];

const html = await (await fetch(url, { headers: { "user-agent": "colyv-no-js-check" } })).text();
const text = html
  .replace(/<script[\s\S]*?<\/script>/g, " ")
  .replace(/<[^>]+>/g, " ")
  .replace(/&#x27;|&#39;/g, "'")
  .replace(/&quot;/g, '"')
  .replace(/&lt;/g, "<")
  .replace(/&gt;/g, ">")
  .replace(/&amp;/g, "&")
  .replace(/\s+/g, " ");

const missing = expected.filter((line) => !text.includes(line.replace(/\s+/g, " ")));
if (missing.length) {
  for (const line of missing) console.log(`::error::not in the server's HTML: ${line}`);
  process.exitCode = 1;
} else {
  console.log(`all ${expected.length} lines are in the server's HTML, no script needed`);
}
