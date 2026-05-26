import { test, expect, chromium } from '@playwright/test'
import type { Page, Locator } from '@playwright/test'
import { Cursor, injectMacCursor } from './lib/cursor'
import { humanType, smoothScroll, submitMessageLikeHuman, sleep, rand } from './lib/humanize'
import { waitForTurnComplete, fetchSnapshot } from './lib/sync'
import { loadRecording } from './lib/recording'

const APP_URL = process.env.APP_URL ?? 'http://127.0.0.1:5173'
const CDP_ENDPOINT = process.env.CDP_ENDPOINT ?? 'http://localhost:9222'
const ANON_CONVERSATION_KEY = 'cinepal_anon_conv_id'

async function visiblePosterTarget(clustersDialog: Locator): Promise<{ index: number; x: number; y: number } | null> {
    const posterButtons = clustersDialog.locator('button:has(img[alt])')
    await expect(posterButtons.first()).toBeVisible({ timeout: 8_000 })

    return await posterButtons.evaluateAll((buttons) => {
        const viewport = {
            left: 0,
            top: 0,
            right: window.innerWidth,
            bottom: window.innerHeight,
        }

        return buttons
            .map((button, index) => {
                const rect = button.getBoundingClientRect()
                const left = Math.max(rect.left, viewport.left)
                const top = Math.max(rect.top, viewport.top)
                const right = Math.min(rect.right, viewport.right)
                const bottom = Math.min(rect.bottom, viewport.bottom)
                const width = Math.max(0, right - left)
                const height = Math.max(0, bottom - top)
                const cx = left + width / 2
                const cy = top + height / 2
                const hit = document.elementFromPoint(cx, cy)
                const receivesPointer = hit === button || button.contains(hit)

                return {
                    index,
                    area: receivesPointer ? width * height : 0,
                    x: cx,
                    y: cy,
                }
            })
            .filter((candidate) => candidate.area > 900)
            .sort((a, b) => b.area - a.area)[0] ?? null
    })
}

async function previewMovieFromInspect(page: Page, cursor: Cursor, clustersDialog: Locator): Promise<void> {
    const target = await visiblePosterTarget(clustersDialog)
    if (!target) {
        throw new Error('No visible exemplar movie button found in Inspect.')
    }

    const posterButton = clustersDialog.locator('button:has(img[alt])').nth(target.index)
    await cursor.click(page, posterButton)

    const movieDialog = page.locator('[role="dialog"]').filter({ has: page.locator('img.w-28') })
    await expect(movieDialog).toBeVisible({ timeout: 4_000 })
    await sleep(rand(900, 1300))
    await cursor.click(page, movieDialog.locator('button.absolute.right-4.top-4'))
    await expect(movieDialog).toBeHidden({ timeout: 4_000 })
}

async function closeDialog(page: Page, cursor: Cursor, dialog: Locator): Promise<void> {
    const absoluteBtn = dialog.locator('button.absolute.right-4.top-4')
    const iconBtn = dialog.locator('button.h-9.w-9')
    const closeBtn = await absoluteBtn.isVisible() ? absoluteBtn : iconBtn
    await cursor.click(page, closeBtn)
    await expect(dialog).toBeHidden({ timeout: 3_000 })
}

async function previewUnclusteredMap(page: Page, cursor: Cursor): Promise<void> {
    await cursor.click(page, page.getByRole('button', { name: 'Evolution' }))
    const evolutionModal = page.getByTestId('evolution-map-modal')
    await expect(page.locator('svg g[data-operation]').first()).toBeVisible({ timeout: 5_000 })
    await sleep(rand(800, 1200))

    const unclusteredNode = page.locator('svg g[data-operation="unclustered"]').first()
    await cursor.click(page, unclusteredNode)
    await sleep(rand(600, 1000))
    await closeDialog(page, cursor, evolutionModal)
    await sleep(rand(400, 700))
}

async function previewFilterMap(page: Page, cursor: Cursor): Promise<void> {
    await cursor.click(page, page.getByRole('button', { name: 'Evolution' }))
    const evolutionModal = page.getByTestId('evolution-map-modal')
    await expect(page.locator('svg g[data-operation]').first()).toBeVisible({ timeout: 5_000 })
    await sleep(rand(800, 1200))

    const filterNode = page.locator('svg g[data-operation="cross_filter"]').first()
    await cursor.click(page, filterNode)
    await sleep(rand(600, 1000))
    await closeDialog(page, cursor, evolutionModal)
    await sleep(rand(400, 700))
}

test('CinePal scripted demo', async () => {
    const { turns } = loadRecording()

    const browser = await chromium.connectOverCDP(CDP_ENDPOINT)
    const contexts = browser.contexts()
    if (contexts.length === 0) {
        throw new Error(
            `No Chrome context found at ${CDP_ENDPOINT}.\n` +
            'Start Chrome with: google-chrome --remote-debugging-port=9222 --user-data-dir=/tmp/chrome-demo',
        )
    }
    const context = contexts[0]
    const existingPages = context.pages()
    const page = existingPages.length > 0 ? existingPages[0] : await context.newPage()
    await page.bringToFront()

    await page.evaluate(() =>
        document.documentElement.requestFullscreen().catch(() => {}),
    )

    await page.goto(APP_URL)
    await page.evaluate((anonKey) => {
        localStorage.removeItem(anonKey)
        sessionStorage.clear()
        window.history.replaceState(null, '', '/')
    }, ANON_CONVERSATION_KEY)
    await page.goto(APP_URL)

    const cursor = new Cursor(96, 96)
    await injectMacCursor(page, cursor)

    await cursor.click(page, page.getByRole('button', { name: 'Start with Poppy' }))
    const chatInput = page.getByPlaceholder('Ask Poppy something…')
    await expect(chatInput).toBeVisible({ timeout: 15_000 })

    await humanType(page, chatInput, turns[0].user_message)
    await submitMessageLikeHuman(page, cursor, chatInput)
    await waitForTurnComplete(page, chatInput)
    await fetchSnapshot(page, turns[0].cluster_snapshot_id)
    await sleep(rand(500, 800))

    await cursor.click(page, page.getByRole('button', { name: 'Inspect' }))
    const clustersDialog = page.getByRole('dialog').filter({ hasText: 'Clusters' })
    await expect(clustersDialog).toBeVisible({ timeout: 5_000 })
    await sleep(rand(700, 1100))

    const exemplarStrip = clustersDialog.locator('[class*="overflow-x-auto"]').first()
    const clusterList = clustersDialog.locator('[class*="overflow-y-auto"]').first()
    await smoothScroll(page, cursor, exemplarStrip, 400, 0, 1000)
	await smoothScroll(page, cursor, exemplarStrip, -400, 0, 1000)
    await smoothScroll(page, cursor, clusterList, 0, 820, 1050)
    await smoothScroll(page, cursor, clusterList, 0, -820, 950)
    await previewMovieFromInspect(page, cursor, clustersDialog)
    await sleep(rand(250, 450))
    await closeDialog(page, cursor, clustersDialog)
    await sleep(rand(800, 1200))

    await previewUnclusteredMap(page, cursor)

    for (const [offset, turn] of turns.slice(1).entries()) {
        const turnNumber = offset + 2
        await humanType(page, chatInput, turn.user_message)
        await submitMessageLikeHuman(page, cursor, chatInput)
        await waitForTurnComplete(page, chatInput)
        await sleep(rand(500, 800))

        if (turnNumber === 4) {
            await previewFilterMap(page, cursor)
        }
    }

    const openDialog = page.getByRole('dialog').first()
    if (await openDialog.isVisible()) {
        await closeDialog(page, cursor, openDialog)
    }
    await sleep(2000)

    await sleep(rand(800, 1200))
    await page.evaluate((anonKey) => {
        localStorage.removeItem(anonKey)
        sessionStorage.clear()
    }, ANON_CONVERSATION_KEY)
    await page.goto(APP_URL)
    await injectMacCursor(page, cursor)

    // Do NOT close the browser — disconnecting from CDP would kill the user's Chrome.
})
