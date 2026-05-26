import type { Page, Locator } from '@playwright/test'
import { expect } from '@playwright/test'
import type { Cursor } from './cursor'

export const rand = (min: number, max: number) => min + Math.random() * (max - min)
export const randInt = (min: number, max: number) => Math.round(rand(min, max))
export const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms))

export function easeInOut(t: number): number {
    return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2
}

function typoFor(ch: string): string | null {
    const lower = ch.toLowerCase()
    const neighbors: Record<string, string[]> = {
        a: ['s', 'q', 'z'],
        e: ['w', 'r', 'd'],
        i: ['u', 'o', 'k'],
        o: ['i', 'p', 'l'],
        r: ['e', 't', 'f'],
        s: ['a', 'd', 'w'],
        t: ['r', 'y', 'g'],
        n: ['b', 'm', 'j'],
    }
    const options = neighbors[lower]
    if (!options) return null
    const typo = options[randInt(0, options.length - 1)]
    return ch === lower ? typo : typo.toUpperCase()
}

/** Type text character-by-character with jitter to mimic a real typist. */
export async function humanType(page: Page, locator: Locator, text: string): Promise<void> {
    await expect(locator).toBeEnabled({ timeout: 15_000 })
    await locator.scrollIntoViewIfNeeded()
    await locator.click({ force: true })
    await locator.focus()
    await sleep(rand(120, 260))

    for (let i = 0; i < text.length;) {
        const ch = text[i]
        const typo = text.length > 18 && Math.random() < 0.004 ? typoFor(ch) : null
        if (typo && ch) {
            await locator.pressSequentially(typo, { delay: randInt(12, 35) })
            await sleep(rand(70, 150))
            await page.keyboard.press('Backspace')
            await sleep(rand(35, 90))
        }

        const chunkSize = /[,.!?;:]/.test(ch) ? 1 : randInt(3, 7)
        const chunk = text.slice(i, i + chunkSize)
        await locator.pressSequentially(chunk, { delay: randInt(10, 30) })
        i += chunk.length

        if (/[,.!?;:]/.test(chunk.at(-1) ?? '')) {
            await sleep(rand(45, 140))
        } else if (chunk.includes(' ')) {
            await sleep(rand(4, 22))
        } else {
            await sleep(rand(6, 26))
        }

        if (Math.random() < 0.008) await sleep(rand(120, 280))
    }

    const typedValue = await locator.inputValue()
    if (typedValue !== text) {
        await locator.fill(text)
    }
    await sleep(rand(120, 260))
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
        box.x + box.width * rand(0.38, 0.62),
        box.y + box.height * rand(0.38, 0.62),
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
    await sleep(rand(180, 320))
}

/** Press Enter or click the submit button, like a human would. */
export async function submitMessageLikeHuman(page: Page, cursor: Cursor, input: Locator): Promise<void> {
    await sleep(rand(350, 900))
    if (Math.random() < 0.72) {
        await page.keyboard.press('Enter')
        return
    }
    await cursor.click(page, input.locator('xpath=following-sibling::button[1]'))
}
