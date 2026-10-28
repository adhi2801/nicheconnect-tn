import { test } from "node:test";
import assert from "node:assert/strict";
import { formatIndianMobile, maskIndianMobile, normalizeIndianMobile } from "./phone.ts";

test("accepts the forms the API accepts and returns +91 and ten digits", () => {
  for (const input of ["9876543210", "+919876543210", "919876543210", "09876543210", "98765 43210", "+91 98765-43210", "(98765) 43210"]) {
    assert.equal(normalizeIndianMobile(input), "+919876543210", input);
  }
});

test("refuses numbers that are not Indian mobiles", () => {
  for (const input of ["", "12345", "5876543210", "98765432", "98765432101", "abcdefghij", "+14155550100", "+91 5876543210"]) {
    assert.equal(normalizeIndianMobile(input), null, input);
  }
});

test("formats and masks without changing the digits that remain", () => {
  assert.equal(formatIndianMobile("+919876543210"), "+91 98765 43210");
  assert.equal(maskIndianMobile("+919876543210"), "+91 ••••• ••210");
  assert.equal(maskIndianMobile("nonsense"), "your number");
});
