import type { Page, Locator } from '@playwright/test'
import { rand, easeInOut, sleep } from './humanize'

/**
 * Single source of truth for the cursor position.
 * All pointer moves go through this class so the overlay never teleports.
 */
export class Cursor {
    x: number
    y: number

    constructor(x = 96, y = 96) {
        this.x = x
        this.y = y
    }

    /** Move to (x, y) in a straight line with easing and tiny per-step jitter. */
    async moveTo(page: Page, x: number, y: number): Promise<void> {
        const dx = x - this.x
        const dy = y - this.y
        const distance = Math.hypot(dx, dy)
        const steps = Math.max(18, Math.min(56, Math.round(distance / 18)))

        for (let i = 1; i <= steps; i++) {
            const t = easeInOut(i / steps)
            const nx = this.x + dx * t + rand(-0.5, 0.5)
            const ny = this.y + dy * t + rand(-0.5, 0.5)
            await page.mouse.move(nx, ny)
            await sleep(rand(3, 10))
        }

        this.x = x
        this.y = y
        await sleep(rand(80, 220))
    }

    /** Move to a locator's centre then click with natural press-and-release timing. */
    async click(page: Page, locator: Locator): Promise<void> {
        const box = await locator.boundingBox()
        if (!box) {
            throw new Error(`cursor.click: element has no bounding box — locator may not be visible: ${locator}`)
        }
        const insetX = Math.min(box.width * 0.22, 16)
        const insetY = Math.min(box.height * 0.22, 16)
        const tx = box.x + rand(insetX, Math.max(insetX, box.width - insetX))
        const ty = box.y + rand(insetY, Math.max(insetY, box.height - insetY))
        await this.moveTo(page, tx, ty)
        await sleep(rand(80, 260))
        await page.mouse.down()
        await sleep(rand(55, 140))
        await page.mouse.up()
        await sleep(rand(180, 420))
    }
}

export async function injectMacCursor(page: Page, cursor: Cursor): Promise<void> {
    await page.evaluate(({ startX, startY }) => {
        if (document.getElementById('__mac-cursor__')) return

        const style = document.createElement('style')
        style.textContent = '*, *::before, *::after { cursor: none !important; }'
        document.head.appendChild(style)

        const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="22" height="26" viewBox="0 0 22 26">
            <defs>
                <filter id="cs" x="-30%" y="-30%" width="160%" height="160%">
                    <feDropShadow dx="0" dy="1.5" stdDeviation="1.5"
                                  flood-color="#000000" flood-opacity="0.28"/>
                </filter>
            </defs>
            <path d="M 4 2 L 4 20 L 8.5 15.5 L 12 23.5 L 14.5 22.5 L 11 14.5 L 17.5 14.5 Z"
                  fill="white" stroke="#1c1c1e" stroke-width="1.2" stroke-linejoin="round"
                  filter="url(#cs)"/>
        </svg>`

        const el = document.createElement('div')
        el.id = '__mac-cursor__'
        el.style.cssText = [
            'position: fixed',
            'top: 0',
            'left: 0',
            'width: 22px',
            'height: 26px',
            'pointer-events: none',
            'z-index: 2147483647',
            'will-change: transform',
            'transition: transform 90ms linear',
        ].join(';')
        el.innerHTML = svg

        document.addEventListener('mousemove', (e) => {
            el.style.transform = `translate(${e.clientX}px,${e.clientY}px)`
        }, { passive: true })

        // Seed overlay at the Playwright cursor's known start position.
        el.style.transform = `translate(${startX}px,${startY}px)`

        const attach = () => document.body.appendChild(el)
        document.body ? attach() : document.addEventListener('DOMContentLoaded', attach)
    }, { startX: cursor.x, startY: cursor.y })

    // Drive the real pointer to the same coordinates so overlay and Playwright agree.
    await page.mouse.move(cursor.x, cursor.y)
}
