import { expect, test, type Page } from "@playwright/test";

const MOCK = "http://localhost:8098";
const scenario = (body: object) => fetch(`${MOCK}/__scenario`, { method: "POST", body: JSON.stringify(body) });

test.beforeEach(async () => { await fetch(`${MOCK}/__reset`, { method: "POST", body: "{}" }); });

async function signInToDeals(page: Page, role: "Creator" | "Brand" = "Creator") {
  await page.goto("/sign-in");
  await page.locator("label", { hasText: new RegExp(`^${role}`) }).click();
  await page.getByLabel("Mobile number").fill("9876543210");
  await page.getByRole("button", { name: "Send code" }).click();
  await page.getByLabel("6-digit code").fill("123456");
  await expect(page).toHaveURL(/\/app$/);
  await page.getByRole("link", { name: "Deals" }).first().click();
  await expect(page.getByRole("heading", { level: 1, name: "Deals" })).toBeVisible();
}

const cards = (page: Page) => page.getByRole("link", { name: /^Open this deal/ });
const column = (page: Page, name: RegExp | string) => page.getByRole("region", { name });

test("a creator sees the journey in five stages, with each deal where it is, and no Draft", async ({ page }) => {
  await signInToDeals(page);
  await expect(column(page, "Memo sent, 1 deal")).toBeVisible();
  await expect(column(page, "Agreed, 1 deal")).toBeVisible();
  await expect(column(page, "In progress, 2 deals")).toBeVisible();
  await expect(column(page, "Payment, 2 deals")).toBeVisible();
  await expect(column(page, "Finished, 1 deal")).toBeVisible();
  await expect(column(page, /^Draft/)).toHaveCount(0);
  await expect(page.getByText("7 deals · 4 need you")).toBeVisible();
  await expect(cards(page)).toHaveCount(7);
});

test("where it is the person's move the card says so, and otherwise whose it is", async ({ page }) => {
  await signInToDeals(page);
  const inProgress = column(page, "In progress, 2 deals");
  await expect(inProgress.getByRole("link", { name: /Spice box unboxing/ })).toContainText("Your move");
  await expect(inProgress.getByRole("link", { name: /Filter coffee tasting/ })).toContainText("Waiting on the brand");
  await expect(inProgress.getByRole("link", { name: /Spice box unboxing/ })).toContainText("Madurai Masala Co.");
  await expect(inProgress.getByRole("link", { name: /Spice box unboxing/ })).toContainText("₹6,500");
  await expect(inProgress.getByRole("link", { name: /Spice box unboxing/ })).toContainText("Due 25 Oct");
  // the person's own moves come first in a column
  await expect(inProgress.getByRole("link").first()).toContainText("Spice box unboxing");
});

test("a card opens its deal, and a dispute shows on the card", async ({ page }) => {
  await signInToDeals(page);
  await expect(column(page, "In progress, 2 deals").getByRole("link", { name: /Spice box unboxing/ })).toHaveAttribute("href", "/app/deals/m-2");
  await expect(column(page, "Payment, 2 deals").getByRole("link", { name: /Combo meal reels/ })).toContainText("Dispute open");
});

test("the filter keeps what needs the person, or what waits on others, and shows everything again", async ({ page }) => {
  await signInToDeals(page);
  await page.getByRole("button", { name: "Needs you" }).click();
  await expect(cards(page)).toHaveCount(4);
  await expect(page.getByRole("button", { name: "Needs you" })).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "Waiting on others" }).click();
  await expect(cards(page)).toHaveCount(2); // the finished deal is waiting on no one
  await page.getByRole("button", { name: "All" }).click();
  await expect(cards(page)).toHaveCount(7);
});

test("deals that ended without being done are counted apart, not drawn as stages", async ({ page }) => {
  await signInToDeals(page);
  await expect(page.locator("p", { hasText: "Closed deals:" })).toContainText("1 declined, 1 cancelled");
});

test("a brand also sees its drafts, with the creator's name on each card", async ({ page }) => {
  await signInToDeals(page, "Brand");
  await expect(column(page, "Draft, 1 deal")).toBeVisible();
  await expect(column(page, "Draft, 1 deal").getByRole("link")).toContainText("Anand Cuts");
  await expect(page.getByText("8 deals · 3 need you")).toBeVisible();
  await expect(column(page, "In progress, 2 deals").getByRole("link", { name: /Filter coffee tasting/ })).toContainText("Your move");
});

test("payments sit under the board with who, how much and where each stands, in words", async ({ page }) => {
  await signInToDeals(page);
  const table = page.getByRole("table");
  await expect(table.getByRole("columnheader", { name: "Brand" })).toBeVisible();
  await expect(table).toContainText("Chennai Bakes");
  await expect(table).toContainText("₹7,000");
  await expect(table).toContainText("Marked paid");
  await expect(table).toContainText("3 days late");
  await expect(table).toContainText("Confirmed received");
  await expect(table).toContainText("Due 5 Nov");
});

test("a brand's payments name the creator", async ({ page }) => {
  await signInToDeals(page, "Brand");
  const table = page.getByRole("table");
  await expect(table.getByRole("columnheader", { name: "Creator" })).toBeVisible();
  await expect(table).toContainText("Suresh Snaps");
});

test("until the API sends names, a card says so plainly, and a payment fills the gap where there is one", async ({ page }) => {
  await scenario({ names: false });
  await signInToDeals(page);
  // m-4 has no payment, so nothing names it
  const memoSent = column(page, "Memo sent, 1 deal").getByRole("link");
  await expect(memoSent).toContainText("Awaiting details");
  await expect(memoSent).toContainText("Deal memo");
  await expect(memoSent).toContainText("₹5,000");
  // m-1 has a payment, which knows the brand and the campaign
  const payment = column(page, "Payment, 2 deals").getByRole("link", { name: /Diwali sweets reel/ });
  await expect(payment).toContainText("Chennai Bakes");
});

test("with no deals the page says how one starts, and points forward", async ({ page }) => {
  await scenario({ deals: "empty" });
  await signInToDeals(page);
  await expect(page.getByRole("heading", { name: "No deals yet" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Browse campaigns" }).first()).toHaveAttribute("href", "/app/discover");
  await expect(page.getByRole("region")).toHaveCount(0);
});

test("a failed load says what happened and the retry brings the board back", async ({ page }) => {
  await scenario({ deals: "error" });
  await signInToDeals(page);
  await expect(page.getByRole("alert").filter({ hasText: "We could not load your deals" })).toBeVisible();
  await scenario({ deals: "full" });
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(column(page, "In progress, 2 deals")).toBeVisible();
});

test("on a phone the stages swipe sideways inside the board, and the page itself never does", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await signInToDeals(page);
  await expect(column(page, "Memo sent, 1 deal")).toBeVisible();
  const pageOverflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(pageOverflow).toBeLessThanOrEqual(0);
  const boardScrolls = await page.evaluate(() => { const el = document.querySelector("main .snap-x") as HTMLElement; return el.scrollWidth > el.clientWidth; });
  expect(boardScrolls).toBe(true);
});

test("when the stages do not all fit, buttons bring the later ones into view", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" }); // the scroll then jumps, so the test does not wait on an animation
  await page.setViewportSize({ width: 1280, height: 900 });
  await signInToDeals(page);
  const finished = column(page, "Finished, 1 deal");
  const next = page.getByRole("button", { name: "Later stages" });
  const previous = page.getByRole("button", { name: "Earlier stages" });
  await expect(next).toBeEnabled();
  await expect(previous).toBeDisabled();
  await expect(finished).not.toBeInViewport({ ratio: 0.5 });
  for (let i = 0; i < 6 && (await next.isEnabled()); i++) { await next.click(); await page.waitForTimeout(150); }
  await expect(next).toBeDisabled();
  await expect(previous).toBeEnabled();
  await expect(finished).toBeInViewport({ ratio: 0.9 });
});
