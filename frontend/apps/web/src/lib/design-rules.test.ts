import { strict as assert } from "node:assert";
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { test } from "node:test";
import { DESIGNS } from "../design/registry.ts";
import { SLOTS } from "../design/slots.ts";

// The rules that keep a design from affecting the website around it (HD-002, frontend/design/website-plan.md section 3), checked on
// the source. The browser test e2e/design-slots.spec.ts checks the same promise on the rendered page.

const SRC = join(import.meta.dirname, "..");
const files = (dir: string): string[] =>
  !existsSync(dir) ? [] : readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? files(path) : [path];
  });
const code = (paths: string[]) => paths.filter((p) => /\.(tsx?|css)$/.test(p) && !p.endsWith(".test.ts"));

test("every slot's box has a height of its own, so it is never empty space of no size", () => {
  // The box is contained (contain: size), so it takes no height from what is inside: its size must say one.
  for (const [id, slot] of Object.entries(SLOTS)) assert.match(slot.size, /(^|\s)(aspect-|h-)/, `${id}: give it an aspect ratio or a height`);
});

test("only known slots have designs", () => {
  for (const id of Object.keys(DESIGNS)) assert.ok(id in SLOTS, `${id} is not a slot in src/design/slots.ts`);
});

test("a page never sizes a slot: its size lives in slots.ts", () => {
  const sizing = /^!?(?:[a-z]+:)*(?:h|w|min-h|min-w|max-h|max-w|size|aspect)-/;
  let seen = 0;
  for (const path of code(files(SRC))) {
    for (const [, classes = ""] of readFileSync(path, "utf8").matchAll(/<DesignSlot\b[^>]*?className="([^"]*)"/g)) {
      seen += 1;
      const bad = classes.split(/\s+/).filter((c) => sizing.test(c));
      assert.deepEqual(bad, [], `${relative(SRC, path)}: move ${bad.join(" ")} into the slot's size in src/design/slots.ts`);
    }
  }
  assert.ok(seen > 0, "the check found the slots it guards");
});

test("a design's styles are its own: no global stylesheet, no :global, no style tag", () => {
  for (const path of files(join(SRC, "design", "art"))) {
    const where = relative(SRC, path);
    if (path.endsWith(".css")) assert.ok(path.endsWith(".module.css"), `${where}: use a CSS module, never a global stylesheet`);
    if (/\.(tsx?|css)$/.test(path)) {
      const text = readFileSync(path, "utf8");
      assert.doesNotMatch(text, /:global\b/, `${where}: :global reaches outside the design`);
      assert.doesNotMatch(text, /<style\b|document\.(head|body|documentElement)/, `${where}: a design changes only its own box`);
    }
  }
});

test("the public site's parts take every colour from the tokens", () => {
  const raw = /#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?|oklch|oklab|lab|lch)\(|\b(?:bg|text|border|fill|stroke|from|to|via|ring|outline|shadow|decoration|caret|accent)-(?:white|black|(?:slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-\d{2,3})\b/;
  const parts = code([
    ...files(join(SRC, "components", "site")),
    ...files(join(SRC, "components", "home")),
    ...files(join(SRC, "design")).filter((p) => !p.includes(`${join("design", "art")}`)),
    join(SRC, "app", "page.tsx"),
  ]);
  assert.ok(parts.length >= 5, "the check found the files it guards");
  for (const path of parts) {
    const found = readFileSync(path, "utf8").match(raw);
    assert.equal(found, null, `${relative(SRC, path)}: ${found?.[0]} is a raw colour; use a token (tokens/tokens.json)`);
  }
});
