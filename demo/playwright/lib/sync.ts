import { expect } from '@playwright/test'
import type { Page, Locator } from '@playwright/test'
import { APP_URL } from './constants'

/** Wait for the backend to finish processing a turn, keyed on the LoadingBubble DOM signal. */
export async function waitForTurnComplete(page: Page, chatInput: Locator): Promise<void> {
    await expect(page.getByTestId('loading-bubble')).toBeVisible({ timeout: 5_000 })
    await expect(page.getByTestId('loading-bubble')).toBeHidden({ timeout: 20_000 })
    await expect(chatInput).toBeEnabled({ timeout: 5_000 })
}

export async function fetchSnapshot(page: Page, snapshotId: string): Promise<unknown> {
    const snapshotUrl = new URL(`/cluster-snapshots/get/${snapshotId}`, APP_URL).toString()
    const response = await page.request.get(snapshotUrl)
    if (!response.ok()) {
        throw new Error(`Could not load snapshot ${snapshotId}: ${response.status()} ${response.statusText()}`)
    }
    const contentType = response.headers()['content-type'] ?? ''
    if (!contentType.includes('application/json')) {
        const body = await response.text()
        throw new Error(
            `Could not load snapshot ${snapshotId}: expected JSON from ${snapshotUrl}, ` +
            `received ${contentType || 'unknown content type'}: ${body.slice(0, 80)}`,
        )
    }
    return await response.json()
}
