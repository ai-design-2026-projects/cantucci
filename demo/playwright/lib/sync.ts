import { expect } from '@playwright/test'
import type { Page, Locator } from '@playwright/test'

const APP_URL = process.env.APP_URL ?? 'http://127.0.0.1:5173'

/** Wait for the backend to finish processing a turn, keyed on the LoadingBubble DOM signal. */
export async function waitForTurnComplete(page: Page, chatInput: Locator): Promise<void> {
    await expect(page.getByTestId('loading-bubble')).toBeVisible({ timeout: 5_000 })
    await expect(page.getByTestId('loading-bubble')).toBeHidden({ timeout: 20_000 })
    await expect(chatInput).toBeEnabled({ timeout: 5_000 })
}

export async function fetchSnapshot(page: Page, snapshotId: string): Promise<unknown> {
    const response = await page.request.get(`${APP_URL}/cluster-snapshots/${snapshotId}`)
    if (!response.ok()) {
        throw new Error(`Could not load snapshot ${snapshotId}: ${response.status()} ${response.statusText()}`)
    }
    return await response.json()
}
