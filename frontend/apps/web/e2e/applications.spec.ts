import { expect, test, type Page } from "@playwright/test";

// C5: my applications, against the stand-in backend (e2e/mock-api.mjs).
const MOCK = "http://localhost:8098";
const scenario = (body: object) => fetch(`${MOCK}/__scenario`, { method: "POST", body: JSON.stringify(body) });
const state = async () => (await fetch(`${MOCK}/__state`)).json();

test.beforeEach(async () => { await fetch(`${MOCK}/__reset`, { method: "POST", body: "{}" }); });

async function open(page: Page, extra: object = {}) {
  await scenario(extra);
  await page.goto("/sign-in");
  await page.locator("label", { hasText: /^Creator/ }).click();
  await page.getByLabel("Mobile number").fill("9876543210");
  await page.getByRole("button", { name: "Send code" }).click();
  await page.getByLabel("6-digit code").fill("123456");
  await expect(page).toHaveURL(/\/app$/);
  await page.goto("/app/applications");
  await expect(page.getByRole("heading", { name: "My applications" })).toBeVisible();
}

test("applications are grouped, dated in India's calendar, with the campaign's name", async ({ page }) => {
  await open(page);
  await expect(page.getByRole("heading", { name: "In progress (2)" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Closed (2)" })).toBeVisible();
  const first = page.locator("article").first();
  await expect(first).toContainText("Temple town food walk 4"); // shortlisted leads
  await expect(first).toContainText("Shortlisted");
  const rejected = page.locator("article", { hasText: "Not chosen" });
  await expect(rejected).toContainText("Updated 19 Nov 2026"); // 19:00 UTC on the 18th is the 19th in India
  await expect(rejected).toContainText("The budget didn't match");
});

test("the brand's note is text with its warning beside it, never a link", async ({ page }) => {
  await open(page);
  const rejected = page.locator("article", { hasText: "Not chosen" });
  await expect(rejected).toContainText("Call me on 98765 43210 to discuss.");
  await expect(rejected).toContainText("This text has contact details.");
  await expect(rejected.locator("a[href^='tel:']")).toHaveCount(0);
});

test("a campaign that no longer exists still shows its application, said plainly", async ({ page }) => {
  await open(page);
  await expect(page.locator("article", { hasText: "Withdrawn" })).toContainText("This campaign is no longer available");
});

test("each campaign is read once, however many applications it has (the R7 stopgap stays bounded)", async ({ page }) => {
  await open(page);
  await expect(page.locator("article")).toHaveCount(4);
  const { calls } = await state();
  for (const id of ["c-2", "c-4", "c-6", "c-gone"]) expect(calls[`/api/v1/campaigns/${id}`]).toBe(1);
});

test("feedback shows facts with what they rest on", async ({ page }) => {
  await open(page);
  await expect(page.getByText("Most common reason across your 3 rejections: the budget didn't match")).toBeVisible();
  await expect(page.getByText("3 of your 4 quotes were above the campaign's maximum budget.")).toBeVisible();
});

test("withdrawing asks first, sends once with a key, then shows it as withdrawn", async ({ page }) => {
  await open(page);
  await page.locator("article", { hasText: "Sent" }).getByRole("button", { name: "Withdraw" }).click();
  await expect(page.getByRole("dialog")).toContainText("This is final.");
  await page.getByRole("button", { name: "Keep it" }).click();
  expect((await state()).writes).toHaveLength(0);
  await page.locator("article", { hasText: "Sent" }).getByRole("button", { name: "Withdraw" }).click();
  await page.getByRole("button", { name: "Withdraw application" }).click();
  await expect(page.getByText("Application withdrawn.")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Closed (3)" })).toBeVisible();
  const { writes } = await state();
  expect(writes).toHaveLength(1);
  expect(writes[0].key).toMatch(/^[0-9a-f-]{36}$/);
});

test("withdrawing something a brand just answered says so, and the list refreshes", async ({ page }) => {
  await open(page, { withdraw: "conflict" });
  await page.locator("article", { hasText: "Shortlisted" }).getByRole("button", { name: "Withdraw" }).click();
  await page.getByRole("button", { name: "Withdraw application" }).click();
  await expect(page.getByText("It wasn't withdrawn. Its status changed since this page loaded.", { exact: false })).toBeVisible();
});

test("only what a brand has not answered for good can be withdrawn", async ({ page }) => {
  await open(page);
  await expect(page.locator("article", { hasText: "Not chosen" }).getByRole("button", { name: "Withdraw" })).toHaveCount(0);
  await expect(page.locator("article", { hasText: "Shortlisted" }).getByRole("button", { name: "Withdraw" })).toHaveCount(1);
});

test("no applications yet points to Discover; a failed load offers a retry", async ({ page }) => {
  await open(page, { applications: "empty" });
  await expect(page.getByRole("heading", { name: "No applications yet" })).toBeVisible();
  await scenario({ applications: "error" });
  await page.reload();
  await expect(page.getByText("Your applications didn't load")).toBeVisible();
});

test("Discover stays marked in the navigation on My applications", async ({ page }) => {
  await open(page);
  await expect(page.getByRole("navigation", { name: "Main" }).first().getByRole("link", { name: "Discover" })).toHaveAttribute("aria-current", "page");
});
