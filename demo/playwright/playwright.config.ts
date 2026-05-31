import { defineConfig } from '@playwright/test'

export default defineConfig({
    testDir: '.',
    testMatch: 'demo-scripted.spec.ts',
    timeout: 180_000,
    retries: 0,
    workers: 1,
    use: {},
})
