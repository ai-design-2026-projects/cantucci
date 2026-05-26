import { test, expect } from '@playwright/test'
import * as fs from 'fs'
import * as path from 'path'

interface Turn {
    user_message: string
    assistant: { content: string }
    cluster_snapshot_id: string
}

interface Recording {
    name: string
    turns: Turn[]
}

function loadRecording(): Recording {
    const recordingPath = process.env.DEMO_RECORDING
    if (!recordingPath) {
        throw new Error(
            'DEMO_RECORDING env var must point to a recording JSON file.\n' +
            'Example: DEMO_RECORDING=../recordings/smoke.json npx playwright test --headed'
        )
    }
    const resolved = path.isAbsolute(recordingPath)
        ? recordingPath
        : path.resolve(__dirname, '..', recordingPath)
    return JSON.parse(fs.readFileSync(resolved, 'utf-8')) as Recording
}

const TURN_PAUSE_MS = parseInt(process.env.DEMO_TURN_PAUSE_MS ?? '1500', 10)

test('CinePal demo replay', async ({ page }) => {
    const recording = loadRecording()

    // Navigate to the app and start a new conversation.
    await page.goto('/')
    await page.getByRole('button', { name: 'Start with Poppy' }).click()

    // Wait until the chat input is visible — the conversation is ready.
    const chatInput = page.getByPlaceholder('Ask Poppy something…')
    await expect(chatInput).toBeVisible({ timeout: 15_000 })

    for (const turn of recording.turns) {
        // Type the user message into the chat textarea.
        await chatInput.click()
        await chatInput.fill(turn.user_message)

        // Submit with Enter.
        await chatInput.press('Enter')

        // Wait for the assistant reply to appear. The last message in the list
        // should contain the recorded assistant content.
        await expect(
            page.locator('text=' + turn.assistant.content.slice(0, 60))
        ).toBeVisible({ timeout: 30_000 })

        // Pause before the next turn so the demo flows naturally.
        if (TURN_PAUSE_MS > 0) {
            await page.waitForTimeout(TURN_PAUSE_MS)
        }
    }
})
