import { test } from "node:test";
import assert from "node:assert/strict";
import { ORBIT_FRAMES, frameAt, frameSrc, progressThrough, widthFor } from "./orbit.ts";

test("the first frame at the top of the stage and the last at its end, never outside the set", () => {
  assert.equal(frameAt(0), 0);
  assert.equal(frameAt(1), ORBIT_FRAMES - 1);
  assert.equal(frameAt(0.5), Math.round(0.5 * (ORBIT_FRAMES - 1)));
  assert.equal(frameAt(-3), 0);
  assert.equal(frameAt(7), ORBIT_FRAMES - 1);
  assert.equal(frameAt(Number.NaN), 0);
  assert.equal(frameAt(0.5, 0), 0);
});

test("every frame is reached once, in order, as the reader scrolls down", () => {
  const seen = new Set<number>();
  let last = -1;
  for (let step = 0; step <= 1000; step += 1) {
    const frame = frameAt(step / 1000);
    assert.ok(frame >= last, `frame ${frame} after ${last}`);
    last = frame;
    seen.add(frame);
  }
  assert.equal(seen.size, ORBIT_FRAMES);
});

test("progress runs from the stage's top reaching the viewport's top to its end leaving the viewport", () => {
  assert.equal(progressThrough(0, 3000, 1000), 0);
  assert.equal(progressThrough(-1000, 3000, 1000), 0.5);
  assert.equal(progressThrough(-2000, 3000, 1000), 1);
  assert.equal(progressThrough(-9000, 3000, 1000), 1);
  assert.equal(progressThrough(400, 3000, 1000), 0);
  assert.equal(progressThrough(-100, 800, 1000), 0, "a stage shorter than the screen does not scrub");
});

test("each screen loads the smallest frames that are not soft on it", () => {
  assert.equal(widthFor(320, 2), 640, "320 points at 2x is 640 pixels");
  assert.equal(widthFor(390, 2), 960, "390 points at 2x is 780 pixels: 640 would be soft");
  assert.equal(widthFor(390, 3), 960, "past 2x the extra density is not paid for");
  assert.equal(widthFor(360, 1), 640);
  assert.equal(widthFor(1440, 1), 1280);
  assert.equal(widthFor(2560, 2), 1280, "nothing larger exists");
  assert.equal(widthFor(400, 0), 640, "a density of zero counts as one");
});

test("frame paths are two-digit and per width", () => {
  assert.equal(frameSrc(0, 640), "/landing/orbit/640/f00.webp");
  assert.equal(frameSrc(47, 1280), "/landing/orbit/1280/f47.webp");
});
