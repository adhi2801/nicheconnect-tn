import { expect, test, type Page } from "@playwright/test";

// Report and block, one tap from anything a brand sent (trust-and-safety.md section 5), against the stand-in backend.
const MOCK = "http://localhost:8098";
const state = async () => (await fetch(`${MOCK}/__state`)).json();

test.beforeEach(async () => { await fetch(`${MOCK}/__reset`, { method: "POST", body: "{}" }); });

async function signIn(page: Page) {
  await page.goto("/sign-in");
  await page.locator("label", { hasText: /^Creator/ }).click();
  await page.getByLabel("Mobile number").fill("9876543210");
  await page.getByRole("button", { name: "Send code" }).click();
  await page.getByLabel("6-digit code").fill("123456");
  await expect(page).toHaveURL(/\/app$/);
}

test("a campaign is reported in one tap and a reason, sent once with a key, and the person is told how soon it is looked at", async ({ page }) => {
  await signIn(page);
  await page.goto("/app/discover/c-flagged");
  await page.getByRole("button", { name: "Report or block" }).click();
  const sheet = page.getByRole("dialog");
  await sheet.getByRole("button", { name: "Send report" }).click();
  await expect(sheet.getByText("Choose what is wrong.")).toBeVisible();
  expect((await state()).writes).toHaveLength(0);
  await sheet.getByLabel(/Spam or a scam/).check();
  await sheet.getByRole("button", { name: "Send report" }).click();
  await expect(sheet.getByText("Report sent. Thank you.")).toBeVisible();
  await expect(sheet.getByText("We aim to look at it within 36 hours.", { exact: false })).toBeVisible();
  const { writes } = await state();
  expect(writes).toHaveLength(1);
  expect(writes[0].key).toMatch(/^[0-9a-f-]{36}$/);
  expect(writes[0].body).toEqual({ subject_kind: "campaign", subject_id: "c-flagged", category: "spam", note: null });
});

test("reporting the same thing again says the first report is still open", async ({ page }) => {
  await signIn(page);
  for (const round of [1, 2]) {
    await page.goto("/app/discover/c-flagged");
    await page.getByRole("button", { name: "Report or block" }).click();
    await page.getByRole("dialog").getByLabel(/Pretending to be me/).check();
    await page.getByRole("dialog").getByRole("button", { name: "Send report" }).click();
    await expect(page.getByRole("dialog").getByText(round === 1 ? "Report sent. Thank you." : "You've already reported this, and that report is still open.")).toBeVisible();
    await expect(page.getByRole("dialog").getByText("We aim to look at it within 2 hours.", { exact: false })).toBeVisible();
  }
});

test("blocking asks once more, then the brand's campaigns are gone and the person is told the brand was not", async ({ page }) => {
  await signIn(page);
  await page.goto("/app/discover/c-1");
  await page.getByRole("button", { name: "Report or block" }).click();
  const sheet = page.getByRole("dialog");
  await expect(sheet.getByText("They won't be told.", { exact: false })).toBeVisible();
  await sheet.getByRole("button", { name: "Block Kovai Organics" }).click();
  expect((await state()).writes).toHaveLength(0);
  await sheet.getByRole("button", { name: "Yes, block Kovai Organics" }).click();
  await expect(page.getByText("Blocked. You won't see that brand's campaigns", { exact: false })).toBeVisible();
  await expect(page.getByText("Deals already agreed carry on. They were not told.", { exact: false })).toBeVisible();
  await expect(page).toHaveURL(/\/app\/discover$/); // the notice is shown once; a reload does not bring it back
  await expect(page.locator("main ul li a[href^='/app/discover/']").first()).toBeVisible();
  await expect(page.getByText("Kovai Organics")).toHaveCount(0);
  const { writes } = await state();
  expect(writes.map((w: { what: string; body: unknown }) => [w.what, w.body])).toEqual([["block", { brand_id: "b-new" }]]);
});

test("a brand's note on My applications is one tap from reporting that brand", async ({ page }) => {
  await signIn(page);
  await page.goto("/app/applications");
  const rejected = page.locator("article", { hasText: "Not chosen" });
  await expect(rejected).toBeVisible();
  await rejected.getByRole("button", { name: "Report or block" }).click();
  await page.getByRole("dialog").getByLabel(/Abuse or harassment/).check();
  await page.getByRole("dialog").getByLabel("Anything to add (optional)").fill("Asked me to call a private number.");
  await page.getByRole("dialog").getByRole("button", { name: "Send report" }).click();
  await expect(page.getByRole("dialog").getByText("Report sent. Thank you.")).toBeVisible();
  expect((await state()).writes[0].body).toEqual({ subject_kind: "brand", subject_id: "b-good", category: "abuse", note: "Asked me to call a private number." });
});

test("blocking from My applications reads again only that brand's campaigns, not every row", async ({ page }) => {
  await signIn(page);
  await page.goto("/app/applications");
  await expect(page.locator("article").first()).toBeVisible();
  await expect(page.getByText("Filter coffee tasting 1")).toBeVisible(); // the one from Kovai Organics, another brand
  const before = (await state()).calls;
  await page.locator("article", { hasText: "Not chosen" }).getByRole("button", { name: "Report or block" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Block Chennai Bakes" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Yes, block Chennai Bakes" }).click();
  await expect(page.getByText("Blocked.", { exact: false })).toBeVisible();
  await expect.poll(async () => (await state()).calls["/api/v1/campaigns/c-6"]).toBe(before["/api/v1/campaigns/c-6"] + 1);
  expect((await state()).calls["/api/v1/campaigns/c-1"]).toBe(before["/api/v1/campaigns/c-1"]); // Kovai's: not read again
});
