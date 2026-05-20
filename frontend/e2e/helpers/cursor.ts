import type { Page } from "@playwright/test";

/**
 * Injects a visible software cursor dot into the page so external screen
 * recorders capture pointer movement (Playwright's native cursor is not
 * rendered in the composited frame that recorders see).
 */
export async function injectCursor(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const dot = document.createElement("div");
    dot.id = "__demo_cursor__";
    dot.style.cssText = [
      "position:fixed",
      "top:0",
      "left:0",
      "width:16px",
      "height:16px",
      "border-radius:50%",
      "background:rgba(220,38,38,0.85)",
      "box-shadow:0 0 0 2px rgba(255,255,255,0.7),0 2px 8px rgba(0,0,0,0.4)",
      "pointer-events:none",
      "z-index:2147483647",
      "transform:translate(-50%,-50%)",
      "transition:transform 60ms ease",
    ].join(";");
    document.addEventListener("DOMContentLoaded", () => document.body.appendChild(dot));
    document.addEventListener("mousemove", (e) => {
      dot.style.left = e.clientX + "px";
      dot.style.top = e.clientY + "px";
    });
  });
}
