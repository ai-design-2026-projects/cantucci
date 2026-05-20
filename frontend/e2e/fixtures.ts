import { test as base, chromium } from "@playwright/test";
import type { Page } from "@playwright/test";

export const test = base.extend<{ page: Page }>({
  page: async ({}, use) => {
    const browser = await chromium.connectOverCDP("http://localhost:9222");
    const context = browser.contexts()[0];
    const page = context.pages()[0] ?? (await context.newPage());
    await use(page);
  },
});

export { expect } from "@playwright/test";
