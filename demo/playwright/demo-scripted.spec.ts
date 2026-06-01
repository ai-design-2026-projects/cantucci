import { test, expect, chromium } from '@playwright/test'
import type { Page, Locator } from '@playwright/test'
import { Cursor, injectMacCursor } from './lib/cursor'
import { humanType, smoothScroll, submitMessageLikeHuman, sleep, rand } from './lib/humanize'
import { waitForTurnComplete, fetchSnapshot } from './lib/sync'
import { loadRecording } from './lib/recording'
import { APP_URL, CDP_ENDPOINT } from './lib/constants'

const ANON_CONVERSATION_KEY = 'cinepal_anon_conv_id'
const CHART_MARGIN = { top: 8, right: 8, bottom: 8, left: 8 }

interface DemoSnapshotMember {
    cluster_id: string
    probability: number
    umap_x: number
    umap_y: number
}

interface DemoSnapshot {
    clusters: Array<{ id: string }>
    members: DemoSnapshotMember[]
}

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

async function previewConceptAxis(page: Page, cursor: Cursor, hoverTitles: string[]): Promise<void> {
    const axisBtn = page.getByRole('button', { name: 'View axis distribution' }).last()
    await axisBtn.scrollIntoViewIfNeeded()
    await cursor.click(page, axisBtn)
    const conceptAxisDialog = page.getByRole('dialog').filter({ hasText: 'How your films spread out' })
    await expect(conceptAxisDialog).toBeVisible({ timeout: 5_000 })
    await expect(conceptAxisDialog.locator('g.recharts-scatter-symbol circle').first()).toBeVisible({ timeout: 8_000 })
    await showTooltipTitles(page, cursor, conceptAxisDialog, hoverTitles)
    await sleep(rand(500, 800))
    await closeDialog(page, cursor, conceptAxisDialog)
}

function computeMemberDomain(members: DemoSnapshotMember[]): { x: [number, number]; y: [number, number] } {
    let xMin = Infinity, xMax = -Infinity, yMin = Infinity, yMax = -Infinity
    for (const member of members) {
        if (member.umap_x < xMin) xMin = member.umap_x
        if (member.umap_x > xMax) xMax = member.umap_x
        if (member.umap_y < yMin) yMin = member.umap_y
        if (member.umap_y > yMax) yMax = member.umap_y
    }

    const xPad = (xMax - xMin) * 0.05 || 1
    const yPad = (yMax - yMin) * 0.05 || 1
    return {
        x: [xMin - xPad, xMax + xPad],
        y: [yMin - yPad, yMax + yPad],
    }
}

function computeCentroids(snapshot: DemoSnapshot): Array<{ clusterId: string; x: number; y: number }> {
    const centroids: Array<{ clusterId: string; x: number; y: number }> = []

    for (const cluster of snapshot.clusters) {
        let sumW = 0, sumX = 0, sumY = 0
        for (const member of snapshot.members) {
            if (member.cluster_id !== cluster.id) continue
            sumW += member.probability
            sumX += member.probability * member.umap_x
            sumY += member.probability * member.umap_y
        }
        if (sumW > 0) {
            centroids.push({ clusterId: cluster.id, x: sumX / sumW, y: sumY / sumW })
        }
    }

    return centroids
}

async function fetchRootSnapshot(page: Page): Promise<DemoSnapshot> {
    const snapshotUrl = new URL('/cluster-snapshots/root', APP_URL).toString()
    const response = await page.request.get(snapshotUrl)
    if (!response.ok()) {
        throw new Error(`Could not load root snapshot: ${response.status()} ${response.statusText()}`)
    }
    return await response.json() as DemoSnapshot
}

async function previewFirstCentroids(page: Page, cursor: Cursor, snapshot: DemoSnapshot, count: number): Promise<void> {
    const rootSnapshot = await fetchRootSnapshot(page)
    const domain = computeMemberDomain(rootSnapshot.members)
    const canvas = page.locator('canvas').first()
    await expect(canvas).toBeVisible({ timeout: 5_000 })
    const box = await canvas.boundingBox()
    if (!box) {
        throw new Error('Could not locate snapshot canvas for centroid preview.')
    }

    const plotW = box.width - CHART_MARGIN.left - CHART_MARGIN.right
    const plotH = box.height - CHART_MARGIN.top - CHART_MARGIN.bottom
    const xRange = domain.x[1] - domain.x[0]
    const yRange = domain.y[1] - domain.y[0]

    for (const centroid of computeCentroids(snapshot).slice(0, count)) {
        const x = box.x + CHART_MARGIN.left + ((centroid.x - domain.x[0]) / xRange) * plotW
        const y = box.y + CHART_MARGIN.top + ((domain.y[1] - centroid.y) / yRange) * plotH
        await cursor.moveTo(page, x, y)
        await sleep(350)
        await page.mouse.down()
        await sleep(95)
        await page.mouse.up()
        await sleep(900)
    }
}

async function showTooltipTitles(
    page: Page,
    cursor: Cursor,
    root: Locator,
    titles: string[],
): Promise<void> {
    const targets = await root.locator('g.recharts-scatter-symbol circle').evaluateAll(
        (circles, wantedTitles) => wantedTitles.map((title) => {
            const match = circles.find((circle) => circle.getAttribute('data-axis-movie-title') === title)
            if (!match) return null

            const rect = match.getBoundingClientRect()
            return {
                x: rect.left + rect.width / 2,
                y: rect.top + rect.height / 2,
            }
        }),
        titles,
    )

    for (const [index, target] of targets.entries()) {
        if (!target) {
            throw new Error(`Could not find concept-axis hover point for title "${titles[index]}".`)
        }
        await cursor.moveTo(page, target.x, target.y)
        await sleep(rand(700, 1100))
    }
}

test('CinePal scripted demo', async () => {
    const { turns } = loadRecording()

    // Load the user's Chrome and connect to it via CDP
    const browser = await chromium.connectOverCDP(CDP_ENDPOINT)
    const contexts = browser.contexts()
    if (contexts.length === 0) {
        throw new Error(
            `No Chrome context found at ${CDP_ENDPOINT}.\n` +
            'Start Chrome with: google-chrome --remote-debugging-port=9222 --user-data-dir=/tmp/cinepal-demo-chrome',
        )
    }
    const context = contexts[0]
    const existingPages = context.pages()
    const page = existingPages.length > 0 ? existingPages[0] : await context.newPage()
    await page.bringToFront()
    await page.evaluate(() =>
        document.documentElement.requestFullscreen().catch(() => {}),
    )

    // Clear any existing conversation state and start fresh
    await page.goto(APP_URL)
    await page.evaluate((anonKey) => {
        localStorage.removeItem(anonKey)
        sessionStorage.clear()
        window.history.replaceState(null, '', '/')
    }, ANON_CONVERSATION_KEY)
    await page.goto(APP_URL)

    // Inject the cursor and start the demo
    const cursor = new Cursor(96, 96)
    await injectMacCursor(page, cursor)
    
    // Click the "Start with Poppy" button to begin the conversation
    await cursor.click(page, page.getByRole('button', { name: 'Start with Poppy' }))
    
    // Find and interact with the chat input
    const chatInput = page.getByPlaceholder('Try: "Group action movies separately"')
    await expect(chatInput).toBeVisible({ timeout: 15_000 })
    await humanType(page, chatInput, turns[0].user_message)
    await submitMessageLikeHuman(page, cursor, chatInput, 'button')
    await waitForTurnComplete(page, chatInput)

    // Fetch the cluster snapshot for the first turn to ensure it's loaded before we interact with the Inspect button
    await fetchSnapshot(page, turns[0].cluster_snapshot_id)
    await sleep(rand(500, 800))

    // Interact with the Inspect button and explore the resulting dialogs and maps
    await cursor.click(page, page.getByRole('button', { name: 'Inspect' }))
    const clustersDialog = page.getByRole('dialog').filter({ hasText: 'Clusters' })
    await expect(clustersDialog).toBeVisible({ timeout: 5_000 })
    await sleep(rand(700, 1100))
    const exemplarStrip = clustersDialog.locator('[class*="overflow-x-auto"]').first()
    const clusterList = clustersDialog.locator('[class*="overflow-y-auto"]').first()
    await smoothScroll(page, cursor, exemplarStrip, 400, 0, 1000)
    await smoothScroll(page, cursor, exemplarStrip, -400, 0, 1000)
    await smoothScroll(page, cursor, clusterList, 0, 1280, 1250)
    await smoothScroll(page, cursor, clusterList, 0, -1280, 1050)
    await previewMovieFromInspect(page, cursor, clustersDialog)
    await sleep(rand(250, 450))
    await closeDialog(page, cursor, clustersDialog)
    await sleep(rand(800, 1200))

    // Go back to the unclustered state and send next message
    await previewUnclusteredMap(page, cursor)
    await humanType(page, chatInput, turns[1].user_message)
    await submitMessageLikeHuman(page, cursor, chatInput, 'enter')
    await waitForTurnComplete(page, chatInput)
    //Set the list of points we want to hover over on the concept axis — these were determined by inspecting the snapshot for turn 2 and finding interesting points to highlight.
    const conceptAxisHoverTitles = [
        'Midsommar',
        'Shutter Island',
        'Fight Club',
        'Pulp Fiction',
        'Scarface',
        'Batman v Superman: Dawn of Justice',
    ]
    await previewConceptAxis(page, cursor, conceptAxisHoverTitles)
    await sleep(rand(500, 800))
    // Send the mesage confirming the number of clusters
    await humanType(page, chatInput, turns[2].user_message)
    await submitMessageLikeHuman(page, cursor, chatInput, 'enter')
    await waitForTurnComplete(page, chatInput)
    const confirmationSnapshot = await fetchSnapshot(page, turns[2].cluster_snapshot_id) as DemoSnapshot
    await sleep(rand(500, 800))

    await previewFirstCentroids(page, cursor, confirmationSnapshot, 2)

    // Focus and deterministic split
    await humanType(page, chatInput, turns[3].user_message)
    await submitMessageLikeHuman(page, cursor, chatInput, 'enter')
    await waitForTurnComplete(page, chatInput)
    await fetchSnapshot(page, turns[3].cluster_snapshot_id)
    //Find the chat message container and scroll to the bottom to show the latest message
    const chatMessages = chatInput.locator('xpath=ancestor::div[contains(@class, "border-t")]/preceding-sibling::div[contains(@class, "overflow-y-auto")][1]')

    await chatMessages.evaluate((el) => {
        el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
    })
    await sleep(3000)
    // Confirm the buckets for the split
    await humanType(page, chatInput, turns[4].user_message)
    await submitMessageLikeHuman(page, cursor, chatInput, 'enter')
    await waitForTurnComplete(page, chatInput)
    await fetchSnapshot(page, turns[4].cluster_snapshot_id)
    await sleep(rand(500, 800))
    
    // Quick Inspect showcase — scroll only, no clicks
    await cursor.click(page, page.getByRole('button', { name: 'Inspect' }))
    const postSplitDialog = page.getByRole('dialog').filter({ hasText: 'Clusters' })
    await expect(postSplitDialog).toBeVisible({ timeout: 5_000 })
    await sleep(rand(500, 800))
    const postSplitStrip = postSplitDialog.locator('[class*="overflow-x-auto"]').first()
    // Horizontal scroll of exemplar strip to show more exemplars in the split view
    await smoothScroll(page, cursor, postSplitStrip, 300, 0, 800)
    await smoothScroll(page, cursor, postSplitStrip, -300, 0, 800)
    // Vertical scroll of cluster list to show more clusters in the split view
    const postSplitClusterList = postSplitDialog.locator('[class*="overflow-y-auto"]').first()
    await smoothScroll(page, cursor, postSplitClusterList, 0, 800, 900)
    await closeDialog(page, cursor, postSplitDialog)
    await sleep(rand(500, 800))

    // Turn 5 — colour palette concept axis
    await chatMessages.evaluate((el) => {
        el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
    })
    await previewUnclusteredMap(page, cursor)
    await humanType(page, chatInput, turns[5].user_message)
    await submitMessageLikeHuman(page, cursor, chatInput, 'enter')
    await waitForTurnComplete(page, chatInput)
    
    const colourAxisHoverTitles = [
        'Mad Max: Fury Road',
        'Pulp Fiction',
        'Frozen',
        'The Dark Knight Rises',
        'Shutter Island',

    ]
    await previewConceptAxis(page, cursor, colourAxisHoverTitles)
    await sleep(rand(500, 800))

    // Turn 6 — confirm 3 clusters + show cluster details
    await humanType(page, chatInput, turns[6].user_message)
    await submitMessageLikeHuman(page, cursor, chatInput, 'enter')
    await waitForTurnComplete(page, chatInput)
    const finalSnapshot = await fetchSnapshot(page, turns[6].cluster_snapshot_id) as DemoSnapshot
    await sleep(rand(500, 800))

    await cursor.click(page, page.getByRole('button', { name: 'Inspect' }))
    const finalClustersDialog = page.getByRole('dialog').filter({ hasText: 'Clusters' })
    await expect(finalClustersDialog).toBeVisible({ timeout: 5_000 })
    await sleep(rand(700, 1100))
    const finalExemplarStrip = finalClustersDialog.locator('[class*="overflow-x-auto"]').first()
    const finalClusterList = finalClustersDialog.locator('[class*="overflow-y-auto"]').first()
    await smoothScroll(page, cursor, finalExemplarStrip, 400, 0, 1000)
    await smoothScroll(page, cursor, finalExemplarStrip, -400, 0, 1000)
    await smoothScroll(page, cursor, finalClusterList, 0, 1280, 1250)

    // End of the demo — show how to clean up any open dialogs and reset the app state without closing the browser (since it's the user's Chrome)
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
