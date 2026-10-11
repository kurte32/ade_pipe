import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end tests against the running local stack (make up + pnpm dev).
 * PWA at :5173, admin at :5174, API proxied through Vite, dev identity provider at :8001.
 */
export default defineConfig({
  testDir: "./tests",
  globalSetup: "./global-setup.ts",
  globalTeardown: "./global-teardown.ts",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    locale: "es-MX",
    timezoneId: "America/Mexico_City",
  },
  projects: [
    {
      name: "pwa-mobile",
      use: { ...devices["Pixel 7"], baseURL: process.env.PWA_URL ?? "http://localhost:5173" },
      testMatch: /pwa\..*\.spec\.ts/,
    },
    {
      name: "admin-desktop",
      use: { ...devices["Desktop Chrome"], baseURL: process.env.ADMIN_URL ?? "http://localhost:5174" },
      testMatch: /admin\..*\.spec\.ts/,
    },
    // The coordinator flow (pwa.flow.spec.ts) runs under pwa-mobile above. The former "flows"
    // desktop project matched nothing (its testMatch lacked the leading dot) and is removed to
    // avoid implying desktop flow coverage that never ran (audit C11).
  ],
});
