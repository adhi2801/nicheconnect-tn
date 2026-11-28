import { expect, test, type Page } from "@playwright/test";

// C5: my applications, against the stand-in backend (e2e/mock-api.mjs).
const MOCK = "http://localhost:8098";
const scenario = (body: object) => fetch(`${MOCK}/__scenario`, { method: "POST", body: JSON.stringify(body) });
const state = async () => (await fetch(`${MOCK}/__state`)).json();

// Waits until the stand-in has stopped hearing from the page: Today's own reads are done, so a count that follows is Discover's alone.
// (Not "network idle": this app never reaches it, e2e/accessibility.spec.ts.)
async function quiet() {
  let last = "";
  for (let i = 0; i < 40; i++) {
    await new Promise((done) => setTimeout(done, 400));
    const now = JSON.stringify((await state()).calls);
    if (now === last) return;
    last = now;
  }
}

test.beforeEach(async () => { await fetch(`${MOCK}/__reset`, { method: "POST", body: "{}" }); });

async function open(page: Page, extra: object = {}) {
  await scenario(extra);
  await page.goto("/sign-in");
  await page.locator("label", { hasText: /^Creator/ }).click();
  await page.getByLabel("Mobile number").fill("9876543210");
  await page.getByRole("button", { name: "Send code" }).click();
  await page.getByLabel("6-digit code").fill("123456");
  await expect(page).toHaveURL(/\/app$/);
  // Today reads some campaigns of its own; let it finish, then count only what My applications reads.
  await quiet();
  await fetch(`${MOCK}/__calls/reset`, { method: "POST", body: "{}" });
  await page.goto("/app/applications");
  await expect(page.getByRole("heading", { name: "My applications" })).toBeVisible();
  // The heading shows with the loading state; a test that counts rows must first wait for them to be there.
  if (!("applications" in extra)) await expect(page.locator("article").first()).toBeVisible();
}

test("applications are grouped, dated in India's calendar, with the campaign's name", async ({ page }) => {
  await open(page);
  await expect(page.getByRole("heading", { name: "In progress (2)" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Closed (3)" })).toBeVisible();
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
  // The backend answers 404 to a creator for any campaign that is no longer open (closed, cancelled or taken down).
  await expect(page.locator("article").filter({ hasText: "This campaign isn't open any more" })).toHaveCount(1);
  await expect(page.locator("article").filter({ hasText: "This campaign isn't open any more" })).toContainText("Withdrawn");
});

test("each campaign is read once, however many applications it has (the R7 stopgap stays bounded)", async ({ page }) => {
  await page.clock.install(); // the page's clock, so the reads can be made old without waiting
  await open(page);
  await expect(page.locator("article")).toHaveCount(6);
  await expect(page.getByText("Filter coffee tasting 6")).toBeVisible();
  const { calls } = await state();
  for (const id of ["c-1", "c-2", "c-4", "c-6", "c-8", "c-gone"]) expect(calls[`/api/v1/campaigns/${id}`]).toBe(1);
  // Not read again when the tab regains focus (the read's limit is 60 a minute an account), even once the reads are old: 11 minutes
  // on, past their 10-minute freshness, a focus would re-read them all if focus re-reads were on.
  await page.clock.fastForward("11:00");
  // As a real browser does on returning to the tab: visibilitychange at the document, bubbling to window, where the query library listens.
  await page.evaluate(() => document.dispatchEvent(new Event("visibilitychange", { bubbles: true })));
  await page.waitForTimeout(500);
  expect((await state()).calls["/api/v1/campaigns/c-2"]).toBe(1);
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
  await expect(page.getByRole("heading", { name: "Closed (4)" })).toBeVisible();
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
  await expect(page.locator("article", { hasText: "Not chosen" })).toBeVisible();
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

test("an invitation is its own group, with the brand's note as text", async ({ page }) => {
  await open(page);
  await expect(page.getByRole("heading", { name: "Invitations (1)" })).toBeVisible();
  await expect(page.locator("article", { hasText: "Invited" })).toContainText("Loved your Madurai reels. Join our launch?");
});

test("a creator with no profile yet gets the way to make one, not an error", async ({ page }) => {
  await open(page, { applications: "noProfile" });
  await expect(page.getByRole("heading", { name: "Set up your profile first" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Set up my profile" })).toHaveAttribute("href", "/app/onboarding");
  await expect(page.getByText("Something went wrong")).toHaveCount(0);
});

test("Discover stays marked in the navigation on My applications", async ({ page }) => {
  await open(page);
  await expect(page.getByRole("navigation", { name: "Main" }).first().getByRole("link", { name: "Discover" })).toHaveAttribute("aria-current", "page");
});
