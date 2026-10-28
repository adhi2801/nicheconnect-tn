import { test } from "node:test";
import assert from "node:assert/strict";
import { formatDate, formatDayMonth, formatLongDate, formatPaise, initials, partOfDay } from "./format.ts";

test("money is in whole rupees with Indian grouping, and paise only when there are some", () => {
  assert.equal(formatPaise(15_000_000), "₹1,50,000");
  assert.equal(formatPaise(700_000), "₹7,000");
  assert.equal(formatPaise(0), "₹0");
  assert.equal(formatPaise(12_345_678), "₹1,23,456.78");
  assert.equal(formatPaise(10_000_000_00), "₹1,00,00,000");
});

test("a calendar date reads the same on every side of the world", () => {
  assert.equal(formatDate("2026-09-17"), "17 Sep 2026");
  assert.equal(formatDayMonth("2026-10-14"), "14 Oct");
  assert.equal(formatLongDate("2026-10-28"), "Wednesday 28 October");
  const saved = process.env.TZ;
  for (const tz of ["Pacific/Honolulu", "Asia/Kolkata", "Pacific/Kiritimati"]) {
    process.env.TZ = tz;
    assert.equal(formatLongDate("2026-10-28"), "Wednesday 28 October", tz);
  }
  process.env.TZ = saved;
});

test("the greeting follows Indian time, whatever the device's zone", () => {
  assert.equal(partOfDay(new Date("2026-10-28T02:00:00Z")), "morning"); // 07:30 in India
  assert.equal(partOfDay(new Date("2026-10-28T08:00:00Z")), "afternoon"); // 13:30
  assert.equal(partOfDay(new Date("2026-10-28T13:00:00Z")), "evening"); // 18:30
  assert.equal(partOfDay(new Date("2026-10-27T19:00:00Z")), "morning"); // 00:30
});

test("initials", () => {
  assert.equal(initials("Lakshmi Loves"), "LL");
  assert.equal(initials("Chennai Bakes"), "CB");
  assert.equal(initials("Priya"), "PR");
  assert.equal(initials("  "), "?");
});
