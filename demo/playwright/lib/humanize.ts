import type { Page, Locator } from '@playwright/test'
import { expect } from '@playwright/test'
import type { Cursor } from './cursor'

export const rand = (min: number, max: number) => (min + max) / 2
export const randInt = (min: number, max: number) => Math.round(rand(min, max))
export const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms))

export function easeInOut(t: number): number {
    return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2
}

/** Type text in stable chunks for repeatable demo captures. */
export async function humanType(_page: Page, locator: Locator, text: string): Promise<void> {
    await expect(locator).toBeEnabled({ timeout: 15_000 })
    await locator.scrollIntoViewIfNeeded()
    await locator.focus()
    await sleep(180)

    for (let i = 0; i < text.length;) {
        const ch = text[i]
        const chunkSize = /[,.!?;:]/.test(ch) ? 1 : 5
        const chunk = text.slice(i, i + chunkSize)
        await locator.pressSequentially(chunk, { delay: 20 })
        i += chunk.length

        if (/[,.!?;:]/.test(chunk.at(-1) ?? '')) {
            await sleep(90)
        } else if (chunk.includes(' ')) {
            await sleep(12)
        } else {
            await sleep(16)
        }
    }

    const typedValue = await locator.inputValue()
    if (typedValue !== text) {
        await locator.fill(text)
    }
    await sleep(180)
}

export async function smoothScroll(
    page: Page,
    cursor: Cursor,
    locator: Locator,
    deltaX: number,
    deltaY: number,
    duration = 650,
): Promise<void> {
    const box = await locator.boundingBox()
    if (!box) return
    await cursor.moveTo(
        page,
        box.x + box.width * 0.5,
        box.y + box.height * 0.5,
    )
    await locator.evaluate(
        (el, args) => new Promise<void>((resolve) => {
            const startLeft = el.scrollLeft
            const startTop = el.scrollTop
            const startedAt = performance.now()
            const ease = (t: number) => 1 - Math.pow(1 - t, 3)

            function tick(now: number) {
                const t = Math.min(1, (now - startedAt) / args.duration)
                const eased = ease(t)
                el.scrollLeft = startLeft + args.deltaX * eased
                el.scrollTop = startTop + args.deltaY * eased
                if (t < 1) {
                    requestAnimationFrame(tick)
                } else {
                    resolve()
                }
            }

            requestAnimationFrame(tick)
        }),
        { deltaX, deltaY, duration },
    )
    await sleep(250)
}

export type SubmitMethod = 'button' | 'enter'

/** Submit with fixed timing for repeatable demo captures. */
export async function submitMessageLikeHuman(
    page: Page,
    cursor: Cursor,
    input: Locator,
    method: SubmitMethod = 'button',
): Promise<void> {
    await sleep(600)
    if (method === 'enter') {
        await page.keyboard.press('Enter')
        return
    }

    await cursor.click(page, input.locator('xpath=following-sibling::button[1]'))
}
