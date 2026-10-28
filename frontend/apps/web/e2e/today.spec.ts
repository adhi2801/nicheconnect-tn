import { expect, test, type Page } from "@playwright/test";

const MOCK = "http://localhost:8098";
const scenario = (body: object) => fetch(`${MOCK}/__scenario`, { method: "POST", body: JSON.stringify(body) });
const calls = async (): Promise<Record<string, number>> => (await (await fetch(`${MOCK}/__state`)).json()).calls;

test.beforeEach(async () => { await fetch(`${MOCK}/__reset`, { method: "POST", body: "{}" }); });

async function signIn(page: Page, role: "Creator" | "Brand" = "Creator") {
  await page.goto("/sign-in");
  await page.locator("label", { hasText: new RegExp(`^${role}`) }).click();
  await page.getByLabel("Mobile number").fill("9876543210");
  await page.getByRole("button", { name: "Send code" }).click();
  await page.getByLabel("6-digit code").fill("123456");
  await expect(page).toHaveURL(/\/app$/);
}

test("a creator's Today greets by name and lists what needs them, most urgent first", async ({ page }) => {
  await signIn(page);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(/^Good (morning|afternoon|evening), Lakshmi Loves$/);
  await expect(page.getByText("Wednesday 28 October")).toBeVisible();
  await expect(page.getByText("7 things need you.")).toBeVisible();
  const rows = page.locator("#needs-you ul > li");
  await expect(rows).toHaveCount(5);
  await expect(rows.first()).toContainText("New sign-in on Chrome on Windows");
  await expect(rows.first()).toContainText("Security");
  await expect(rows.nth(1)).toContainText("Confirm you received the payment");
  await expect(rows.nth(1)).toContainText("Chennai Bakes · Diwali sweets reel");
  await expect(rows.nth(1)).toContainText("₹7,000");
  await expect(rows.nth(1)).toContainText("Due today");
  await expect(rows.nth(2)).toContainText("3 days late");
  await expect(rows.nth(1).getByRole("link", { name: "Check payment" })).toHaveAttribute("href", "/app/deals/m-1");
});

test("the rest of the list opens on request, and closes again", async ({ page }) => {
  await signIn(page);
  const rows = page.locator("#needs-you ul > li");
  await page.getByRole("button", { name: "Show all 7" }).click();
  await expect(rows).toHaveCount(7);
  await page.getByRole("button", { name: "Show fewer" }).click();
  await expect(rows).toHaveCount(5);
});

test("a brand sees its own navigation and handles as @handle", async ({ page }) => {
  await signIn(page, "Brand");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(/Chennai Bakes$/);
  await expect(page.locator("#needs-you").getByText("3 new applications to review")).toBeVisible();
  await expect(page.getByText("3 new applications to review").first()).toBeVisible(); // and the hero card names the most urgent one
  await expect(page.locator("#needs-you").getByText("@priya · Diwali sweets reel")).toBeVisible();
  await expect(page.getByRole("link", { name: "Campaigns" }).first()).toBeVisible();
  await expect(page.getByRole("link", { name: "Discover" })).toHaveCount(0);
});

test("payments show what each role acts on first, with late money called out", async ({ page }) => {
  await signIn(page);
  await expect(page.getByText("Waiting for you to confirm")).toBeVisible();
  await expect(page.getByText("₹6,500 is late")).toBeVisible();
  await expect(page.getByText("₹1,25,000").first()).toBeVisible(); // confirmed so far, Indian grouping
});

test("when nothing needs the person, Today says so calmly and points forward", async ({ page }) => {
  await scenario({ attention: "empty", totals: "zero" });
  await signIn(page);
  await expect(page.getByText("You are all caught up.")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Nothing needs you right now" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Browse campaigns" }).first()).toHaveAttribute("href", "/app/discover");
  await expect(page.getByText("Nothing yet").first()).toBeVisible();
});

test("a new account is asked to finish its profile first", async ({ page }) => {
  await scenario({ profile: "missing", attention: "empty" });
  await signIn(page);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Welcome to Colyv"); // no name yet, and no placeholder left behind
  await expect(page.getByRole("heading", { name: "Finish setting up your profile" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Set up my profile" })).toHaveAttribute("href", "/app/onboarding");
  // Before a profile exists there are no payments to show and nothing is "all clear".
  await expect(page.getByText("Nothing needs you right now")).toHaveCount(0);
  await expect(page.getByText("Payments")).toHaveCount(0);
  await expect(page.getByText("Waiting for you to confirm")).toHaveCount(0);
});

test("a failed load says what happened, offers a retry, and the retry works", async ({ page }) => {
  await scenario({ attention: "error" });
  await signIn(page);
  await expect(page.getByRole("alert").filter({ hasText: "We could not load Today" })).toBeVisible();
  await scenario({ attention: "items" });
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(page.getByText("7 things need you.")).toBeVisible();
});

test("a busy backend is retried quietly and the person never sees an error", async ({ page }) => {
  await scenario({ busyOnce: true });
  await signIn(page);
  await expect(page.getByText("7 things need you.")).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText("We could not load Today")).toHaveCount(0);
  expect((await calls())["/api/v1/me/attention"]).toBe(2);
});

test("a payments failure does not take Today down with it", async ({ page }) => {
  await scenario({ totals: "error" });
  await signIn(page);
  await expect(page.getByText("7 things need you.")).toBeVisible();
  await expect(page.getByText("Payments could not be loaded")).toBeVisible();
});

test("the bell shows how many are unread, to a screen reader too", async ({ page }) => {
  await signIn(page);
  await expect(page.getByRole("link", { name: "3 unread notifications" })).toBeVisible();
});

test("the navigation marks where you are, and a screen not built yet answers kindly", async ({ page }) => {
  await signIn(page);
  await expect(page.getByRole("link", { name: "Today" }).first()).toHaveAttribute("aria-current", "page");
  await page.getByRole("link", { name: "Inbox" }).first().click();
  await expect(page).toHaveURL(/\/app\/inbox$/);
  await expect(page.getByRole("heading", { name: "This screen is being built" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Inbox" }).first()).toHaveAttribute("aria-current", "page");
  await page.getByRole("link", { name: "Back to Today" }).click();
  await expect(page).toHaveURL(/\/app$/);
});

test("on a laptop the navigation is a sidebar, on a phone a bar at the bottom", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await signIn(page);
  // Both bars are in the page; CSS shows one. (Role queries skip hidden elements, so these use the label.)
  const nav = page.locator('nav[aria-label="Main"]');
  await expect(nav).toHaveCount(2);
  const [top, bottom] = [nav.first(), nav.last()];
  await expect(top).toBeVisible();
  await expect(bottom).toBeHidden();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(top).toBeHidden();
  await expect(bottom).toBeVisible();
  const box = await bottom.boundingBox();
  expect(box!.y + box!.height).toBeGreaterThan(800); // pinned to the bottom of the phone screen
});

test("nothing scrolls sideways on a phone", async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 740 });
  await signIn(page);
  await expect(page.getByText("7 things need you.")).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
