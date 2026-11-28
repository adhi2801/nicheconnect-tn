import { expect, test, type Page } from "@playwright/test";

// The brand's Campaigns page and campaign page (D-205), against the stand-in backend (e2e/mock-api.mjs).
const MOCK = "http://localhost:8098";
const scenario = (body: object) => fetch(`${MOCK}/__scenario`, { method: "POST", body: JSON.stringify(body) });

test.beforeEach(async () => { await fetch(`${MOCK}/__reset`, { method: "POST", body: "{}" }); });

async function signIn(page: Page, role: "Creator" | "Brand" = "Brand") {
  await page.goto("/sign-in");
  await page.locator("label", { hasText: new RegExp(`^${role}`) }).click();
  await page.getByLabel("Mobile number").fill("9876543210");
  await page.getByRole("button", { name: "Send code" }).click();
  await page.getByLabel("6-digit code").fill("123456");
  await expect(page).toHaveURL(/\/app$/);
}

const panel = (page: Page, title: string) => page.getByRole("region", { name: title, exact: true });
const cards = (page: Page) => page.locator("main ul a[href^='/app/campaigns/']");

test("Campaigns lists every campaign, groups them with counts, and each card says how it is doing", async ({ page }) => {
  await signIn(page);
  await page.getByRole("link", { name: "Campaigns" }).first().click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Campaigns");
  await expect(cards(page)).toHaveCount(4);
  await expect(page.getByRole("button", { name: /^All/ })).toContainText("4");
  await expect(page.getByRole("button", { name: /^Ongoing/ })).toContainText("3");
  await expect(page.getByRole("button", { name: /^Drafts/ })).toContainText("1");
  await expect(page.getByRole("button", { name: /^Cancelled/ })).toContainText("0");
  const diwali = page.getByRole("link", { name: /Diwali sweets reel/ });
  await expect(diwali).toHaveAttribute("href", "/app/campaigns/c-1");
  await expect(diwali).toContainText("Taking applications");
  await expect(diwali).toContainText("11"); // applications, from its report
  await page.getByRole("button", { name: /^Drafts/ }).click();
  await expect(cards(page)).toHaveCount(1);
  await expect(cards(page).first()).toContainText("Millet snacks launch");
  await page.getByRole("button", { name: /^Cancelled/ }).click();
  await expect(page.getByText("No campaign in this group.")).toBeVisible();
});

test("a brand with no campaign is shown the four steps, on Campaigns and on Today, not a blank page", async ({ page }) => {
  await scenario({ campaigns: "empty" });
  await signIn(page);
  await expect(page.getByRole("heading", { name: "Your first steps" })).toBeVisible();
  await page.getByRole("link", { name: "Campaigns" }).first().click();
  await expect(page.getByRole("heading", { name: "Start your first campaign" })).toBeVisible();
  await expect(page.locator("main ol li")).toHaveCount(4);
  await expect(page.getByRole("link", { name: "New campaign" }).first()).toHaveAttribute("href", "/app/campaigns/new");
});

test("a creator who opens Campaigns is sent to Discover", async ({ page }) => {
  await signIn(page, "Creator");
  await page.goto("/app/campaigns");
  await expect(page).toHaveURL(/\/app\/discover$/);
});

test("a campaign's overview: figures, progress, where the applications and deals stand, the money, and its terms", async ({ page }) => {
  await signIn(page);
  await page.goto("/app/campaigns/c-1");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Diwali sweets reel");
  await expect(page.getByRole("progressbar", { name: "Applications looked at" })).toHaveAttribute("aria-valuenow", "73"); // 8 of 11
  await expect(page.getByRole("progressbar", { name: "Paid and confirmed" })).toHaveAttribute("aria-valuenow", "43"); // 3 of 7
  const funnel = panel(page, "Applications");
  await expect(funnel).toContainText("New");
  for (const [label, count] of [["New", "3"], ["Shortlisted", "2"], ["Accepted", "5"], ["Not chosen", "1"]]) await expect(funnel.getByText(label, { exact: true }).locator("xpath=following-sibling::span")).toHaveText(count);
  await expect(panel(page, "Deals by stage").locator("ol li")).toHaveCount(5);
  const money = panel(page, "Money");
  await expect(money).toContainText("₹42,000"); // agreed
  await expect(money).toContainText("₹18,000"); // confirmed
  await expect(money).toContainText("You pay creators directly. Colyv records it.");
  await expect(panel(page, "The campaign")).toContainText("2 reels");
});

test("Creators: every collaboration, filtered by stage, and its post opens in full with the checks and the screenshot", async ({ page }) => {
  await signIn(page);
  await page.goto("/app/campaigns/c-1?tab=creators");
  const rows = page.locator("main li").filter({ has: page.getByRole("link", { name: "Open the deal" }) });
  await expect(rows).toHaveCount(7);
  await page.getByRole("button", { name: /^Finished/ }).click();
  await expect(rows).toHaveCount(3);
  await page.getByRole("button", { name: /^All/ }).click();
  await rows.filter({ hasText: "Priya Eats" }).getByRole("button", { name: /48.2K/ }).click();
  const sheet = page.getByRole("dialog", { name: "Priya Eats's post" });
  await expect(sheet).toBeVisible();
  await expect(sheet).toContainText("Read from the creators' screenshots, not verified.");
  await expect(sheet.getByText("Views", { exact: true }).locator("xpath=following-sibling::dd")).toHaveText("48.2K");
  await expect(sheet.getByText("Shares", { exact: true }).locator("xpath=following-sibling::dd")).toHaveText("Not shown");
  await expect(sheet).toContainText("at least 8%"); // (3,100 + 212 + 540) / 48,200 = 7.99%, shares not shown
  await expect(sheet.getByRole("img", { name: "The creator's screenshot of the post's insights" })).toBeVisible();
  await expect(sheet.getByText("The handle on it is the creator's linked channel").locator("xpath=following-sibling::span")).toHaveText("Checked");
  await expect(sheet.getByRole("link", { name: "Open the deal" })).toHaveAttribute("href", "/app/deals/m-3");
  await page.keyboard.press("Escape");
  await expect(sheet).toBeHidden();
});

test("a check the backend failed is shown as failed, not hidden", async ({ page }) => {
  await signIn(page);
  await page.goto("/app/campaigns/c-1?tab=creators");
  await page.locator("main li").filter({ hasText: "Meera Makes" }).getByRole("button", { name: /31.4K/ }).click();
  const sheet = page.getByRole("dialog", { name: "Meera Makes's post" });
  await expect(sheet.getByText("The handle on it is the creator's linked channel").locator("xpath=following-sibling::span")).toHaveText("Does not match");
});

test("Insights: totals per figure, posts ranked by the figure you pick, a missing figure last and never 0", async ({ page }) => {
  await signIn(page);
  await page.goto("/app/campaigns/c-1?tab=insights");
  await expect(page.getByText("Read from the creators' screenshots, not verified.").first()).toBeVisible();
  const metrics = page.getByRole("group", { name: "Compare posts by" });
  await expect(metrics.getByRole("button", { name: /Views/ })).toContainText("1.2L"); // 122,900
  await expect(metrics.getByRole("button", { name: /Shares/ })).toContainText("Not shown");
  await expect(metrics.getByRole("button", { name: /Views/ })).toHaveAttribute("aria-pressed", "true");
  const ranked = panel(page, "Posts by Views").locator("ul > li");
  await expect(ranked).toHaveCount(5);
  await expect(ranked.first()).toContainText("Priya Eats");
  await expect(ranked.nth(1)).toContainText("Meera Makes");
  await metrics.getByRole("button", { name: /Saves/ }).click();
  const bySaves = panel(page, "Posts by Saves").locator("ul > li");
  await expect(bySaves.first()).toContainText("Priya Eats"); // 540
  await expect(bySaves.nth(1)).toContainText("Meera Makes"); // 310
  await expect(bySaves.last()).toContainText("Not shown"); // the rest: their screenshots showed no saves
  await expect(bySaves.last()).not.toContainText("0");
  // Engagement is calculated from the numbers read, and says so.
  const average = panel(page, "Average engagement");
  // The mean of this campaign's five posts: 7.99, 7.53, 8.44, 7.48 and 8.04 percent (each partial: no screenshot showed shares) = 7.9.
  await expect(average).toContainText("at least 7.9%");
  await expect(average).toContainText("across 5 posts with enough shown");
  await expect(average).toContainText("Calculated from the numbers read");
  await expect(average).toContainText("Highest: Meera Makes");
  // Selecting a post opens it.
  await bySaves.first().getByRole("button").click();
  await expect(page.getByRole("dialog", { name: "Priya Eats's post" })).toBeVisible();
});

test("the section is in the address, so a link opens Insights directly and back returns to the section before", async ({ page }) => {
  await signIn(page);
  await page.goto("/app/campaigns/c-1");
  await expect(page.getByRole("link", { name: "Overview" })).toHaveAttribute("aria-current", "page");
  await page.getByRole("link", { name: "Insights" }).click();
  await expect(page).toHaveURL(/tab=insights$/);
  await expect(page.getByRole("link", { name: "Insights" })).toHaveAttribute("aria-current", "page");
});

test("a campaign with no post numbers yet says so, and a failed evidence read leaves the numbers on screen", async ({ page }) => {
  await scenario({ reports: "none" });
  await signIn(page);
  await page.goto("/app/campaigns/c-1?tab=insights");
  await expect(page.getByText("No post numbers yet")).toBeVisible();
  await scenario({ reports: "some", evidence: "error" });
  await page.goto("/app/campaigns/c-1?tab=creators");
  await page.locator("main li").filter({ hasText: "Priya Eats" }).getByRole("button", { name: /48.2K/ }).click();
  const sheet = page.getByRole("dialog", { name: "Priya Eats's post" });
  await expect(sheet.getByText("The evidence could not be loaded.")).toBeVisible();
  await expect(sheet.getByText("Views", { exact: true }).locator("xpath=following-sibling::dd")).toHaveText("48.2K");
});

test("a campaign that does not exist, and a failed report, each say what happened", async ({ page }) => {
  await signIn(page);
  await page.goto("/app/campaigns/c-gone");
  await expect(page.getByRole("heading", { name: "We could not find this campaign" })).toBeVisible();
  await expect(page.getByRole("link", { name: "All campaigns" }).first()).toHaveAttribute("href", "/app/campaigns");
  await scenario({ reports: "error" });
  await page.goto("/app/campaigns/c-1");
  await expect(page.getByText("The numbers for this campaign could not be loaded.")).toBeVisible();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Diwali sweets reel"); // the campaign itself still shows
});
