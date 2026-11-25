import { test } from "node:test";
import assert from "node:assert/strict";
import { checkStepOne, checkStepTwo, isAdult, MAX_NICHES, NICHES, normalizeHandle, problemsFromServer, profileBody, stepOf, todayInIndia, toggleNiche } from "./onboarding.ts";

test("a handle is stored as the backend stores it", () => {
  assert.equal(normalizeHandle("  @Priya.Eats "), "priya.eats");
  assert.equal(normalizeHandle("@@kovai_bites"), "kovai_bites");
});

test("a handle must be 3 to 30 lowercase letters, numbers, dots or underscores", () => {
  const p = (handle: string) => checkStepOne({ displayName: "Priya", handle }).handle;
  assert.equal(p("priya.eats"), undefined);
  assert.equal(p("@Priya_Eats"), undefined); // normalised first
  assert.equal(p("ab"), "onboarding.errors.handleShape");
  assert.equal(p("a".repeat(31)), "onboarding.errors.handleShape");
  assert.equal(p("priya eats"), "onboarding.errors.handleShape");
  assert.equal(p("priya-eats"), "onboarding.errors.handleShape");
  assert.equal(p("   "), "onboarding.errors.handleMissing");
});

test("a name is needed and at most 100 characters", () => {
  assert.equal(checkStepOne({ displayName: "  ", handle: "abc" }).displayName, "onboarding.errors.nameMissing");
  assert.equal(checkStepOne({ displayName: "x".repeat(101), handle: "abc" }).displayName, "onboarding.errors.nameLong");
  assert.deepEqual(checkStepOne({ displayName: "x".repeat(100), handle: "abc" }), {});
});

test("18 or over is decided on the date, the day of the eighteenth birthday counting", () => {
  assert.equal(isAdult("2008-11-25", "2026-11-25"), true);
  assert.equal(isAdult("2008-11-26", "2026-11-25"), false);
  assert.equal(isAdult("1990-01-01", "2026-11-25"), true);
});

test("someone born on 29 February turns 18 on 1 March in a year without one", () => {
  assert.equal(isAdult("2008-02-29", "2026-02-28"), false);
  assert.equal(isAdult("2008-02-29", "2026-03-01"), true);
  assert.equal(isAdult("2004-02-29", "2022-02-28"), false); // 2022 has no 29 February either
  assert.equal(isAdult("2000-02-29", "2018-02-28"), false);
});

test("today is Tamil Nadu's date, not the device's time zone", () => {
  assert.equal(todayInIndia(new Date("2026-11-24T19:00:00Z")), "2026-11-25"); // 00:30 in India
  assert.equal(todayInIndia(new Date("2026-11-24T18:00:00Z")), "2026-11-24");
});

test("step two needs a city, one to five niches and a real date of birth of an adult", () => {
  const today = "2026-11-25";
  const good = { city: "Madurai", niches: ["food" as const], dateOfBirth: "2000-04-14" };
  assert.deepEqual(checkStepTwo(good, today), {});
  assert.equal(checkStepTwo({ ...good, city: " M " }, today).city, "onboarding.errors.cityMissing");
  assert.equal(checkStepTwo({ ...good, city: "x".repeat(61) }, today).city, "onboarding.errors.cityLong");
  assert.equal(checkStepTwo({ ...good, niches: [] }, today).niches, "onboarding.errors.nichesMissing");
  assert.equal(checkStepTwo({ ...good, niches: [...NICHES] }, today).niches, "onboarding.errors.nichesTooMany");
  assert.equal(checkStepTwo({ ...good, dateOfBirth: "" }, today).dateOfBirth, "onboarding.errors.dobMissing");
  assert.equal(checkStepTwo({ ...good, dateOfBirth: "2001-02-30" }, today).dateOfBirth, "onboarding.errors.dobInvalid");
  assert.equal(checkStepTwo({ ...good, dateOfBirth: "2027-01-01" }, today).dateOfBirth, "onboarding.errors.dobInvalid");
  assert.equal(checkStepTwo({ ...good, dateOfBirth: "2010-01-01" }, today).dateOfBirth, "onboarding.errors.underage");
});

test("niches toggle, and a sixth is never added", () => {
  let chosen = toggleNiche([], "food");
  assert.deepEqual(chosen, ["food"]);
  chosen = toggleNiche(chosen, "food");
  assert.deepEqual(chosen, []);
  const five = NICHES.slice(0, MAX_NICHES);
  assert.deepEqual(toggleNiche(five, "lifestyle"), [...five]);
});

test("the body is trimmed and normalised, in English (D-054)", () => {
  const body = profileBody({ displayName: " Priya Eats ", handle: "@Priya.Eats" }, { city: " Madurai ", niches: ["food"], dateOfBirth: "2000-04-14" });
  assert.deepEqual(body, { display_name: "Priya Eats", handle: "priya.eats", city: "Madurai", niches: ["food"], languages: ["en"], date_of_birth: "2000-04-14" });
});

test("a refusal from the backend lands on its field in our words, and on the right step", () => {
  assert.deepEqual(problemsFromServer("handle_taken", []), { handle: "onboarding.errors.handleTaken" });
  assert.deepEqual(problemsFromServer("must_be_18_or_over", []), { dateOfBirth: "onboarding.errors.underage" });
  const many = problemsFromServer("validation_failed", [{ field: "city", message: "String should have at least 2 characters" }, { field: "unknown_field", message: "?" }]);
  assert.deepEqual(many, { city: "onboarding.errors.cityMissing" });
  assert.equal(stepOf({ handle: "onboarding.errors.handleTaken" }), 1);
  assert.equal(stepOf({ city: "onboarding.errors.cityMissing" }), 2);
});
