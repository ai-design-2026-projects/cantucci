/**
 * Demo recording script for CinePal.
 *
 * Drives a full 3-turn session with human-paced typing and natural pauses.
 * Run against a backend started with CINEPAL_LLM_MODE=replay to avoid
 * real API costs on subsequent takes.
 *
 * Prerequisites (start manually before running):
 *   uvicorn backend.app:app --reload        (port 8000)
 *   npm run dev                              (port 5173, proxies to 8000)
 *
 * Recording:
 *   npm run e2e:headed   (then capture screen with OBS / QuickTime)
 */

import { test, expect } from "@playwright/test";
import { injectCursor } from "./helpers/cursor";

const TYPE_DELAY = 55;
const TURN_TIMEOUT = 90_000;

test("CinePal demo", async ({ page }) => {
  await injectCursor(page);

  await page.goto("/");

  const composer = page.getByRole("textbox", { name: "Oracle message" });
  await expect(composer).toBeVisible({ timeout: 15_000 });

  await page.waitForTimeout(800);

  await composer.click();
  await composer.pressSequentially(
    "I want something cozy — a detective story set in Europe, preferably rainy cities.",
    { delay: TYPE_DELAY },
  );
  await page.waitForTimeout(600);

  await page.getByRole("button", { name: "Send message" }).click();

  await expect(composer).toBeEnabled({ timeout: TURN_TIMEOUT });
  await page.waitForTimeout(1200);

  await page.getByRole("button", { name: "Open clusters panel" }).click();
  await page.waitForTimeout(2000);

  await page.keyboard.press("Escape");
  await page.waitForTimeout(600);

  await composer.click();
  await composer.pressSequentially(
    "Actually I prefer something more recent — post-2010, and with a female lead.",
    { delay: TYPE_DELAY },
  );
  await page.waitForTimeout(500);

  await page.getByRole("button", { name: "Send message" }).click();

  await expect(composer).toBeEnabled({ timeout: TURN_TIMEOUT });
  await page.waitForTimeout(1200);

  await page.getByRole("button", { name: "Open clusters panel" }).click();
  await page.waitForTimeout(2500);

  await page.keyboard.press("Escape");
  await page.waitForTimeout(600);

  await composer.click();
  await composer.pressSequentially(
    "Yes, these look great. I'll go with the second cluster.",
    { delay: TYPE_DELAY },
  );
  await page.waitForTimeout(500);

  await page.getByRole("button", { name: "Send message" }).click();

  await expect(composer).toBeEnabled({ timeout: TURN_TIMEOUT });
  await page.waitForTimeout(2000);
});
