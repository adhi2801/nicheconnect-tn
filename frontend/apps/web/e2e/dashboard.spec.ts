import { expect, test, type Page } from "@playwright/test";

// The two Today dashboards (frontend/design/dashboard-plan.md, D-204), against the stand-in backend (e2e/mock-api.mjs).
const MOCK = "http://localhost:8098";
const scenario = (body: object) => fetch(`${MOCK}/__scenario`, { method: "POST", body: JSON.stringify(body) });

test.beforeEach(async () => { await fetch(`${MOCK}/__reset`, { method: "POST", body: "{}" }); });

async function signIn(page: Page, role: "Creator" | "Brand") {
  await page.goto("/sign-in");
  await page.locator("label", { hasText: new RegExp(`^${role}`) }).click();
  await page.getByLabel("Mobile number").fill("9876543210");
  await page.getByRole("button", { name: "Send code" }).click();
  await page.getByLabel("6-digit code").fill("123456");
  await expect(page).toHaveURL(/\/app$/);
}

const panel = (page: Page, title: string) => page.getByRole("region", { name: title, exact: true });

test("a creator's dashboard: what needs them, what is due, what is coming up, their applications and payments", async ({ page }) => {
  await signIn(page, "Creator");
  await expect(page.getByText("Confirmed so far")).toBeVisible();
  await expect(page.getByText("₹1,25,000").first()).toBeVisible();
  await expect(panel(page, "Needs you")).toBeVisible();
  await expect(panel(page, "Next due")).toContainText("Confirm you received the payment");
  // Coming up: deals whose work is still to come, nearest first, with whose move it is. The deal at payment is not in it.
  const coming = panel(page, "Coming up");
  const rows = coming.locator("ul a");
  await expect(rows).toHaveCount(4);
  await expect(rows.first()).toContainText("Madurai Masala Co.");
  await expect(rows.first()).toContainText("Due in 2 days");
  await expect(rows.first()).toContainText("Your move");
  await expect(coming).not.toContainText("Chennai Bakes"); // that deal is at the payment stage: its work date means nothing now
  await expect(panel(page, "Your applications").locator("ul a")).toHaveCount(4);
  await expect(panel(page, "Payments")).toContainText("Not yet marked as paid");
  // A brand's cards are not a creator's.
  await expect(page.getByText("Post performance")).toHaveCount(0);
  await expect(page.getByText("Your campaigns")).toHaveCount(0);
});

test("a brand's dashboard: progress, needs you, campaigns, each collaboration's status", async ({ page }) => {
  await signIn(page, "Brand");
  await expect(page.getByText("Creators applied")).toBeVisible();
  await expect(page.getByText("14", { exact: true })).toBeVisible(); // 8 + 2 + 4 applications across the three ongoing campaigns
  // Progress, worked out from every campaign's report: 10 of 14 looked at, 5 of 5 memos agreed, 3 of 5 approved, 2 of 5 paid.
  await expect(page.getByRole("progressbar", { name: "Applications looked at" })).toHaveAttribute("aria-valuenow", "71");
  await expect(page.getByRole("progressbar", { name: "Memos agreed" })).toHaveAttribute("aria-valuenow", "100");
  await expect(page.getByRole("progressbar", { name: "Work approved" })).toHaveAttribute("aria-valuenow", "60");
  await expect(page.getByRole("progressbar", { name: "Paid and confirmed" })).toHaveAttribute("aria-valuenow", "40");
  // Campaigns: the three ongoing ones, not the draft.
  const campaigns = panel(page, "Your campaigns");
  await expect(campaigns.locator("ul a")).toHaveCount(3);
  await expect(campaigns).toContainText("Diwali sweets reel");
  await expect(campaigns).toContainText("8 applied · 1 of 3 deals finished");
  await expect(campaigns).toContainText("Closed to applications");
  await expect(campaigns).not.toContainText("Millet snacks launch");
  await expect(campaigns.getByRole("link", { name: /Diwali sweets reel/ })).toHaveAttribute("href", "/app/campaigns/c-1");
  // Collaborations: the creator, the campaign, the stage and whose move it is.
  const collabs = panel(page, "Collaborations");
  await expect(collabs.locator("ul a").first()).toContainText("Your move");
  await expect(collabs).toContainText("Suresh Snaps");
  await expect(collabs).toContainText("Waiting on them");
  await expect(page.getByText("Your applications")).toHaveCount(0);
});

test("performance says it is read from screenshots, shows what they said, and never turns a missing number into zero", async ({ page }) => {
  await signIn(page, "Brand");
  const perf = panel(page, "Post performance");
  await expect(perf).toContainText("Read from the creators' screenshots, not verified.");
  await expect(perf).toContainText("3 posts, from 4 screenshots");
  await expect(perf.getByText("Views").locator("xpath=following-sibling::dd")).toHaveText("60.7K");
  await expect(perf.getByText("Saves").locator("xpath=following-sibling::dd")).toHaveText("540");
  // No screenshot showed shares: the total says so in words. It is not 0 (zero shares and "nobody said" mean opposite things).
  await expect(perf.getByText("Shares").locator("xpath=following-sibling::dd")).toHaveText("Not shown");
  await expect(perf).toContainText("48.2K views");
  await expect(perf).toContainText("7.4K reach"); // a post whose screenshot showed no views is headlined by its reach
  await expect(perf).toContainText("Some figures were shown rounded on the screenshot");
  await expect(perf).toContainText("Readings a creator marked as wrong are left out.");
});

test("before any screenshot is read, performance says so and shows no zeros", async ({ page }) => {
  await scenario({ reports: "none" });
  await signIn(page, "Brand");
  const perf = panel(page, "Post performance");
  await expect(perf).toContainText("No post numbers yet");
  await expect(perf).not.toContainText("0");
  await expect(perf.getByRole("definition")).toHaveCount(0);
});

test("a campaign whose report fails is counted, not left out silently, and the rest still shows", async ({ page }) => {
  await scenario({ reports: "error" });
  await signIn(page, "Brand");
  await expect(panel(page, "Your campaigns")).toContainText("3 campaigns could not be loaded.");
  await expect(panel(page, "Post performance")).toContainText("Post numbers could not be loaded.");
  await expect(panel(page, "Needs you")).toBeVisible();
  await expect(panel(page, "Collaborations")).toContainText("Suresh Snaps");
});

test("a brand with no campaign running is told so and offered the next step", async ({ page }) => {
  await scenario({ campaigns: "empty" });
  await signIn(page, "Brand");
  await expect(panel(page, "Your campaigns")).toContainText("No campaign is running.");
  await expect(panel(page, "Your campaigns").getByRole("link", { name: "New campaign" })).toHaveAttribute("href", "/app/campaigns/new");
  await expect(page.getByRole("progressbar")).toHaveCount(0);
  await expect(page.getByText("Not enough yet")).toHaveCount(4); // four steps with nothing to divide: words, never 0%
});

test("a failed deals call says so in its own cards and leaves the rest of Today working", async ({ page }) => {
  await scenario({ deals: "error" });
  await signIn(page, "Creator");
  await expect(panel(page, "Coming up")).toContainText("Deals could not be loaded.");
  await expect(panel(page, "Needs you")).toBeVisible();
});
