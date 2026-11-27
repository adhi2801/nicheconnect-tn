import { expect, test, type Browser, type Page } from "@playwright/test";

// HD-002 (frontend/design/DESIGN_DECISIONS.md), as a test: a design added to a slot later must not affect the website "in any way".
// Every slot on the page is filled with a deliberately unruly design (a layer fixed over the whole window, a box thousands of pixels
// wide placed far outside the slot, oversized text, a sticky shadow) and the rest of the page is compared before and after: the place
// and size of every element outside the slots, and every pixel outside them.

// Pages with design slots. A page added to the website with a slot is added here.
const PAGES = ["/"];
const VIEWS = [
  { name: "phone", width: 360, height: 780 },
  { name: "laptop", width: 1280, height: 800 },
] as const;

const UNRULY = `
  <div data-unruly style="position:fixed;inset:0;z-index:2147483647;background:#ff00ff"></div>
  <div data-unruly style="position:absolute;left:-2000px;top:-2000px;width:6000px;height:6000px;background:rgb(0 200 0 / 0.6)"></div>
  <div data-unruly style="width:3000px;height:3000px;margin:-120px;font:900 240px/1 serif;color:#0000ff">AN UNRULY DESIGN</div>
  <div data-unruly style="position:sticky;top:0;height:9000px;box-shadow:0 0 0 4000px #ff0000"></div>`;

// Where every element outside the slots sits (the slots' own boxes included), rounded to a hundredth of a pixel.
const layout = (page: Page) =>
  page.evaluate(() =>
    [...document.querySelectorAll("body *")]
      .filter((el) => el.matches("[data-slot]") || !el.closest("[data-slot]"))
      .map((el) => {
        const r = el.getBoundingClientRect();
        return `${el.tagName} ${[r.x, r.y + window.scrollY, r.width, r.height].map((n) => Math.round(n * 100) / 100).join(",")}`;
      }),
  );

// Pixels are compared in a browser canvas (no image library). Chrome's anti-aliasing of an edge can change by a few levels between two
// screenshots of the same page with nothing changed at all (measured 27 November 2026: one pixel at a button's rounded edge, 9 of 255,
// flipping on every screenshot). So a pixel may move by at most EDGE levels, and only on a handful of pixels; anything a design could
// draw outside its box (the unruly one paints whole areas in pure magenta, green, red and blue) changes pixels by up to 255.
const EDGE = 12;
const MAX_EDGE_PIXELS = 50;
async function pixelChange(browser: Browser, before: Buffer, after: Buffer) {
  const page = await browser.newPage();
  try {
    return await page.evaluate(async ([a, b]) => {
      const load = (src: string) => new Promise<HTMLImageElement>((done) => { const img = new Image(); img.onload = () => done(img); img.src = `data:image/png;base64,${src}`; });
      const pixels = (img: HTMLImageElement) => {
        const canvas = document.createElement("canvas");
        canvas.width = img.width;
        canvas.height = img.height;
        const context = canvas.getContext("2d")!; // a 2D context always exists on a fresh canvas
        context.drawImage(img, 0, 0);
        return context.getImageData(0, 0, img.width, img.height).data;
      };
      const [x, y] = await Promise.all([load(a), load(b)]);
      if (x.width !== y.width || x.height !== y.height) return { sameSize: false, largest: 255, changed: Infinity };
      const p = pixels(x), q = pixels(y);
      let largest = 0, changed = 0;
      for (let i = 0; i < p.length; i += 4) {
        const d = Math.max(Math.abs(p[i]! - q[i]!), Math.abs(p[i + 1]! - q[i + 1]!), Math.abs(p[i + 2]! - q[i + 2]!)); // in bounds: i < length
        if (d > 0) changed += 1;
        largest = Math.max(largest, d);
      }
      return { sameSize: true, largest, changed };
    }, [before.toString("base64"), after.toString("base64")]);
  } finally {
    await page.close();
  }
}

for (const path of PAGES) {
  for (const view of VIEWS) {
    test(`${path}: a design in any slot changes nothing outside it, ${view.name}`, async ({ page, browser }) => {
      await page.setViewportSize({ width: view.width, height: view.height });
      await page.goto(path);
      await page.evaluate(() => document.fonts.ready);
      const slots = page.locator("[data-slot]");
      expect(await slots.count(), "the page has design slots to fill").toBeGreaterThan(0);
      // Every slot has a real box: one that collapsed to nothing would pass this test while hiding its design.
      for (const box of await slots.evaluateAll((els) => els.filter((el) => el.checkVisibility()).map((el) => el.getBoundingClientRect().height))) expect(box).toBeGreaterThan(0);

      const shot = () => page.screenshot({ fullPage: true, animations: "disabled", caret: "hide", mask: [slots], maskColor: "#808080" });
      const before = { layout: await layout(page), image: await shot() };

      await page.evaluate((html) => {
        for (const slot of document.querySelectorAll("[data-slot]")) slot.insertAdjacentHTML("afterbegin", html);
      }, UNRULY);
      expect(await page.locator("[data-unruly]").count(), "the unruly design is in every slot").toBe((await slots.count()) * 4);

      expect(await layout(page), "no element outside the slots moved or changed size").toEqual(before.layout);
      const change = await pixelChange(browser, before.image, await shot());
      expect(change.sameSize, "the page is the same size").toBe(true);
      expect(change.largest, "no pixel outside the slots changed beyond edge smoothing").toBeLessThanOrEqual(EDGE);
      expect(change.changed, "only a handful of edge pixels may differ at all").toBeLessThanOrEqual(MAX_EDGE_PIXELS);
    });
  }
}
