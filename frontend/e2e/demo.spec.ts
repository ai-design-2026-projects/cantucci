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

import { test, expect } from "./fixtures";
import { injectCursor, moveAndClick } from "./helpers/cursor";

const TYPE_DELAY = 35;
const TURN_TIMEOUT = 90_000;

test("CinePal demo", async ({ page }) => {
  await page.waitForTimeout(1_000);

  await injectCursor(page);

  await page.goto("http://localhost:5173");

  const composer = page.getByRole("textbox", { name: "Oracle message" });
  await expect(composer).toBeVisible({ timeout: 15_000 });

  await page.waitForTimeout(1200);

  await moveAndClick(page, composer);
  await composer.pressSequentially(
    "Recently I've seen Interstellar, can you suggest something similar?",
    { delay: TYPE_DELAY },
  );
  await page.waitForTimeout(800);

  const sendBtn = page.getByRole("button", { name: "Send message" });
  await moveAndClick(page, sendBtn);

  await expect(composer).toBeEnabled({ timeout: TURN_TIMEOUT });
  await page.waitForTimeout(1500);

  const clustersBtn = page.getByRole("button", { name: "Open clusters panel" });
  await moveAndClick(page, clustersBtn);
  await page.waitForTimeout(1500);

  const sheetViewport = page.locator('[data-radix-scroll-area-viewport]').first();
  const sheetBox = await sheetViewport.boundingBox();
  if (sheetBox) {
    const cx = sheetBox.x + sheetBox.width / 2;
    const cy = sheetBox.y + sheetBox.height / 2;
    await page.mouse.move(cx, cy, { steps: 10 });
    await page.waitForTimeout(400);
    const frames = 30;
    for (let i = 0; i < frames; i++) {
      const t = i / (frames - 1);
      const ease = t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t;
      await page.mouse.wheel(0, Math.round(ease * 16 + 2));
      await page.waitForTimeout(16);
    }
    await page.waitForTimeout(800);
  }

  await page.keyboard.press("Escape");
  await page.waitForTimeout(800);

  await moveAndClick(page, composer);
  await composer.pressSequentially(
    "The sheer sense of cosmic awe",
    { delay: TYPE_DELAY },
  );
  await page.waitForTimeout(800);

  await moveAndClick(page, sendBtn);

  await expect(composer).toBeEnabled({ timeout: TURN_TIMEOUT });
  await page.waitForTimeout(1500);

  await moveAndClick(page, clustersBtn);
  await page.waitForTimeout(2500);

  await page.keyboard.press("Escape");
  await page.waitForTimeout(800);

  await moveAndClick(page, composer);
  await composer.pressSequentially(
    "A mix of both",
    { delay: TYPE_DELAY },
  );
  await page.waitForTimeout(800);

  await moveAndClick(page, sendBtn);

  await expect(composer).toBeEnabled({ timeout: TURN_TIMEOUT });
  await page.waitForTimeout(1000);

  const logBox = await page.locator('[role="log"]').boundingBox();
  if (logBox) {
    const cx = logBox.x + logBox.width / 2;
    const cy = logBox.y + logBox.height / 2;
    await page.mouse.move(cx, cy, { steps: 10 });
    const frames = 40;
    for (let i = 0; i < frames; i++) {
      const t = i / (frames - 1);
      const ease = t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t;
      await page.mouse.wheel(0, Math.round(ease * 18 + 2));
      await page.waitForTimeout(16);
    }
  }
  await page.waitForTimeout(800);

  const heroFilm = page.locator("button.w-full.flex.gap-4").first();
  await moveAndClick(page, heroFilm, { steps: 40, preClickDelay: 200 });
  await page.waitForTimeout(3000);
});
