import { readdirSync } from "node:fs";
import { join, relative, sep } from "node:path";
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

// frontend.md sections 6 and 12 (D-171, D-198): every page (each page.tsx under
// src/app, found by walking the folder, so a new page is checked without being listed) passes the automated
// WCAG 2.2 AA checks in light and dark, with motion on and off, at a phone's
// width and a laptop's, and body text meets 7:1 (AAA's enhanced contrast rule
// checks exactly our bar: 7:1 for body text, 4.5:1 for large text).
// Tools find only part of what people hit (axe: 57% of issues in Deque's own
// audits), so this is the floor; the manual TalkBack and VoiceOver pass and the
// outside audit (D-188) stay release steps.

const MOCK = "http://localhost:8098";
const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];
const RULES_ABOVE_AA = ["color-contrast-enhanced"];

// A dynamic segment is visited at a sample value. One not listed here fails the run below, so a new
// dynamic page is never skipped unseen.
const SAMPLE_SEGMENTS: Record<string, string> = {
  "[...slug]": "deals/1", // the screens not built yet answer at /app/<anything> (app/app/[...slug])
  "[id]": "c-flagged", // a campaign (app/app/discover/[id]); the one with a warning beside its text, so the warning is checked too
};

const APP_DIR = join(__dirname, "..", "src", "app");

function pageFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return pageFiles(path);
    return entry.name === "page.tsx" ? [path] : [];
  });
}

function routeOf(file: string): string {
  const segments = relative(APP_DIR, file).split(sep).slice(0, -1)
    .filter((segment) => !(segment.startsWith("(") && segment.endsWith(")"))) // route groups add no segment
    .map((segment) => {
      if (!segment.startsWith("[")) return segment;
      const sample = SAMPLE_SEGMENTS[segment];
      if (sample === undefined) throw new Error(`${relative(APP_DIR, file)}: give ${segment} a sample value in SAMPLE_SEGMENTS`);
      return sample;
    });
  return `/${segments.join("/")}`;
}

const PAGE_FILES = pageFiles(APP_DIR);
const ROUTES = PAGE_FILES.map(routeOf).sort();
const isSignedIn = (route: string) => route === "/app" || route.startsWith("/app/");
const PUBLIC_PAGES = ROUTES.filter((route) => !isSignedIn(route));
const SIGNED_IN_PAGES = ROUTES.filter(isSignedIn);

const VIEWS = [
  { name: "phone", width: 360, height: 780 },
  { name: "laptop", width: 1280, height: 800 },
] as const;
const SCHEMES = ["light", "dark"] as const;
const MOTION = ["no-preference", "reduce"] as const;

test.beforeEach(async () => { await fetch(`${MOCK}/__reset`, { method: "POST", body: "{}" }); });

async function signIn(page: Page, role: "Creator" | "Brand") {
  await page.goto("/sign-in");
  await page.locator("label", { hasText: new RegExp(`^${role}`) }).click();
  await page.getByLabel("Mobile number").fill("9876543210");
  await page.getByRole("button", { name: "Send code" }).click();
  await page.getByLabel("6-digit code").fill("123456");
  await expect(page).toHaveURL(/\/app$/);
}

// Ready means loaded and showing its main heading. Not "network idle": the sign-in page never
// reached it within the 30 s test limit (all eight views, 18 November 2026).
async function settled(page: Page) {
  await page.waitForLoadState("load");
  await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible();
  // Judged at rest: an element still fading in has a lower contrast than the one people read.
  // Endless animations (a loading shimmer) are left out; they never finish.
  await page.waitForFunction(() => document.getAnimations().every((a) => a.playState !== "running" || a.effect?.getComputedTiming().iterations === Infinity));
}

async function violations(page: Page) {
  const scheme = await page.evaluate(() => document.documentElement.dataset.theme);
  const ink = await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue("--c-ink").trim().toLowerCase());
  expect(ink, `the ${scheme} theme is what renders`).toBe(scheme === "dark" ? "#f4f0e7" : "#201712");
  const result = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  const above = await new AxeBuilder({ page }).withRules(RULES_ABOVE_AA).analyze();
  return [...result.violations, ...above.violations].map((v) => ({
    rule: v.id,
    impact: v.impact,
    help: v.help,
    where: v.nodes.slice(0, 5).map((n) => n.target.join(" ")),
  }));
}

test("the pages checked are the website's pages, none forgotten", () => {
  // Every page.tsx became exactly one route checked below (routeOf throws on a dynamic segment with no
  // sample), and the walk found the real tree, not an empty folder (testing.md section 2).
  expect(PUBLIC_PAGES.length + SIGNED_IN_PAGES.length).toBe(PAGE_FILES.length);
  expect(new Set(ROUTES).size).toBe(ROUTES.length);
  expect(ROUTES).toEqual(expect.arrayContaining(["/", "/sign-in", "/app", "/app/deals", "/app/me"]));
});

for (const view of VIEWS) {
  for (const colorScheme of SCHEMES) {
    for (const reducedMotion of MOTION) {
      const label = `${view.name}, ${colorScheme}, motion ${reducedMotion}`;

      test.describe(label, () => {
        test.use({ viewport: { width: view.width, height: view.height }, colorScheme, reducedMotion });
        // The tokens' dark theme is applied by data-theme on <html>; set it here so the dark runs
        // really render dark, and prove it before checking (a dark run that rendered light would pass
        // while checking nothing).
        test.beforeEach(async ({ page }) => {
          await page.addInitScript((theme) => { document.documentElement.dataset.theme = theme; }, colorScheme);
        });

        for (const path of PUBLIC_PAGES) {
          test(`${path} has no accessibility violation`, async ({ page }) => {
            await page.goto(path);
            await settled(page);
            expect(await violations(page)).toEqual([]);
          });
        }

        // States a page visit never reaches: the onboarding form (anyone with a profile is sent past it), with its errors showing,
        // and the Apply sheet open over a campaign.
        test("a new creator's onboarding steps, the Apply sheet and the report sheet have no accessibility violation", async ({ page }) => {
          await fetch(`${MOCK}/__scenario`, { method: "POST", body: JSON.stringify({ profile: "missing", attention: "empty" }) });
          await signIn(page, "Creator");
          await page.goto("/app/onboarding");
          await settled(page);
          await page.getByRole("button", { name: "Continue" }).click();
          expect(await violations(page), "onboarding step 1, with errors").toEqual([]);
          await page.getByLabel("Your name, as brands will see it").fill("Meena Makes Food");
          await page.getByLabel("Handle").fill("meena.makes");
          await page.getByRole("button", { name: "Continue" }).click();
          await page.getByRole("button", { name: "Food" }).click();
          await settled(page);
          expect(await violations(page), "onboarding step 2").toEqual([]);
          await page.goto("/app/discover/c-5");
          await settled(page);
          await page.getByRole("button", { name: "Apply" }).click();
          await page.getByRole("button", { name: "Send application" }).click();
          await expect(page.getByText("Write at least 20 characters.")).toBeVisible();
          await settled(page);
          expect(await violations(page), "the Apply sheet, with an error").toEqual([]);
          await page.keyboard.press("Escape");
          await page.getByRole("button", { name: "Report or block" }).click();
          await page.getByRole("dialog").getByRole("button", { name: "Send report" }).click();
          await expect(page.getByText("Choose what is wrong.")).toBeVisible();
          await settled(page);
          expect(await violations(page), "the report and block sheet, with an error").toEqual([]);
        });

        for (const role of ["Creator", "Brand"] as const) {
          test(`a ${role.toLowerCase()}'s signed-in pages have no accessibility violation`, async ({ page }) => {
            await signIn(page, role);
            for (const path of SIGNED_IN_PAGES) {
              await page.goto(path);
              await settled(page);
              expect(await violations(page), path).toEqual([]);
            }
          });
        }
      });
    }
  }
}
