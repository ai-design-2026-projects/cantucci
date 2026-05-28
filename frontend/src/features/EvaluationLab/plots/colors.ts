const PALETTE = [
    '#6366f1', // indigo
    '#f59e0b', // amber
    '#10b981', // emerald
    '#ef4444', // red
    '#8b5cf6', // violet
    '#06b6d4', // cyan
    '#f97316', // orange
    '#84cc16', // lime
]

const assigned = new Map<string, string>()

/**
 * Return a stable color string for a given run ID.
 * Colors are assigned in PALETTE order on first call and reused thereafter.
 *
 * @param runId Run UUID string.
 * @returns CSS color string.
 */
export function colorForRun(runId: string): string {
    if (!assigned.has(runId)) {
        assigned.set(runId, PALETTE[assigned.size % PALETTE.length])
    }
    return assigned.get(runId)!
}

/** Return PALETTE[index % PALETTE.length] for positional use (e.g. judge dimensions). */
export function paletteAt(index: number): string {
    return PALETTE[index % PALETTE.length]
}
