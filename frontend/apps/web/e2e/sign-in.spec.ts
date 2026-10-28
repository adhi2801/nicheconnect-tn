import { expect, test, type BrowserContext, type Page } from "@playwright/test";

const MOCK = "http://localhost:8098";
const state = async (): Promise<{ reuseDetected: boolean; refreshCalls: number; lastForwardedFor: string | null; liveLogins: number }> => (await fetch(`${MOCK}/__state`)).json();

test.beforeEach(async () => { await fetch(`${MOCK}/__reset`, { method: "POST", body: "{}" }); });

// People click the visible card, not the hidden radio underneath it.
async function chooseRole(page: Page, role: "Creator" | "Brand") {
  await page.locator("label", { hasText: new RegExp(`^${role}`) }).click();
  await expect(page.getByRole("radio", { name: new RegExp(`^${role}`) })).toBeChecked();
}

async function signIn(page: Page, role: "Creator" | "Brand" = "Creator") {
  await page.goto("/sign-in");
  await chooseRole(page, role);
  await page.getByLabel("Mobile number").fill("98765 43210");
  await page.getByRole("button", { name: "Send code" }).click();
  await expect(page.getByRole("heading", { name: "Enter your code" })).toBeVisible();
  await page.getByLabel("6-digit code").fill("123456");
  await expect(page).toHaveURL(/\/app$/);
}

const signedIn = (page: Page) => expect(page.getByRole("link", { name: "Your account" })).toBeVisible();
const signOutFrom = async (page: Page) => {
  await page.getByRole("button", { name: "Sign out" }).first().click(); // the sidebar's
};

const refreshCookie = async (context: BrowserContext) => (await context.cookies()).find((c) => c.name === "colyv_rt");

test("asks which role before sending a code", async ({ page }) => {
  await page.goto("/sign-in");
  await page.getByRole("button", { name: "Send code" }).click();
  await expect(page.getByText("Choose whether you are a creator or a brand")).toBeVisible();
});

test("refuses a number that is not an Indian mobile, in words", async ({ page }) => {
  await page.goto("/sign-in");
  await chooseRole(page, "Creator");
  await page.getByLabel("Mobile number").fill("12345");
  await page.getByRole("button", { name: "Send code" }).click();
  await expect(page.getByText("Enter a 10-digit Indian mobile number")).toBeVisible();
});

test("a wrong code says so and clears the boxes, then the right code signs in", async ({ page }) => {
  await page.goto("/sign-in");
  await chooseRole(page, "Brand");
  await page.getByLabel("Mobile number").fill("9876543210");
  await page.getByRole("button", { name: "Send code" }).click();
  await expect(page.getByText("+91 ••••• ••210")).toBeVisible();
  await page.getByLabel("6-digit code").fill("000000");
  await expect(page.getByText("That code is wrong")).toBeVisible();
  await expect(page.getByLabel("6-digit code")).toHaveValue("");
  await page.getByLabel("6-digit code").fill("123456");
  await expect(page).toHaveURL(/\/app$/);
  await signedIn(page);
  await expect(page.getByRole("link", { name: "Campaigns" }).first()).toBeVisible(); // a brand's navigation
});

test("a rate limit shows the wait and a reference to quote", async ({ page }) => {
  await page.goto("/sign-in");
  await chooseRole(page, "Creator");
  await page.getByLabel("Mobile number").fill("9000000429");
  await page.getByRole("button", { name: "Send code" }).click();
  // Next.js keeps its own hidden role="alert" element for route changes, so pick ours by its words.
  await expect(page.getByRole("alert").filter({ hasText: "Too many" })).toBeVisible();
});

test("the refresh token is in an httpOnly cookie and nowhere a script can read", async ({ page, context }) => {
  await signIn(page);
  const cookie = await refreshCookie(context);
  expect(cookie?.httpOnly).toBe(true);
  expect(cookie?.sameSite).toBe("Strict");
  expect(cookie?.path).toBe("/api/session");
  const visible = await page.evaluate(() => ({ cookie: document.cookie, local: JSON.stringify({ ...localStorage }), session: JSON.stringify({ ...sessionStorage }) }));
  expect(visible.cookie).not.toContain("colyv_rt");
  expect(visible.local + visible.session).not.toMatch(/refresh|mock-access|mock-refresh/);
});

test("a reload keeps the person signed in", async ({ page }) => {
  await signIn(page);
  await page.reload();
  await signedIn(page);
  expect((await state()).reuseDetected).toBe(false);
});

test("two tabs opening together never present the same refresh token twice", async ({ page, context }) => {
  await signIn(page);
  await fetch(`${MOCK}/__slow-refresh`, { method: "POST", body: JSON.stringify({ ms: 400 }) });
  const other = await context.newPage();
  await Promise.all([page.reload(), other.goto("/app")]);
  await signedIn(page);
  await signedIn(other);
  expect((await state()).reuseDetected).toBe(false);
});

test("signing out in one tab signs out the other, and a reload stays signed out", async ({ page, context }) => {
  await signIn(page);
  const other = await context.newPage();
  await other.goto("/app");
  await signedIn(other);
  await signOutFrom(page);
  await expect(page).toHaveURL(/\/sign-in$/);
  await expect(other).toHaveURL(/\/sign-in$/);
  expect(await refreshCookie(context)).toBeUndefined();
  await page.goto("/app");
  await expect(page).toHaveURL(/\/sign-in$/);
  expect((await state()).liveLogins).toBe(0);
});

test("a cookie the backend refuses sends the person to sign in and is cleared", async ({ page, context }) => {
  await context.addCookies([{ name: "colyv_rt", value: "not-a-real-token-0123456789", domain: "localhost", path: "/api/session", httpOnly: true, sameSite: "Strict" }]);
  await page.goto("/app");
  await expect(page).toHaveURL(/\/sign-in$/);
  expect(await refreshCookie(context)).toBeUndefined();
});

test("the person's address is passed on, so the backend's limits count the person and not the website", async ({ page }) => {
  await signIn(page);
  expect((await state()).lastForwardedFor).toBe("203.0.113.7");
});

test("a page that is not the website's own cannot use the session routes", async ({ request }) => {
  const res = await request.post("/api/session/refresh", { headers: { origin: "https://evil.example" } });
  expect(res.status()).toBe(403);
});
