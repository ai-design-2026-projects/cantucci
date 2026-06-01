export const APP_URL = process.env.APP_URL ?? 'http://localhost:5173/'
export const CDP_ENDPOINT = process.env.CDP_ENDPOINT ?? 'http://localhost:9222'

// Maximum ms to wait for a turn to complete (loading-bubble hidden) — increase for slow machines
export const TIMEOUT_TURN_COMPLETE_MS = 20_000
