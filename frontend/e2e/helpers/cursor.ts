import type { Locator, Page } from "@playwright/test";

/**
 * Injects a visible software cursor into the page so external screen
 * recorders capture pointer movement (Playwright's native cursor is not
 * rendered in the composited frame that recorders see).
 */
export async function injectCursor(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><path d="M5 3l14 9-7 1-4 7L5 3z" fill="white" stroke="#222" stroke-width="1.5" stroke-linejoin="round"/></svg>`;
    const el = document.createElement("div");
    el.id = "__demo_cursor__";
    el.style.cssText = [
      "position:fixed",
      "top:0",
      "left:0",
      "width:24px",
      "height:24px",
      "pointer-events:none",
      "z-index:2147483647",
      "transition:left 40ms linear,top 40ms linear",
      "filter:drop-shadow(0 1px 3px rgba(0,0,0,0.4))",
      "will-change:left,top",
    ].join(";");
    el.innerHTML = svg;
    const attach = () => document.body.appendChild(el);
    if (document.body) attach();
    else document.addEventListener("DOMContentLoaded", attach);
    document.addEventListener("mousemove", (e) => {
      el.style.left = e.clientX + "px";
      el.style.top = e.clientY + "px";
    });
  });
}

/**
 * Moves the mouse to the center of a locator in human-like steps,
 * then clicks it. Use instead of locator.click() in demo specs.
 */
export async function moveAndClick(
  page: Page,
  locator: Locator,
  options?: { steps?: number; preClickDelay?: number },
): Promise<void> {
  const { steps = 18, preClickDelay = 80 } = options ?? {};
  const box = await locator.boundingBox();
  if (!box) {
    await locator.click();
    return;
  }
  const x = box.x + box.width / 2;
  const y = box.y + box.height / 2;
  await page.mouse.move(x, y, { steps });
  await page.waitForTimeout(preClickDelay);
  await page.mouse.click(x, y);
}
