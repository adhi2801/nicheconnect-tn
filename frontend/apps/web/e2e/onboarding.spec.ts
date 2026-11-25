import { expect, test, type Page } from "@playwright/test";

// C0: a new creator's two steps, against the stand-in backend (e2e/mock-api.mjs).
const MOCK = "http://localhost:8098";
const scenario = (body: object) => fetch(`${MOCK}/__scenario`, { method: "POST", body: JSON.stringify(body) });
const state = async () => (await fetch(`${MOCK}/__state`)).json();

test.beforeEach(async () => { await fetch(`${MOCK}/__reset`, { method: "POST", body: "{}" }); });

async function newCreator(page: Page, extra: object = {}) {
  await scenario({ profile: "missing", attention: "empty", ...extra });
  await page.goto("/sign-in");
  await page.locator("label", { hasText: /^Creator/ }).click();
  await page.getByLabel("Mobile number").fill("9876543210");
  await page.getByRole("button", { name: "Send code" }).click();
  await page.getByLabel("6-digit code").fill("123456");
  await expect(page).toHaveURL(/\/app$/);
  await page.getByRole("link", { name: "Set up my profile" }).click();
  await expect(page).toHaveURL(/\/app\/onboarding$/);
}

async function stepOne(page: Page, handle = "@Meena.Makes") {
  await page.getByLabel("Your name, as brands will see it").fill("Meena Makes Food");
  await page.getByLabel("Handle").fill(handle);
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByRole("heading", { name: "Where and what" })).toBeVisible();
}

async function stepTwo(page: Page, dob = "1998-06-14") {
  await page.getByLabel("City").fill("Madurai");
  await page.getByRole("button", { name: "Food" }).click();
  await page.getByLabel("Date of birth").fill(dob);
  await page.getByRole("button", { name: "Finish setup" }).click();
}

test("a new creator sets up in two steps and lands on Discover; the profile is sent once, with a key", async ({ page }) => {
  await newCreator(page);
  await expect(page.getByText("Step 1 of 2")).toBeVisible();
  await stepOne(page);
  await expect(page.getByText("Step 2 of 2")).toBeVisible();
  await stepTwo(page);
  await expect(page).toHaveURL(/\/app\/discover$/);
  const { writes } = await state();
  expect(writes).toHaveLength(1);
  expect(writes[0].key).toMatch(/^[0-9a-f-]{36}$/);
  expect(writes[0].body).toEqual({ display_name: "Meena Makes Food", handle: "meena.makes", city: "Madurai", niches: ["food"], languages: ["en"], date_of_birth: "1998-06-14" });
});

test("each field says what is wrong before anything is sent, and the error goes once the field is edited", async ({ page }) => {
  await newCreator(page);
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByText("Enter the name brands will see.")).toBeVisible();
  await expect(page.getByText("Choose a handle.")).toBeVisible();
  await page.getByLabel("Handle").fill("a b");
  await expect(page.getByText("Choose a handle.")).toHaveCount(0);
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByText("Use 3 to 30 characters: lowercase letters, numbers, dots or underscores.")).toBeVisible();
  await expect(page.getByLabel("Handle")).toHaveAttribute("aria-invalid", "true");
  expect((await state()).writes).toHaveLength(0);
});

test("under 18 is refused on the device, in plain words, and nothing is sent", async ({ page }) => {
  await newCreator(page);
  await stepOne(page);
  await stepTwo(page, "2012-01-01");
  await expect(page.getByText("Colyv is for people 18 or over, so you can't sign up yet.")).toBeVisible();
  expect((await state()).writes).toHaveLength(0);
});

test("a handle taken on the server takes the person back to step 1, to that field", async ({ page }) => {
  await newCreator(page, { createProfile: "handle_taken" });
  await stepOne(page);
  await stepTwo(page);
  await expect(page.getByRole("heading", { name: "About you" })).toBeVisible();
  await expect(page.getByText("That handle is taken. Try another, for example with your city added.")).toBeVisible();
  await expect(page.getByLabel("Handle")).toHaveValue("@Meena.Makes"); // what was typed is kept
});

test("the server's own age refusal lands on the date of birth", async ({ page }) => {
  await newCreator(page, { createProfile: "underage" });
  await stepOne(page);
  await stepTwo(page);
  await expect(page.getByText("Colyv is for people 18 or over, so you can't sign up yet.")).toBeVisible();
});

test("a busy backend is retried with the same key, so the profile is made once", async ({ page }) => {
  await newCreator(page, { createProfile: "busyOnce" });
  await stepOne(page);
  await stepTwo(page);
  await expect(page).toHaveURL(/\/app\/discover$/, { timeout: 10_000 });
  const { writes } = await state();
  expect(writes).toHaveLength(2);
  expect(writes[1].key).toBe(writes[0].key);
});

test("too many tries shows the wait, and keeps the form", async ({ page }) => {
  await newCreator(page, { createProfile: "rate" });
  await stepOne(page);
  await stepTwo(page);
  await expect(page.getByText("Too many tries in a short time. Try again in 40 seconds.")).toBeVisible();
  await expect(page.getByLabel("City")).toHaveValue("Madurai");
});

test("what was typed survives a reload, except the date of birth, which is never kept", async ({ page }) => {
  await newCreator(page);
  await stepOne(page);
  await page.getByLabel("City").fill("Madurai");
  await page.getByLabel("Date of birth").fill("1998-06-14");
  // Checked before the reload: once the form loads again it saves its (empty) date, which would hide a date kept a moment ago.
  await expect(page.getByLabel("Date of birth")).toHaveValue("1998-06-14");
  const stored = await page.evaluate(() => Object.entries(localStorage).filter(([k]) => k.startsWith("colyv-draft:")).map(([, v]) => v).join(""));
  expect(stored).toContain("Madurai"); // the draft is there
  expect(stored).not.toContain("1998-06-14"); // and the date of birth is not in it
  await page.reload();
  await expect(page.getByLabel("Handle")).toHaveValue("@Meena.Makes");
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByLabel("City")).toHaveValue("Madurai");
  await expect(page.getByLabel("Date of birth")).toHaveValue("");
});

test("someone who already has a profile is sent to Today", async ({ page }) => {
  await page.goto("/sign-in");
  await page.locator("label", { hasText: /^Creator/ }).click();
  await page.getByLabel("Mobile number").fill("9876543210");
  await page.getByRole("button", { name: "Send code" }).click();
  await page.getByLabel("6-digit code").fill("123456");
  await expect(page).toHaveURL(/\/app$/);
  await page.goto("/app/onboarding");
  await expect(page).toHaveURL(/\/app$/);
});

test("signing out wipes every draft", async ({ page }) => {
  await newCreator(page);
  await page.getByLabel("Handle").fill("meena");
  await page.goto("/app/me");
  await page.getByRole("button", { name: /Sign out/ }).first().click();
  await expect(page).toHaveURL(/\/sign-in$/);
  const drafts = await page.evaluate(() => Object.keys(localStorage).filter((k) => k.startsWith("colyv-draft:")));
  expect(drafts).toEqual([]);
});
