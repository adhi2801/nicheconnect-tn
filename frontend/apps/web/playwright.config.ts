import { defineConfig } from "@playwright/test";

const WEB = 3131;
const MOCK = 8098;
const env = { API_URL: `http://localhost:${MOCK}`, NEXT_PUBLIC_API_URL: `http://localhost:${MOCK}`, NEXT_DIST_DIR: ".next-e2e", PORT: String(MOCK) };

// Runs against the website built for production plus a stand-in for the backend's login endpoints (e2e/mock-api.mjs).
// Uses the Chrome already installed on the machine, so no browser is downloaded.
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"]],
  use: { baseURL: `http://localhost:${WEB}`, channel: "chrome", trace: "retain-on-failure", extraHTTPHeaders: { "x-forwarded-for": "203.0.113.7" } },
  webServer: [
    { command: "node e2e/mock-api.mjs", url: `http://localhost:${MOCK}/__state`, env, reuseExistingServer: !process.env.CI },
    { command: `pnpm build && pnpm start -p ${WEB}`, url: `http://localhost:${WEB}/sign-in`, env, timeout: 240_000, reuseExistingServer: !process.env.CI },
  ],
});
