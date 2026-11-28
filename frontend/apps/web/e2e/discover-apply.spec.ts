import { expect, test, type Page } from "@playwright/test";

// C2 to C4: finding a campaign and applying, against the stand-in backend (e2e/mock-api.mjs).
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
const PITCH = "I make Madurai street-food reels every week for an audience of 18 to 30 year olds in the city.";

test.beforeEach(async () => { await fetch(`${MOCK}/__reset`, { method: "POST", body: "{}" }); });

async function signIn(page: Page, extra: object = {}) {
  await scenario(extra);
  await page.goto("/sign-in");
  await page.locator("label", { hasText: /^Creator/ }).click();
  await page.getByLabel("Mobile number").fill("9876543210");
  await page.getByRole("button", { name: "Send code" }).click();
  await page.getByLabel("6-digit code").fill("123456");
  await expect(page).toHaveURL(/\/app$/);
}

const cards = (page: Page) => page.locator("main ul li a[href^='/app/discover/']");

test("Discover shows pay, type, place and closing date on each card, and marks what was already applied to", async ({ page }) => {
  await signIn(page);
  await page.goto("/app/discover");
  await expect(cards(page)).toHaveCount(20);
  const first = cards(page).first();
  await expect(first).toContainText("Kovai Organics");
  await expect(first).toContainText("₹5,000 to ₹15,000");
  await expect(first).toContainText("Madurai, Chennai");
  await expect(first).toContainText("Open until the end of 15 Dec");
  await expect(cards(page).filter({ hasText: "Chennai Bakes" }).first()).toContainText("chennaibakes.in, verified since 1 Oct 2026");
  await expect(page.locator("a[href='/app/discover/c-8']")).toContainText("Invited");
  await expect(page.locator("a[href='/app/discover/c-8']")).not.toContainText("Applied");
  await expect(page.locator("a[href='/app/discover/c-2']")).toContainText("Applied");
  await expect(page.locator("a[href='/app/discover/c-1']")).not.toContainText("Applied");
});

test("Discover makes no call per card: one for campaigns, one for applications, whatever the page size", async ({ page }) => {
  await signIn(page);
  await quiet(); // Today's own reads finish first, so only Discover's are counted
  await fetch(`${MOCK}/__calls/reset`, { method: "POST", body: "{}" });
  await page.goto("/app/discover");
  await expect(cards(page)).toHaveCount(20);
  const { calls } = await state();
  // Every call made, not only the two expected: the screen's two, plus the frame's own (who is signed in, the unread count).
  expect(Object.keys(calls).sort()).toEqual(["/api/v1/applications/me", "/api/v1/campaigns/discover", "/api/v1/creators/me", "/api/v1/notifications/unread-count"]);
  expect(calls["/api/v1/campaigns/discover"]).toBe(1);
  expect(calls["/api/v1/applications/me"]).toBe(1);
  // The city suggestions are read only once the city field is used.
  await page.getByLabel("City").focus();
  await expect.poll(async () => (await state()).calls["/api/v1/cities"]).toBe(1);
});

test("more campaigns load by cursor, then the list says it has reached the end", async ({ page }) => {
  await signIn(page);
  await page.goto("/app/discover");
  await page.getByRole("button", { name: "Show more campaigns" }).click();
  await expect(cards(page)).toHaveCount(25);
  await expect(page.getByText("That's every open campaign that matches.")).toBeVisible();
  expect((await state()).lastQuery.cursor).toBe("page-2");
});

test("filters go into the address and to the API, and clearing them brings everything back", async ({ page }) => {
  await signIn(page);
  await page.goto("/app/discover");
  await page.getByLabel("Niche").selectOption("fashion");
  await page.getByLabel("Minimum pay (₹)").fill("5,000");
  await page.getByRole("button", { name: "Show campaigns" }).click();
  await expect(page).toHaveURL(/\/app\/discover\?niche=fashion&min=5000$/);
  await expect(page.getByText("2 filters on")).toBeVisible();
  expect((await state()).lastQuery).toMatchObject({ niche: "fashion", min_budget_paise: "500000" });
  await expect(cards(page)).toHaveCount(8);
  await page.getByRole("button", { name: "Clear filters" }).click();
  await expect(page).toHaveURL(/\/app\/discover$/);
  await expect(cards(page)).toHaveCount(20);
});

test("an address with filters we do not know shows everything rather than an error", async ({ page }) => {
  await signIn(page);
  await page.goto("/app/discover?niche=gaming&type=free");
  await expect(cards(page)).toHaveCount(20);
  expect((await state()).lastQuery.niche).toBeUndefined();
});

test("no open campaigns, and a failed load, each say what happened and what to do", async ({ page }) => {
  await signIn(page, { discover: "empty" });
  await page.goto("/app/discover");
  await expect(page.getByRole("heading", { name: "No open campaigns right now" })).toBeVisible();
  await scenario({ discover: "error" });
  await page.goto("/app/discover?niche=food");
  await expect(page.getByText("Campaigns didn't load")).toBeVisible();
  await expect(page.getByText("Reference 01MOCKREQUEST")).toBeVisible();
  await scenario({ discover: "empty" });
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(page.getByRole("heading", { name: "No open campaigns match" })).toBeVisible();
});

test("a campaign shows its terms, and the brand's record as facts with what they rest on", async ({ page }) => {
  await signIn(page);
  await page.goto("/app/discover/c-2");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Silk saree styling 2");
  await expect(page.getByText("2 × reel on Instagram")).toBeVisible();
  await expect(page.getByText("Marked 8 of 9 finished deals as paid, with 6 different creators")).toBeVisible();
  await expect(page.getByText("Paid by the due date in 88% of 9 finished deals")).toBeVisible();
  await expect(page.getByText("chennaibakes.in, verified since 1 Oct 2026")).toBeVisible();
  await expect(page.getByText("The domain registry says it was registered on 2 Mar 2019.")).toBeVisible();
  await expect(page.getByText(/registered recently/)).toHaveCount(0);
});

test("a website registered days ago is said plainly, beside the domain", async ({ page }) => {
  await signIn(page);
  await page.goto("/app/discover/c-newdomain");
  await expect(page.getByText(/This website was registered recently, on .*Take extra care before you agree to anything\./)).toBeVisible();
});

test("opened from Discover, the brand's record is asked for at once, not after the campaign", async ({ page }) => {
  await signIn(page, { campaignDelayMs: 2500 });
  await page.goto("/app/discover");
  await cards(page).first().waitFor();
  await page.locator("a[href='/app/discover/c-1']").click();
  // The campaign's own read takes 2.5 s here. The record shows well before that, because the card already named the brand; in a
  // chain it could not show until the campaign had arrived.
  await expect(page.getByText(/Fewer than 3 finished deals on Colyv/)).toBeVisible({ timeout: 1500 });
});

test("a new brand has no history yet, never a zero, and money it owes now still shows", async ({ page }) => {
  await signIn(page);
  await page.goto("/app/discover/c-1");
  await expect(page.getByText(/Fewer than 3 finished deals on Colyv/)).toBeVisible();
  await expect(page.getByText("1 payment to a creator is overdue right now")).toBeVisible();
  await expect(page.getByText(/0%/)).toHaveCount(0);
});

test("a warning sits beside the text it is about, and the text stays", async ({ page }) => {
  await signIn(page);
  await page.goto("/app/discover/c-flagged");
  await expect(page.getByText("Pay a ₹500 registration fee to apply.")).toBeVisible();
  await expect(page.getByText("This text asks for money. On Colyv you never pay to get a deal.")).toBeVisible();
});

test("a campaign already applied to shows the application, not the Apply button, even while the applications load", async ({ page }) => {
  await signIn(page, { applicationsDelayMs: 1500 });
  await page.goto("/app/discover/c-2");
  // The campaign is on screen while the applications are still on their way: Apply must not be offered in that moment.
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Silk saree styling 2");
  // Counted once, now: toHaveCount(0) would wait for the button to go, and pass even if it had been offered.
  expect(await page.getByRole("button", { name: "Apply" }).count()).toBe(0);
  await expect(page.getByRole("heading", { name: "Your application" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Apply" })).toHaveCount(0);
});

test("a closed, missing or withheld campaign says so, with a way back", async ({ page }) => {
  await signIn(page);
  await page.goto("/app/discover/c-closed");
  await expect(page.getByText("Applications for this campaign have closed.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Apply" })).toHaveCount(0);
  await page.goto("/app/discover/c-gone");
  await expect(page.getByRole("heading", { name: "This campaign isn't available" })).toBeVisible();
  await page.goto("/app/discover/c-withheld");
  await expect(page.getByRole("heading", { name: "This campaign is unavailable for legal reasons" })).toBeVisible();
  await page.getByRole("link", { name: "Browse campaigns" }).click();
  await expect(page).toHaveURL(/\/app\/discover$/);
});

test("applying: checked first, budget beside the quote, sent once with a key, then shown as sent", async ({ page }) => {
  await signIn(page);
  await page.goto("/app/discover/c-5");
  await page.getByRole("button", { name: "Apply" }).click();
  const sheet = page.getByRole("dialog");
  await expect(sheet.getByText("You never pay to get a deal.", { exact: false })).toBeVisible();
  await sheet.getByRole("button", { name: "Send application" }).click();
  await expect(sheet.getByText("Write at least 20 characters.")).toBeVisible();
  expect((await state()).writes).toHaveLength(0);
  await sheet.getByLabel("Why you're a good fit").fill(PITCH);
  await expect(sheet.getByText("Write at least 20 characters.")).toHaveCount(0);
  await sheet.getByLabel("Your quote (optional)").fill("20000");
  await expect(sheet.getByText(/above this campaign's maximum of ₹15,000/)).toBeVisible();
  await sheet.getByLabel("Your quote (optional)").fill("6,000");
  await expect(sheet.getByText(/above this campaign's maximum/)).toHaveCount(0);
  await sheet.getByRole("button", { name: "Send application" }).click();
  await expect(page.getByText("Application sent")).toBeVisible();
  await expect(page.getByRole("dialog")).toBeHidden();
  const { writes } = await state();
  expect(writes).toHaveLength(1);
  expect(writes[0].key).toMatch(/^[0-9a-f-]{36}$/);
  expect(writes[0].body).toEqual({ pitch: PITCH, quoted_amount_paise: 600_000 });
  await expect(page.getByText("Sent 26 Nov 2026")).toBeVisible(); // 19:30 UTC on the 25th is the 26th in India
});

test("a busy backend is retried with the same key, so one application is made", async ({ page }) => {
  await signIn(page, { apply: "busyOnce" });
  await page.goto("/app/discover/c-5");
  await page.getByRole("button", { name: "Apply" }).click();
  await page.getByLabel("Why you're a good fit").fill(PITCH);
  await page.getByRole("button", { name: "Send application" }).click();
  await expect(page.getByText("Application sent")).toBeVisible({ timeout: 10_000 });
  const { writes } = await state();
  expect(writes).toHaveLength(2);
  expect(writes[1].key).toBe(writes[0].key);
});

test("a refusal says why in plain words, and the pitch is kept, even across a reload", async ({ page }) => {
  await signIn(page, { apply: "closed" });
  await page.goto("/app/discover/c-5");
  await page.getByRole("button", { name: "Apply" }).click();
  await page.getByLabel("Why you're a good fit").fill(PITCH);
  await page.getByRole("button", { name: "Send application" }).click();
  await expect(page.getByText("Applications for this campaign have closed.")).toBeVisible();
  await expect(page.getByText("Your words are kept. Try again when you're ready.")).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: "Apply" }).click();
  await expect(page.getByLabel("Why you're a good fit")).toHaveValue(PITCH);
});

test("too many tries shows the wait, never retried by itself", async ({ page }) => {
  await signIn(page, { apply: "rate" });
  await page.goto("/app/discover/c-5");
  await page.getByRole("button", { name: "Apply" }).click();
  await page.getByLabel("Why you're a good fit").fill(PITCH);
  await page.getByRole("button", { name: "Send application" }).click();
  await expect(page.getByText("Too many tries in a short time. Try again in 40 seconds.")).toBeVisible();
  expect((await state()).writes).toHaveLength(1);
});

test("an old refusal is not shown as current when the sheet is opened again", async ({ page }) => {
  await signIn(page, { apply: "rate" });
  await page.goto("/app/discover/c-5");
  await page.getByRole("button", { name: "Apply" }).click();
  await page.getByLabel("Why you're a good fit").fill(PITCH);
  await page.getByRole("button", { name: "Send application" }).click();
  await expect(page.getByText("Try again in 40 seconds.", { exact: false })).toBeVisible();
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Apply" }).click();
  await expect(page.getByLabel("Why you're a good fit")).toHaveValue(PITCH); // the words stay
  await expect(page.getByText("Try again in 40 seconds.", { exact: false })).toHaveCount(0); // the old wait does not
});

test("a pitch the backend flags shows its warning to the author once sent", async ({ page }) => {
  await signIn(page);
  await page.goto("/app/discover/c-5");
  await page.getByRole("button", { name: "Apply" }).click();
  await page.getByLabel("Why you're a good fit").fill("Send a deposit first and I will make the reel for you.");
  await page.getByRole("button", { name: "Send application" }).click();
  await expect(page.getByText("This text asks for money. On Colyv you never pay to get a deal.")).toBeVisible();
});

test("a sheet the browser closes by itself can always be opened again", async ({ page }) => {
  await signIn(page);
  await page.goto("/app/discover/c-5");
  await page.getByRole("button", { name: "Apply" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  // As Android's Back or a second Escape does under the close-watcher rules: the dialog closes without our code asking.
  await page.evaluate(() => document.querySelector<HTMLDialogElement>("dialog[open]")?.close());
  await expect(page.getByRole("dialog")).toBeHidden();
  await page.getByRole("button", { name: "Apply" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
});

test("a draft goes when the session ends by itself, not only on Sign out", async ({ page, context }) => {
  await signIn(page);
  await page.goto("/app/discover/c-5");
  await page.getByRole("button", { name: "Apply" }).click();
  await page.getByLabel("Why you're a good fit").fill("A pitch the next person on this computer must never see.");
  const drafts = () => page.evaluate(() => Object.keys(localStorage).filter((k) => k.startsWith("colyv-draft:")));
  expect(await drafts()).toHaveLength(1);
  // The login ends without Sign out (it expired, or "sign out everywhere" from a phone): the refresh is refused.
  await context.clearCookies();
  await page.reload();
  await expect(page).toHaveURL(/\/sign-in$/);
  expect(await drafts()).toEqual([]);
});

test("a draft survives a reload when the server cannot be reached, because the session has not ended", async ({ page }) => {
  await signIn(page);
  await page.goto("/app/discover/c-5");
  await page.getByRole("button", { name: "Apply" }).click();
  await page.getByLabel("Why you're a good fit").fill("A pitch written on patchy 4G.");
  // The session cannot be renewed (the backend busy or out of reach) while the page reloads.
  await fetch(`${MOCK}/__scenario`, { method: "POST", body: JSON.stringify({ refreshBusy: true }) });
  await page.reload();
  await expect(page).toHaveURL(/\/sign-in$/);
  // Back in reach: the same login restores, and the words are still there.
  await fetch(`${MOCK}/__scenario`, { method: "POST", body: JSON.stringify({ refreshBusy: false }) });
  await page.goto("/app/discover/c-5");
  await page.getByRole("button", { name: "Apply" }).click();
  await expect(page.getByLabel("Why you're a good fit")).toHaveValue("A pitch written on patchy 4G.");
});

test("numbers in other people's text are never turned into phone links by the browser", async ({ page }) => {
  await signIn(page);
  await expect(page.locator('meta[name="format-detection"]')).toHaveAttribute("content", /telephone=no/);
});

test("Escape closes the sheet, and the draft is still there when it opens again", async ({ page }) => {
  await signIn(page);
  await page.goto("/app/discover/c-5");
  await page.getByRole("button", { name: "Apply" }).click();
  await page.getByLabel("Why you're a good fit").fill("Half-written pitch");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toBeHidden();
  await page.getByRole("button", { name: "Apply" }).click();
  await expect(page.getByLabel("Why you're a good fit")).toHaveValue("Half-written pitch");
});
