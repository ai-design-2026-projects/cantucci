import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
    testDir: './tests',
    timeout: 120_000,
    retries: 0,
    workers: 1,
    use: {
        baseURL: process.env.APP_URL ?? 'http://127.0.0.1:5173',
        headless: process.env.HEADLESS === '1',
        viewport: { width: 1280, height: 800 },
        video: process.env.RECORD_VIDEO === '1' ? 'on' : 'off',
    },
    projects: [
        {
            name: 'chromium',
            use: { ...devices['Desktop Chrome'] },
        },
    ],
})
