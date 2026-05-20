import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  retries: 0,
  workers: 1,
  timeout: 300_000,
  reporter: "list",
  use: {
    baseURL: "http://localhost:5173",
    headless: false,
    viewport: null,
    launchOptions: {
      slowMo: 120,
    },
    video: "off",
    trace: "off",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
